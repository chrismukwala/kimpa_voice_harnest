"""Install Voice Harness git hooks (Phase H1).

Writes ``.git/hooks/pre-commit`` and ``.git/hooks/pre-push`` shell
wrappers that delegate to the Python scripts in ``scripts/hooks/``.

The wrappers are POSIX shell because Git for Windows ships ``sh.exe``;
the same files work on Linux/macOS without modification.

Usage::

    python scripts/install_hooks.py

Re-running is idempotent: existing hook files are overwritten with the
current wrapper content.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

PRE_COMMIT_WRAPPER = """#!/bin/sh
# Voice Harness pre-commit hook — installed by scripts/install_hooks.py
exec python scripts/hooks/pre_commit.py "$@"
"""

PRE_PUSH_WRAPPER = """#!/bin/sh
# Voice Harness pre-push hook — installed by scripts/install_hooks.py
exec python scripts/hooks/pre_push.py "$@"
"""

HOOKS = {
    "pre-commit": PRE_COMMIT_WRAPPER,
    "pre-push": PRE_PUSH_WRAPPER,
}


def main() -> int:
    hooks_dir = REPO_ROOT / ".git" / "hooks"
    if not hooks_dir.is_dir():
        print(
            f"[install_hooks] ERROR: {hooks_dir} not found. Run from inside "
            "a git repository.",
            file=sys.stderr,
        )
        return 1

    for name, content in HOOKS.items():
        target = hooks_dir / name
        target.write_text(content, encoding="utf-8", newline="\n")
        # chmod +x — harmless on Windows, required on POSIX.
        try:
            mode = target.stat().st_mode
            target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
        print(f"[install_hooks] installed {target.relative_to(REPO_ROOT)}")

    print("[install_hooks] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
