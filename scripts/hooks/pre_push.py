"""Pre-push hook entry point (Phase H1.2).

1. Run the full pytest suite (skipped when ``.test-passed`` is current).
2. Run ``pip-audit`` against ``requirements.txt`` (warn-only).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB_DIR))

import test_cache  # noqa: E402


def _run_pytest() -> int:
    if test_cache.is_cache_valid(REPO_ROOT):
        print("[pre-push] tests: skipped (cache hit on .test-passed)")
        return 0
    print("[pre-push] tests: running full pytest suite...")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v"],
        cwd=REPO_ROOT,
    )
    if proc.returncode == 0:
        test_cache.mark_cache_valid(REPO_ROOT)
    return proc.returncode


def _run_pip_audit() -> None:
    if shutil.which("pip-audit") is None:
        print("[pre-push] pip-audit: not installed; skipping (warn only)")
        return
    print("[pre-push] pip-audit: scanning requirements.txt...")
    proc = subprocess.run(
        ["pip-audit", "-r", "requirements.txt"],
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        print("[pre-push] pip-audit reported issues (warn only — not blocking)")


def main() -> int:
    rc = _run_pytest()
    if rc != 0:
        print("[pre-push] BLOCKED — pytest failed.")
        return rc
    _run_pip_audit()
    print("[pre-push] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
