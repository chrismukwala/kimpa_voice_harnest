"""Tests for scripts/lib/preflight.py — session-start env validation (Phase H5.2)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LIB_DIR = _REPO_ROOT / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import preflight  # noqa: E402


# --- check_python_version --------------------------------------------------

class TestCheckPythonVersion:
    def test_passes_on_311(self):
        result = preflight.check_python_version((3, 11, 7, "final", 0))
        assert result.ok is True
        assert "3.11" in result.detail

    def test_fails_on_312(self):
        result = preflight.check_python_version((3, 12, 0, "final", 0))
        assert result.ok is False

    def test_fails_on_310(self):
        result = preflight.check_python_version((3, 10, 14, "final", 0))
        assert result.ok is False


# --- check_ctranslate2 -----------------------------------------------------

class TestCheckCtranslate2:
    def test_passes_on_pinned_version(self):
        fake_mod = SimpleNamespace(__version__="4.4.0")
        result = preflight.check_ctranslate2(importer=lambda _name: fake_mod)
        assert result.ok is True
        assert result.detail == "4.4.0"

    def test_fails_on_newer_version(self):
        fake_mod = SimpleNamespace(__version__="4.5.0")
        result = preflight.check_ctranslate2(importer=lambda _name: fake_mod)
        assert result.ok is False
        assert "4.5.0" in result.detail

    def test_fails_when_not_installed(self):
        def boom(_name):
            raise ImportError("No module named 'ctranslate2'")

        result = preflight.check_ctranslate2(importer=boom)
        assert result.ok is False
        assert "not installed" in result.detail


# --- check_tool_on_path ----------------------------------------------------

class TestCheckToolOnPath:
    def test_passes_when_tool_found(self):
        result = preflight.check_tool_on_path(
            "espeak-ng", which=lambda _n: r"C:\Program Files\eSpeak NG\espeak-ng.exe"
        )
        assert result.ok is True
        assert "espeak-ng" in result.detail

    def test_fails_when_tool_missing(self):
        result = preflight.check_tool_on_path("nvcc", which=lambda _n: None)
        assert result.ok is False
        assert result.detail == "not found"


# --- check_active_venv -----------------------------------------------------

class TestCheckActiveVenv:
    def test_passes_when_venv_active(self):
        result = preflight.check_active_venv(
            prefix=r"C:\repo\.venv-poc", base_prefix=r"C:\Python311"
        )
        assert result.ok is True
        assert ".venv-poc" in result.detail

    def test_fails_when_no_venv(self):
        result = preflight.check_active_venv(
            prefix=r"C:\Python311", base_prefix=r"C:\Python311"
        )
        assert result.ok is False


# --- check_last_commit -----------------------------------------------------

class TestCheckLastCommit:
    def test_returns_short_sha_on_success(self, tmp_path):
        def fake_run(cmd, cwd, capture_output, text, check):
            assert cmd[:2] == ["git", "rev-parse"]
            return subprocess.CompletedProcess(cmd, 0, stdout="abc1234\n", stderr="")

        result = preflight.check_last_commit(tmp_path, runner=fake_run)
        assert result.ok is True
        assert result.detail == "abc1234"

    def test_fails_when_not_a_git_repo(self, tmp_path):
        def fake_run(cmd, cwd, capture_output, text, check):
            return subprocess.CompletedProcess(
                cmd, 128, stdout="", stderr="fatal: not a git repository"
            )

        result = preflight.check_last_commit(tmp_path, runner=fake_run)
        assert result.ok is False
        assert "not a git repo" in result.detail

    def test_fails_when_git_missing(self, tmp_path):
        def fake_run(*_args, **_kwargs):
            raise FileNotFoundError("git")

        result = preflight.check_last_commit(tmp_path, runner=fake_run)
        assert result.ok is False
        assert "git not found" in result.detail


# --- check_pytest_collect --------------------------------------------------

class TestCheckPytestCollect:
    def test_parses_collected_count(self, tmp_path):
        def fake_run(cmd, cwd, capture_output, text, check):
            return subprocess.CompletedProcess(
                cmd, 0, stdout="42 tests collected in 0.30s\n", stderr=""
            )

        result = preflight.check_pytest_collect(tmp_path, runner=fake_run)
        assert result.ok is True
        assert "42 tests" in result.detail

    def test_fails_on_collection_error(self, tmp_path):
        def fake_run(cmd, cwd, capture_output, text, check):
            return subprocess.CompletedProcess(
                cmd, 2, stdout="", stderr="ERROR collecting tests/test_x.py"
            )

        result = preflight.check_pytest_collect(tmp_path, runner=fake_run)
        assert result.ok is False
        assert "exit 2" in result.detail

    def test_handles_singular_test_collected(self, tmp_path):
        def fake_run(cmd, cwd, capture_output, text, check):
            return subprocess.CompletedProcess(
                cmd, 0, stdout="1 test collected\n", stderr=""
            )

        result = preflight.check_pytest_collect(tmp_path, runner=fake_run)
        assert result.ok is True
        assert "1 tests" in result.detail


# --- run_all + format_results ---------------------------------------------

class TestRunAll:
    def test_returns_a_result_per_checker(self, tmp_path):
        results = preflight.run_all(tmp_path)
        # Python + venv + ctranslate2 + each required tool + git + pytest.
        expected_minimum = 3 + len(preflight.REQUIRED_TOOLS) + 2
        assert len(results) >= expected_minimum
        assert all(hasattr(r, "ok") and hasattr(r, "label") for r in results)

    def test_format_results_marks_pass_and_fail(self):
        results = [
            preflight.PreflightResult(True, "thing-a", "v1"),
            preflight.PreflightResult(False, "thing-b", "missing"),
        ]
        text = preflight.format_results(results)
        assert "[OK  ] thing-a: v1" in text
        assert "[FAIL] thing-b: missing" in text


# --- plan template ---------------------------------------------------------

class TestPlanTemplate:
    def test_template_exists_with_required_sections(self):
        path = _REPO_ROOT / "docs" / "plans" / "_TEMPLATE.md"
        assert path.exists(), "Phase H5.1 plan template missing"
        body = path.read_text(encoding="utf-8")
        for section in (
            "Problem statement",
            "Test list",
            "Module touch-list",
            "Risks",
            "Success criteria",
        ):
            assert section in body, f"template missing section: {section}"
