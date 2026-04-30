"""Voice Harness session-start preflight (Phase H5.2).

Run this at the top of a coding session to surface drift between the
local environment and the pinned constraints in ``AGENTS.md``::

    python scripts/preflight.py

Exit code is ``0`` when every checker passes, ``1`` otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``scripts/lib`` importable without installing the repo as a package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LIB_DIR = _REPO_ROOT / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import preflight as _preflight  # noqa: E402  (path mutated above)


def main() -> int:
    results = _preflight.run_all(_REPO_ROOT)
    print(_preflight.format_results(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
