"""Pre-commit hook entry point (Phase H1.1).

Runs against the staged file set:
1. Secret scan (regex-based; blocks on hit).
2. Forbidden-pattern scan (blocks on hit).
3. File-size limits (blocks on hit, with ``ALLOWLIST`` for grandfathered files).
4. Pytest (skipped when ``.test-passed`` matches the current signature).
5. Drift warning when ``harness/*.py`` is staged without ``docs/PROGRESS.md``.

Run via ``.git/hooks/pre-commit`` after ``python scripts/install_hooks.py``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB_DIR))

import check_secrets  # noqa: E402
import check_forbidden  # noqa: E402
import check_file_sizes  # noqa: E402
import test_cache  # noqa: E402
import validate_docs  # noqa: E402


def _staged_files() -> list[Path]:
    """Return paths staged for commit (Added, Copied, Modified, Renamed)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def _run_pytest_if_needed() -> int:
    if test_cache.is_cache_valid(REPO_ROOT):
        print("[pre-commit] tests: skipped (cache hit on .test-passed)")
        return 0
    print("[pre-commit] tests: running pytest...")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=REPO_ROOT,
    )
    if proc.returncode == 0:
        test_cache.mark_cache_valid(REPO_ROOT)
    return proc.returncode


def _drift_warning(staged: list[Path]) -> None:
    msg = validate_docs.drift_warning(staged)
    if msg:
        print(f"[pre-commit] WARNING: {msg}")


def main() -> int:
    staged = _staged_files()
    if not staged:
        print("[pre-commit] no staged files; skipping checks")
        return 0

    findings = []
    findings += check_secrets.scan_paths(staged, REPO_ROOT)
    findings += check_forbidden.scan_paths(staged, REPO_ROOT)
    findings += check_file_sizes.check_paths(staged, REPO_ROOT)

    if findings:
        print("[pre-commit] BLOCKED — the following violations were found:")
        for f in findings:
            print(f"  {f.format()}")
        print(
            "\nResolve the violations above and try again, or add a "
            "`# pragma: allowlist secret` / `# pragma: allow forbidden` "
            "marker on intentional examples."
        )
        return 1

    rc = _run_pytest_if_needed()
    if rc != 0:
        print("[pre-commit] BLOCKED — pytest failed.")
        return rc

    _drift_warning(staged)
    print("[pre-commit] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
