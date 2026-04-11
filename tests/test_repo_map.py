"""Tests for harness/repo_map.py — tree-sitter repo map generation."""

import os
from unittest.mock import patch, MagicMock

import pytest

from harness.repo_map import (
    is_indexable,
    extract_symbols,
    generate_repo_map,
    _format_symbols,
    _should_exclude,
    _ALLOWED_EXTENSIONS,
    _DEFAULT_EXCLUDE_DIRS,
    _MAX_INDEX_FILE_SIZE,
)


# ---------------------------------------------------------------------------
# Helper: lightweight mock of tree_sitter.Node
# ---------------------------------------------------------------------------
class MockNode:
    """Mimics tree-sitter Node for testing AST walking logic."""

    def __init__(self, node_type, text=b"", children=None,
                 start_point=(0, 0), fields=None):
        self.type = node_type
        self.text = text
        self.children = children or []
        self.start_point = start_point
        self._fields = fields or {}

    def child_by_field_name(self, name):
        return self._fields.get(name)


# ===========================================================================
# is_indexable
# ===========================================================================
class TestIsIndexable:
    def test_python_file(self):
        assert is_indexable("foo.py") is True

    def test_javascript_file(self):
        assert is_indexable("app.js") is True

    def test_typescript_file(self):
        assert is_indexable("index.ts") is True

    def test_go_file(self):
        assert is_indexable("main.go") is True

    def test_rust_file(self):
        assert is_indexable("lib.rs") is True

    def test_c_and_cpp_files(self):
        assert is_indexable("main.c") is True
        assert is_indexable("main.cpp") is True

    def test_java_file(self):
        assert is_indexable("App.java") is True

    def test_header_files(self):
        assert is_indexable("header.h") is True
        assert is_indexable("class.hpp") is True

    def test_text_file_rejected(self):
        assert is_indexable("readme.txt") is False

    def test_markdown_rejected(self):
        assert is_indexable("docs.md") is False

    def test_case_insensitive(self):
        assert is_indexable("Main.PY") is True

    def test_all_allowed_extensions_accepted(self):
        for ext in _ALLOWED_EXTENSIONS:
            assert is_indexable(f"test{ext}") is True


# ===========================================================================
# _should_exclude
# ===========================================================================
class TestShouldExclude:
    def test_git_excluded(self):
        assert _should_exclude(".git", _DEFAULT_EXCLUDE_DIRS) is True

    def test_pycache_excluded(self):
        assert _should_exclude("__pycache__", _DEFAULT_EXCLUDE_DIRS) is True

    def test_node_modules_excluded(self):
        assert _should_exclude("node_modules", _DEFAULT_EXCLUDE_DIRS) is True

    def test_venv_variants_excluded(self):
        assert _should_exclude(".venv", _DEFAULT_EXCLUDE_DIRS) is True
        assert _should_exclude("venv", _DEFAULT_EXCLUDE_DIRS) is True

    def test_normal_dirs_not_excluded(self):
        assert _should_exclude("harness", _DEFAULT_EXCLUDE_DIRS) is False
        assert _should_exclude("src", _DEFAULT_EXCLUDE_DIRS) is False

    def test_egg_info_excluded(self):
        assert _should_exclude("my_package.egg-info", _DEFAULT_EXCLUDE_DIRS) is True


# ===========================================================================
# _format_symbols
# ===========================================================================
class TestFormatSymbols:
    def test_single_function(self):
        symbols = [{"name": "foo", "kind": "def", "line": 1, "children": []}]
        result = _format_symbols("file.py", symbols)
        assert result == "file.py:\n  def foo"

    def test_class_with_methods(self):
        symbols = [{
            "name": "MyClass",
            "kind": "class",
            "line": 1,
            "children": [
                {"name": "bar", "kind": "def", "line": 2, "children": []},
                {"name": "baz", "kind": "def", "line": 5, "children": []},
            ],
        }]
        result = _format_symbols("file.py", symbols)
        expected = "file.py:\n  class MyClass\n    def bar\n    def baz"
        assert result == expected

    def test_multiple_top_level_symbols(self):
        symbols = [
            {"name": "foo", "kind": "def", "line": 1, "children": []},
            {"name": "bar", "kind": "def", "line": 5, "children": []},
        ]
        result = _format_symbols("utils.py", symbols)
        assert result == "utils.py:\n  def foo\n  def bar"


