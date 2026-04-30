"""File-size limit check (Phase H1).

Per-directory line caps with a small ``ALLOWLIST`` to grandfather
existing oversize files until they are split.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from _finding import Finding


# Top-level directory → max line count. Files outside these prefixes
# are not checked.
LIMITS: dict[str, int] = {
    "harness": 400,
    "ui": 400,
    "tools": 400,
    "scripts": 400,
    "setup": 400,
    "phase0_poc": 400,
    "tests": 600,
}

# Files known to exceed their limit at Phase H1 cut-over.
# Removing entries here is the trigger to split a module.
ALLOWLIST: frozenset[str] = frozenset({
    "harness/coordinator.py",
    "harness/voice_input.py",
    "ui/ai_panel.py",
    "ui/main_window.py",
    "tests/test_code_llm.py",
    "tests/test_coordinator.py",
})


def _limit_for(rel_path: str) -> int | None:
    parts = rel_path.replace("\\", "/").split("/", 1)
    if len(parts) < 2:
        return None
    return LIMITS.get(parts[0])


def check_paths(paths: Iterable[Path], repo_root: Path) -> List[Finding]:
    """Return findings for any path exceeding its directory's line limit."""
    findings: List[Finding] = []
    for rel in paths:
        rel_str = str(rel).replace("\\", "/")
        if rel_str in ALLOWLIST:
            continue
        if not rel_str.endswith(".py"):
            continue
        limit = _limit_for(rel_str)
        if limit is None:
            continue
        full = repo_root / rel
        if not full.is_file():
            continue
        try:
            line_count = sum(1 for _ in full.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if line_count > limit:
            findings.append(
                Finding(
                    path=rel_str,
                    line=line_count,
                    message=(
                        f"file has {line_count} lines, exceeds {limit}-line "
                        f"limit for {rel_str.split('/', 1)[0]}/"
                    ),
                )
            )
    return findings
