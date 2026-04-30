"""Session-start environment preflight checks (Phase H5.2).

Pure-function checkers that surface drift between the local environment
and the pinned constraints in ``AGENTS.md``. The CLI entry point lives
at ``scripts/preflight.py``; tests import the individual ``check_*``
functions from this module and feed them fakes.

Each checker returns a :class:`PreflightResult`:
- ``ok`` — boolean pass/fail
- ``label`` — short human-readable name
- ``detail`` — observed value or remediation hint
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


REQUIRED_PYTHON = (3, 11)
REQUIRED_CTRANSLATE2 = "4.4.0"
REQUIRED_TOOLS = ("espeak-ng", "nvcc")


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    label: str
    detail: str


# --- individual checkers --------------------------------------------------

def check_python_version(version_info: tuple = sys.version_info) -> PreflightResult:
    major, minor = version_info[0], version_info[1]
    detail = f"{major}.{minor}.{version_info[2]}"
    ok = (major, minor) == REQUIRED_PYTHON
    return PreflightResult(ok, "Python 3.11.x", detail)


def check_ctranslate2(
    importer: Optional[Callable[[str], object]] = None,
) -> PreflightResult:
    label = f"ctranslate2 == {REQUIRED_CTRANSLATE2}"
    try:
        if importer is None:
            import importlib

            mod = importlib.import_module("ctranslate2")
        else:
            mod = importer("ctranslate2")
    except ImportError as exc:
        return PreflightResult(False, label, f"not installed ({exc})")

    version = getattr(mod, "__version__", "unknown")
    ok = version == REQUIRED_CTRANSLATE2
    return PreflightResult(ok, label, str(version))


def check_tool_on_path(
    name: str,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> PreflightResult:
    location = which(name)
    if location is None:
        return PreflightResult(False, f"{name} on PATH", "not found")
    return PreflightResult(True, f"{name} on PATH", location)


def check_active_venv(prefix: str = sys.prefix, base_prefix: str = sys.base_prefix) -> PreflightResult:
    in_venv = prefix != base_prefix
    detail = prefix if in_venv else "system interpreter (no venv active)"
    return PreflightResult(in_venv, "active venv", detail)


def check_last_commit(
    repo_root: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> PreflightResult:
    try:
        result = runner(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return PreflightResult(False, "last commit", "git not found on PATH")

    if result.returncode != 0:
        return PreflightResult(False, "last commit", "not a git repo")

    sha = (result.stdout or "").strip()
    return PreflightResult(bool(sha), "last commit", sha or "no commits")


def check_pytest_collect(
    repo_root: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> PreflightResult:
    """Count tests via ``pytest --collect-only -q``.

    A successful collection (returncode 0) with at least one test counts
    as a pass; collection errors are surfaced verbatim.
    """
    try:
        result = runner(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return PreflightResult(False, "pytest collect", str(exc))

    output = (result.stdout or "") + (result.stderr or "")
    count = _parse_collected_count(output)
    if result.returncode != 0:
        return PreflightResult(False, "pytest collect", f"exit {result.returncode}")
    if count is None:
        return PreflightResult(False, "pytest collect", "could not parse count")
    return PreflightResult(count > 0, "pytest collect", f"{count} tests")


def _parse_collected_count(output: str) -> Optional[int]:
    # Matches "42 tests collected" / "1 test collected" produced by `-q`.
    match = re.search(r"(\d+)\s+tests?\s+collected", output)
    if match:
        return int(match.group(1))
    # Fall-back: count node-id lines like ``tests/test_x.py::test_y``.
    nodes = [line for line in output.splitlines() if "::" in line]
    return len(nodes) if nodes else None


# --- aggregate ------------------------------------------------------------

def run_all(repo_root: Path) -> List[PreflightResult]:
    results: List[PreflightResult] = [
        check_python_version(),
        check_active_venv(),
        check_ctranslate2(),
    ]
    for tool in REQUIRED_TOOLS:
        results.append(check_tool_on_path(tool))
    results.append(check_last_commit(repo_root))
    results.append(check_pytest_collect(repo_root))
    return results


def format_results(results: List[PreflightResult]) -> str:
    lines = []
    for r in results:
        marker = "OK  " if r.ok else "FAIL"
        lines.append(f"[{marker}] {r.label}: {r.detail}")
    return "\n".join(lines)
