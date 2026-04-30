"""SHA-based test cache (Phase H1.3).

Skip ``pytest`` when nothing relevant has changed since the last green
run. A relevant change is any modification to a tracked ``.py`` file
under ``harness/``, ``ui/``, ``tests/``, ``tools/``, ``scripts/``,
``setup/``, ``main.py``, or ``pytest.ini``/``conftest.py``.

The cache is local-only — ``.test-passed`` is gitignored.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Iterable


CACHE_FILENAME = ".test-passed"

_TRACKED_PREFIXES = (
    "harness/", "ui/", "tests/", "tools/", "scripts/", "setup/", "phase0_poc/",
)
_TRACKED_FILES = ("main.py", "pytest.ini", "conftest.py", "requirements.txt")


def _list_files(repo_root: Path) -> list[Path]:
    """Walk the working tree (no git required) for cache-relevant files."""
    out: list[Path] = []
    for prefix in _TRACKED_PREFIXES:
        base = repo_root / prefix
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part == "__pycache__" for part in p.parts):
                continue
            out.append(p)
    for name in _TRACKED_FILES:
        p = repo_root / name
        if p.is_file():
            out.append(p)
    return sorted(out)


def compute_signature(repo_root: Path) -> str:
    """Hash of (relative path, sha256-of-content) tuples for tracked files."""
    h = hashlib.sha256()
    for p in _list_files(repo_root):
        rel = p.relative_to(repo_root).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
        h.update(b"\0\0")
    return h.hexdigest()


def cache_path(repo_root: Path) -> Path:
    return repo_root / CACHE_FILENAME


def is_cache_valid(repo_root: Path) -> bool:
    p = cache_path(repo_root)
    if not p.is_file():
        return False
    try:
        stored = p.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return stored == compute_signature(repo_root)


def mark_cache_valid(repo_root: Path) -> None:
    cache_path(repo_root).write_text(compute_signature(repo_root), encoding="utf-8")
