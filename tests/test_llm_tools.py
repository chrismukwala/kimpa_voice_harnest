"""Tests for harness/llm_tools.py — sandboxed tool dispatcher for the LLM."""

import json
import os
from unittest.mock import patch

import pytest

from harness import llm_tools


@pytest.fixture
def project(tmp_path):
    """Build a small fake project under tmp_path."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# proj\nhello world\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- read_file
class TestReadFile:
    def test_read_file_returns_content(self, project):
        out = llm_tools.read_file("src/main.py", project_root=str(project))
        assert "def hello" in out

    def test_read_file_rejects_traversal(self, project):
        with pytest.raises(ValueError):
            llm_tools.read_file("../escape.py", project_root=str(project))

    def test_read_file_rejects_absolute(self, project):
        with pytest.raises(ValueError):
            llm_tools.read_file("/etc/passwd", project_root=str(project))

    def test_read_file_missing_raises(self, project):
        with pytest.raises(FileNotFoundError):
            llm_tools.read_file("nope.py", project_root=str(project))


# ---------------------------------------------------------------- list_dir
class TestListDir:
    def test_list_dir_lists_entries(self, project):
        entries = llm_tools.list_dir(".", project_root=str(project))
        names = [e["name"] for e in entries]
        assert "src" in names
        assert "README.md" in names

    def test_list_dir_marks_dirs_vs_files(self, project):
        entries = llm_tools.list_dir(".", project_root=str(project))
        kinds = {e["name"]: e["type"] for e in entries}
        assert kinds["src"] == "dir"
        assert kinds["README.md"] == "file"

    def test_list_dir_rejects_traversal(self, project):
        with pytest.raises(ValueError):
            llm_tools.list_dir("..", project_root=str(project))


# ---------------------------------------------------------------- search_text
class TestSearchText:
    def test_search_text_returns_matches(self, project):
        results = llm_tools.search_text("hello", path=".", project_root=str(project))
        # Both files contain "hello"
        files = {r["path"] for r in results}
        assert any("README.md" in f for f in files)
        assert any("main.py" in f for f in files)

    def test_search_text_returns_line_numbers(self, project):
        results = llm_tools.search_text("hello", path="README.md", project_root=str(project))
        assert all("line" in r for r in results)


# ---------------------------------------------------------------- delete/create
class TestDeleteFile:
    def test_delete_file_returns_pending_proposal(self, project):
        result = llm_tools.delete_file("README.md", project_root=str(project))
        assert result["status"] == "pending_user_confirmation"
        # File must NOT actually be deleted by the tool itself.
        assert (project / "README.md").exists()

    def test_delete_file_rejects_traversal(self, project):
        with pytest.raises(ValueError):
            llm_tools.delete_file("../bad.py", project_root=str(project))


class TestCreateFile:
    def test_create_file_returns_pending_proposal(self, project):
        result = llm_tools.create_file("new.py", "print(1)", project_root=str(project))
        assert result["status"] == "pending_user_confirmation"
        assert not (project / "new.py").exists()


# ---------------------------------------------------------------- run_tests
class TestRunTests:
    def test_run_tests_invokes_pytest_and_returns_output(self, project):
        with patch("subprocess.run") as run:
            run.return_value.stdout = "1 passed"
            run.return_value.stderr = ""
            run.return_value.returncode = 0
            result = llm_tools.run_tests(project_root=str(project))
        assert result["returncode"] == 0
        assert "passed" in result["stdout"]


# ---------------------------------------------------------------- dispatcher
class TestDispatcher:
    def test_dispatcher_routes_read_file(self, project):
        out = llm_tools.dispatch(
            "read_file", {"path": "src/main.py"}, project_root=str(project)
        )
        assert "def hello" in out

    def test_dispatcher_unknown_tool_raises(self, project):
        with pytest.raises(ValueError):
            llm_tools.dispatch("steal_secrets", {}, project_root=str(project))

    def test_dispatcher_returns_json_for_complex_results(self, project):
        out = llm_tools.dispatch(
            "list_dir", {"path": "."}, project_root=str(project)
        )
        # dispatcher should return a string (JSON) the LLM can consume
        assert isinstance(out, str)
        parsed = json.loads(out)
        assert any(e["name"] == "src" for e in parsed)


# ---------------------------------------------------------------- schema
class TestSchema:
    def test_tool_schemas_returns_openai_compatible_list(self):
        schemas = llm_tools.tool_schemas()
        assert isinstance(schemas, list)
        names = {s["function"]["name"] for s in schemas}
        assert {"read_file", "list_dir", "search_text",
                "create_file", "delete_file", "run_tests"} <= names

    def test_each_schema_has_parameters(self):
        for s in llm_tools.tool_schemas():
            assert s["type"] == "function"
            assert "parameters" in s["function"]