# ===========================================================================
# extract_symbols (mocked tree-sitter)
# ===========================================================================
class TestExtractSymbols:
    def test_unknown_language_returns_empty(self):
        assert extract_symbols(b"hello", "brainfuck") == []

    def test_returns_empty_when_treesitter_unavailable(self):
        with patch("harness.repo_map._get_parser", None):
            assert extract_symbols(b"def foo(): pass", "python") == []

    @patch("harness.repo_map._get_parser")
    def test_python_function(self, mock_get_parser):
        name_node = MockNode("identifier", b"my_func")
        func_node = MockNode(
            "function_definition",
            children=[name_node],
            start_point=(5, 0),
            fields={"name": name_node},
        )
        root = MockNode("module", children=[func_node])

        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = root
        mock_parser.parse.return_value = mock_tree
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"def my_func(): pass", "python")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "my_func"
        assert symbols[0]["kind"] == "def"
        assert symbols[0]["line"] == 6  # 0-indexed row 5 → display line 6

    @patch("harness.repo_map._get_parser")
    def test_python_class_with_method(self, mock_get_parser):
        class_name = MockNode("identifier", b"Foo")
        method_name = MockNode("identifier", b"bar")
        method_node = MockNode(
            "function_definition",
            children=[method_name],
            start_point=(2, 4),
            fields={"name": method_name},
        )
        body = MockNode("block", children=[method_node])
        class_node = MockNode(
            "class_definition",
            children=[class_name, body],
            start_point=(0, 0),
            fields={"name": class_name},
        )
        root = MockNode("module", children=[class_node])

        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = root
        mock_parser.parse.return_value = mock_tree
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"class Foo:\n  def bar(): pass", "python")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "Foo"
        assert symbols[0]["kind"] == "class"
        assert len(symbols[0]["children"]) == 1
        assert symbols[0]["children"][0]["name"] == "bar"
        assert symbols[0]["children"][0]["kind"] == "def"

    @patch("harness.repo_map._get_parser")
    def test_empty_file_returns_empty(self, mock_get_parser):
        root = MockNode("module", children=[])
        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = root
        mock_parser.parse.return_value = mock_tree
        mock_get_parser.return_value = mock_parser

        assert extract_symbols(b"", "python") == []

    @patch("harness.repo_map._get_parser")
    def test_node_without_name_skipped(self, mock_get_parser):
        """A definition node with no extractable name should be skipped."""
        func_node = MockNode(
            "function_definition",
            children=[],
            start_point=(0, 0),
            fields={},
        )
        root = MockNode("module", children=[func_node])

        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = root
        mock_parser.parse.return_value = mock_tree
        mock_get_parser.return_value = mock_parser

        assert extract_symbols(b"broken", "python") == []


