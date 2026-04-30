"""Repository hygiene gates (Phase H4).

Encodes the "complexity red flags" from the harness-engineering field
guide as automated checks. Runs as part of the normal pytest suite so
every developer (and CI) catches drift.

Gates:
- Function length ≤ 60 lines (in ``harness/`` and ``ui/``).
- Top-level imports per module ≤ 15 (in ``harness/`` and ``ui/``).
- No ``print(`` calls in ``harness/`` or ``ui/`` (use logging instead).

Existing violations are grandfathered in ``LONG_FUNCTION_ALLOWLIST``.
New violations must either be fixed or explicitly added to the
allowlist with a code-review note.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, List, Tuple

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCOPED_DIRS: Tuple[str, ...] = ("harness", "ui")

MAX_FUNCTION_LINES = 60
MAX_TOPLEVEL_IMPORTS = 15

# (relative_path, qualified_function_name) pairs that are grandfathered
# in. New entries require a paired refactor ticket; do not add silently.
LONG_FUNCTION_ALLOWLIST: frozenset[Tuple[str, str]] = frozenset({
    ("harness/code_llm.py", "chat_with_tools"),
    ("harness/coordinator.py", "Coordinator._process_message"),
    ("harness/repo_map.py", "generate_repo_map"),
    ("harness/voice_input.py", "VoiceInput._listen_loop"),
    ("ui/ai_panel.py", "AiPanel.__init__"),
    ("ui/editor_panel.py", "_get_monaco_html"),
    ("ui/main_window.py", "MainWindow.__init__"),
})


def _iter_scoped_files() -> Iterable[Path]:
    for d in SCOPED_DIRS:
        root = REPO_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            yield p


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _qualname(stack: List[str], node: ast.AST) -> str:
    name = getattr(node, "name", "?")
    return ".".join(stack + [name])


def _walk_functions(tree: ast.AST) -> Iterable[Tuple[str, int, int]]:
    """Yield ``(qualname, start_line, end_line)`` for every function."""
    stack: List[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            stack.append(node.name)
            for child in node.body:
                visit(child)
            stack.pop()
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield_data.append((
                _qualname(stack, node),
                node.lineno,
                node.end_lineno or node.lineno,
            ))
            stack.append(node.name)
            for child in node.body:
                visit(child)
            stack.pop()
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    yield_data: List[Tuple[str, int, int]] = []
    visit(tree)
    return yield_data


def _toplevel_import_count(tree: ast.Module) -> int:
    return sum(1 for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)))


def _print_call_lines(tree: ast.AST) -> List[int]:
    lines: List[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "print":
                lines.append(node.lineno)
    return lines


@pytest.fixture(scope="module")
def parsed_files() -> List[Tuple[Path, ast.Module]]:
    out: List[Tuple[Path, ast.Module]] = []
    for path in _iter_scoped_files():
        text = path.read_text(encoding="utf-8")
        out.append((path, ast.parse(text, filename=str(path))))
    assert out, "no source files found in harness/ or ui/"
    return out


def test_function_length_within_limit(parsed_files):
    violations: List[str] = []
    for path, tree in parsed_files:
        rel = _rel(path)
        for qname, start, end in _walk_functions(tree):
            length = end - start + 1
            if length <= MAX_FUNCTION_LINES:
                continue
            if (rel, qname) in LONG_FUNCTION_ALLOWLIST:
                continue
            violations.append(
                f"{rel}::{qname} is {length} lines (limit {MAX_FUNCTION_LINES})"
            )
    assert not violations, "function length violations:\n  " + "\n  ".join(violations)


def test_long_function_allowlist_is_accurate(parsed_files):
    """Every entry in the allowlist must point at a real long function."""
    actual: set[Tuple[str, str]] = set()
    for path, tree in parsed_files:
        rel = _rel(path)
        for qname, start, end in _walk_functions(tree):
            if (end - start + 1) > MAX_FUNCTION_LINES:
                actual.add((rel, qname))
    stale = LONG_FUNCTION_ALLOWLIST - actual
    assert not stale, (
        "stale entries in LONG_FUNCTION_ALLOWLIST (function no longer over limit "
        f"or was renamed): {sorted(stale)}"
    )


def test_toplevel_imports_within_limit(parsed_files):
    violations: List[str] = []
    for path, tree in parsed_files:
        n = _toplevel_import_count(tree)
        if n > MAX_TOPLEVEL_IMPORTS:
            violations.append(
                f"{_rel(path)} has {n} top-level imports (limit {MAX_TOPLEVEL_IMPORTS})"
            )
    assert not violations, "import-count violations:\n  " + "\n  ".join(violations)


def test_no_print_calls_in_scoped_dirs(parsed_files):
    violations: List[str] = []
    for path, tree in parsed_files:
        for line in _print_call_lines(tree):
            violations.append(f"{_rel(path)}:{line} — use logging instead of print()")
    assert not violations, "print() forbidden in harness/ and ui/:\n  " + "\n  ".join(violations)
