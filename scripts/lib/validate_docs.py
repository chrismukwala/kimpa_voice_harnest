"""Documentation drift detector (Phase H3.2).

Provides a pure ``drift_warning`` helper invoked by the pre-commit hook.
The hook surfaces a warning (never blocks) when ``harness/*.py`` is staged
without a matching update to ``docs/PROGRESS.md``. CI may opt to escalate
this to a hard failure later.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional


def _norm(p: Path) -> str:
    return str(p).replace("\\", "/")


def drift_warning(staged: Iterable[Path]) -> Optional[str]:
    """Return a warning string if ``harness/*.py`` is staged without PROGRESS.md.

    Returns ``None`` when there is no drift to report.
    """
    paths = [_norm(p) for p in staged]
    has_harness = any(p.startswith("harness/") and p.endswith(".py") for p in paths)
    has_progress = any(p == "docs/PROGRESS.md" for p in paths)
    if has_harness and not has_progress:
        return (
            "harness/*.py changed without an update to docs/PROGRESS.md "
            "(warning only)"
        )
    return None
