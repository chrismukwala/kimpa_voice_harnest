"""LLM tools — sandboxed file-system + test-running tools the LLM can call.

All paths are validated against *project_root* via edit_applier.validate_path
plus a realpath/commonpath check so the model can never escape the project.

Destructive operations (create_file, delete_file) do NOT touch the disk —
they return a `pending_user_confirmation` envelope so the coordinator can
route them through the existing accept/reject diff UI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

from harness import edit_applier

_MAX_FILE_SIZE = 256 * 1024  # 256 KB cap on tool reads
_MAX_RESULTS = 100


# ----------------------------------------------------------------------
# Path resolution
# ----------------------------------------------------------------------
def _resolve(path: str, project_root: str) -> str:
    """Validate *path* and return an absolute filesystem path inside *project_root*."""
    edit_applier.validate_path(path, project_root)
    full = os.path.realpath(os.path.join(project_root, path))
    real_root = os.path.realpath(project_root)
    try:
        common = os.path.commonpath([full, real_root])
    except ValueError as exc:
        raise ValueError(f"Refusing path outside project: {path}") from exc
    if os.path.normcase(common) != os.path.normcase(real_root):
        raise ValueError(f"Refusing path outside project: {path}")
    return full


# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------
def read_file(path: str, project_root: str) -> str:
    """Return the UTF-8 contents of *path* inside *project_root*."""
    full = _resolve(path, project_root)
    if not os.path.exists(full):
        raise FileNotFoundError(path)
    if not os.path.isfile(full):
        raise ValueError(f"Not a file: {path}")
    if os.path.getsize(full) > _MAX_FILE_SIZE:
        raise ValueError(f"File too large (>256 KB): {path}")
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def list_dir(path: str, project_root: str) -> list[dict]:
    """Return [{name, type}] for entries directly under *path*."""
    full = _resolve(path, project_root)
    if not os.path.isdir(full):
        raise ValueError(f"Not a directory: {path}")
    entries = []
    for name in sorted(os.listdir(full))[:_MAX_RESULTS]:
        entry_path = os.path.join(full, name)
        kind = "dir" if os.path.isdir(entry_path) else "file"
        entries.append({"name": name, "type": kind})
    return entries


def search_text(pattern: str, path: str, project_root: str) -> list[dict]:
    """Plain-text grep across *path* (file or directory).  Returns line hits."""
    full = _resolve(path, project_root)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc
    results: list[dict] = []

    targets: list[str] = []
    if os.path.isfile(full):
        targets.append(full)
    elif os.path.isdir(full):
        for root, dirs, files in os.walk(full):
            # Skip hidden + virtualenv dirs.
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for fname in files:
                targets.append(os.path.join(root, fname))
    else:
        return []

    real_root = os.path.realpath(project_root)
    for target in targets:
        if len(results) >= _MAX_RESULTS:
            break
        try:
            if os.path.getsize(target) > _MAX_FILE_SIZE:
                continue
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, start=1):
                    if regex.search(line):
                        rel = os.path.relpath(target, real_root).replace("\\", "/")
                        results.append({
                            "path": rel,
                            "line": lineno,
                            "text": line.rstrip("\n")[:400],
                        })
                        if len(results) >= _MAX_RESULTS:
                            break
        except OSError:
            continue
    return results


def create_file(path: str, content: str, project_root: str) -> dict:
    """Return a pending creation proposal — the coordinator routes it through accept/reject."""
    _resolve(path, project_root)  # validate only; do not touch disk
    return {
        "status": "pending_user_confirmation",
        "action": "create",
        "path": path,
        "content": content,
    }


def delete_file(path: str, project_root: str) -> dict:
    """Return a pending deletion proposal — destructive ops require user confirm."""
    full = _resolve(path, project_root)
    if not os.path.exists(full):
        raise FileNotFoundError(path)
    return {
        "status": "pending_user_confirmation",
        "action": "delete",
        "path": path,
    }


def run_tests(project_root: str) -> dict:
    """Invoke pytest in *project_root* and return stdout/stderr/returncode."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-2000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": -1, "stdout": "", "stderr": str(exc)}


# ----------------------------------------------------------------------
# Dispatcher + schemas
# ----------------------------------------------------------------------
_TOOLS = {
    "read_file": read_file,
    "list_dir": list_dir,
    "search_text": search_text,
    "create_file": create_file,
    "delete_file": delete_file,
    "run_tests": run_tests,
}


def dispatch(name: str, args: dict, project_root: str) -> str:
    """Run *name* with *args* and return a JSON string for the LLM."""
    if name not in _TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    fn = _TOOLS[name]
    kwargs = dict(args or {})
    kwargs["project_root"] = project_root
    try:
        result = fn(**kwargs)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return json.dumps({"error": str(exc)})
    if isinstance(result, str):
        return result
    return json.dumps(result)


def tool_schemas() -> list[dict]:
    """Return OpenAI-style function-tool schemas."""
    def fn(name, desc, props, required):
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }

    return [
        fn(
            "read_file",
            "Read the UTF-8 contents of a project file.",
            {"path": {"type": "string", "description": "Project-relative path"}},
            ["path"],
        ),
        fn(
            "list_dir",
            "List entries in a project directory.",
            {"path": {"type": "string", "description": "Project-relative directory"}},
            ["path"],
        ),
        fn(
            "search_text",
            "Plain-text/regex search across a file or directory.",
            {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "path": {"type": "string", "description": "File or directory to search"},
            },
            ["pattern", "path"],
        ),
        fn(
            "create_file",
            "Propose creating a new file. The user must approve before it is written.",
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            ["path", "content"],
        ),
        fn(
            "delete_file",
            "Propose deleting a file. The user must approve before it is removed.",
            {"path": {"type": "string"}},
            ["path"],
        ),
        fn(
            "run_tests",
            "Run the project test suite via pytest and return the output.",
            {},
            [],
        ),
    ]