# ===========================================================================
# generate_repo_map (file system + mocked extract_symbols)
# ===========================================================================
class TestGenerateRepoMap:
    def test_single_python_file(self, tmp_path):
        (tmp_path / "hello.py").write_text("def greet(): pass")
        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = [
                {"name": "greet", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(tmp_path))
        assert "hello.py:" in result
        assert "def greet" in result

    def test_skips_non_allowed_extensions(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "hello.py").write_text("def greet(): pass")
        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = [
                {"name": "greet", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(tmp_path))
        assert "readme.txt" not in result
        assert "hello.py" in result
        mock_ext.assert_called_once()

    def test_skips_excluded_directories(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "cached.py").write_text("x = 1")
        (tmp_path / "hello.py").write_text("def greet(): pass")
        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = [
                {"name": "greet", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(tmp_path))
        assert "__pycache__" not in result
        assert "hello.py" in result

    def test_empty_directory_returns_empty(self, tmp_path):
        result = generate_repo_map(str(tmp_path))
        assert result == ""

    def test_files_with_no_symbols_omitted(self, tmp_path):
        (tmp_path / "empty.py").write_text("")
        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = []
            result = generate_repo_map(str(tmp_path))
        assert result == ""

    def test_skips_oversized_files(self, tmp_path):
        big = tmp_path / "big.py"
        big.write_bytes(b"x" * (_MAX_INDEX_FILE_SIZE + 1))
        (tmp_path / "small.py").write_text("def f(): pass")
        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = [
                {"name": "f", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(tmp_path))
        assert "big.py" not in result
        assert "small.py" in result

    def test_relative_paths_in_output(self, tmp_path):
        sub = tmp_path / "harness"
        sub.mkdir()
        (sub / "code_llm.py").write_text("def chat(): pass")
        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = [
                {"name": "chat", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(tmp_path))
        # Path should be relative, not absolute.
        assert str(tmp_path) not in result
        assert "code_llm.py" in result

    def test_custom_exclude_dirs(self, tmp_path):
        gen = tmp_path / "generated"
        gen.mkdir()
        (gen / "auto.py").write_text("x = 1")
        (tmp_path / "real.py").write_text("def f(): pass")
        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = [
                {"name": "f", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(tmp_path), exclude_dirs={"generated"})
        assert "auto.py" not in result
        assert "real.py" in result

    def test_truncation_when_map_exceeds_budget(self, tmp_path):
        for i in range(20):
            (tmp_path / f"mod_{i:03d}.py").write_text("x = 1")
        with patch("harness.repo_map.extract_symbols") as mock_ext, \
             patch("harness.repo_map._MAX_MAP_CHARS", 80):
            mock_ext.return_value = [
                {"name": "func", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(tmp_path))
        assert "more files)" in result

    def test_symlink_escaping_project_root_skipped(self, tmp_path):
        """Files symlinked from outside the project root must be skipped."""
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.py"
        secret.write_text("def leak(): pass")

        project = tmp_path / "project"
        project.mkdir()
        link = project / "evil.py"
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip("symlinks not supported on this platform/config")

        with patch("harness.repo_map.extract_symbols") as mock_ext:
            mock_ext.return_value = [
                {"name": "leak", "kind": "def", "line": 1, "children": []},
            ]
            result = generate_repo_map(str(project))

        assert "evil.py" not in result
        assert "secret.py" not in result


# ===========================================================================
# extract_symbols — non-Python languages (mocked tree-sitter)
# ===========================================================================
class TestExtractSymbolsNonPython:
    """Cover _SYMBOL_NODE_TYPES dispatch for JS/TS/Go/Rust/Java/C/C++."""

    @patch("harness.repo_map._get_parser")
    def test_javascript_function(self, mock_get_parser):
        name_node = MockNode("identifier", b"handleClick")
        func_node = MockNode(
            "function_declaration",
            children=[name_node],
            start_point=(0, 0),
            fields={"name": name_node},
        )
        root = MockNode("program", children=[func_node])
        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock(root_node=root)
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"function handleClick() {}", "javascript")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "handleClick"
        assert symbols[0]["kind"] == "function"

    @patch("harness.repo_map._get_parser")
    def test_typescript_interface(self, mock_get_parser):
        name_node = MockNode("type_identifier", b"IProps")
        iface_node = MockNode(
            "interface_declaration",
            children=[name_node],
            start_point=(0, 0),
            fields={"name": name_node},
        )
        root = MockNode("program", children=[iface_node])
        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock(root_node=root)
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"interface IProps {}", "typescript")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "IProps"
        assert symbols[0]["kind"] == "interface"

    @patch("harness.repo_map._get_parser")
    def test_go_function(self, mock_get_parser):
        name_node = MockNode("identifier", b"main")
        func_node = MockNode(
            "function_declaration",
            children=[name_node],
            start_point=(2, 0),
            fields={"name": name_node},
        )
        root = MockNode("source_file", children=[func_node])
        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock(root_node=root)
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"func main() {}", "go")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "main"
        assert symbols[0]["kind"] == "func"

    @patch("harness.repo_map._get_parser")
    def test_rust_struct(self, mock_get_parser):
        name_node = MockNode("type_identifier", b"Config")
        struct_node = MockNode(
            "struct_item",
            children=[name_node],
            start_point=(0, 0),
            fields={"name": name_node},
        )
        root = MockNode("source_file", children=[struct_node])
        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock(root_node=root)
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"struct Config {}", "rust")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "Config"
        assert symbols[0]["kind"] == "struct"

    @patch("harness.repo_map._get_parser")
    def test_java_class_with_method(self, mock_get_parser):
        class_name = MockNode("identifier", b"App")
        method_name = MockNode("identifier", b"run")
        method_node = MockNode(
            "method_declaration",
            children=[method_name],
            start_point=(1, 4),
            fields={"name": method_name},
        )
        body = MockNode("class_body", children=[method_node])
        class_node = MockNode(
            "class_declaration",
            children=[class_name, body],
            start_point=(0, 0),
            fields={"name": class_name},
        )
        root = MockNode("program", children=[class_node])
        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock(root_node=root)
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"class App { void run() {} }", "java")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "App"
        assert symbols[0]["kind"] == "class"
        assert len(symbols[0]["children"]) == 1
        assert symbols[0]["children"][0]["name"] == "run"

    @patch("harness.repo_map._get_parser")
    def test_c_function_with_declarator(self, mock_get_parser):
        decl_id = MockNode("identifier", b"init")
        declarator = MockNode(
            "function_declarator",
            children=[decl_id],
            fields={"declarator": decl_id},
        )
        func_node = MockNode(
            "function_definition",
            children=[declarator],
            start_point=(0, 0),
            fields={"declarator": declarator},
        )
        root = MockNode("translation_unit", children=[func_node])
        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock(root_node=root)
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"void init() {}", "c")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "init"
        assert symbols[0]["kind"] == "function"

    @patch("harness.repo_map._get_parser")
    def test_cpp_class(self, mock_get_parser):
        name_node = MockNode("type_identifier", b"Widget")
        class_node = MockNode(
            "class_specifier",
            children=[name_node],
            start_point=(0, 0),
            fields={"name": name_node},
        )
        root = MockNode("translation_unit", children=[class_node])
        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock(root_node=root)
        mock_get_parser.return_value = mock_parser

        symbols = extract_symbols(b"class Widget {};", "cpp")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "Widget"
        assert symbols[0]["kind"] == "class"


# ===========================================================================
# Coordinator integration
# ===========================================================================
@pytest.mark.ui
class TestCoordinatorRepoMap:
    @patch("harness.coordinator.VoiceInput")
    def test_refresh_populates_repo_map(self, MockVI, tmp_path, qapp):
        from harness.coordinator import Coordinator
        MockVI.return_value = MagicMock()

        coord = Coordinator(project_root=str(tmp_path))
        with patch("harness.coordinator.repo_map_mod.generate_repo_map") as mock_gen:
            mock_gen.return_value = "hello.py:\n  def greet"
            coord.refresh_repo_map()

        assert coord._repo_map == "hello.py:\n  def greet"
        coord._stop_event.set()

    @patch("harness.coordinator.VoiceInput")
    def test_refresh_handles_no_project_root(self, MockVI, qapp):
        from harness.coordinator import Coordinator
        MockVI.return_value = MagicMock()

        coord = Coordinator(project_root=None)
        coord.refresh_repo_map()
        assert coord._repo_map is None
        coord._stop_event.set()

    @patch("harness.coordinator.VoiceInput")
    def test_refresh_handles_generation_error(self, MockVI, tmp_path, qapp):
        from harness.coordinator import Coordinator
        MockVI.return_value = MagicMock()

        coord = Coordinator(project_root=str(tmp_path))
        with patch("harness.coordinator.repo_map_mod.generate_repo_map") as mock_gen:
            mock_gen.side_effect = RuntimeError("parse error")
            coord.refresh_repo_map()

        assert coord._repo_map is None
        coord._stop_event.set()

    @patch("harness.coordinator.VoiceInput")
    def test_pipeline_loop_calls_refresh(self, MockVI, tmp_path, qapp):
        from harness.coordinator import Coordinator
        MockVI.return_value = MagicMock()

        coord = Coordinator(project_root=str(tmp_path))
        coord._stop_event.set()  # Make loop exit immediately.
        coord._queue.put(None)   # Sentinel to unblock get().

        with patch.object(coord, "refresh_repo_map") as mock_refresh:
            coord._pipeline_loop()

        mock_refresh.assert_called_once()
        coord._stop_event.set()

    @patch("harness.coordinator.VoiceInput")
    def test_repo_map_propagates_into_enqueued_message(self, MockVI, qapp):
        """A populated _repo_map must appear in messages from _enqueue()."""
        from harness.coordinator import Coordinator
        MockVI.return_value = MagicMock()

        coord = Coordinator(project_root="/fake")
        coord._repo_map = "app.py:\n  def main"
        coord._enqueue("do something")

        msg = coord._queue.get_nowait()
        assert msg["repo_map"] == "app.py:\n  def main"
        coord._stop_event.set()
