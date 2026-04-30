"""Tests for git-hook check libraries (Phase H1).

Covers the pure-function check libraries under ``scripts/lib/``:
secret detection, file-size limits, forbidden patterns. Hook entry
points (``scripts/hooks/*.py``) are integration glue and are smoke-tested
manually; this file keeps the tests fast and importable.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# Make ``scripts/lib`` importable as ``check_secrets``, ``check_forbidden``,
# ``check_file_sizes`` without polluting the project package layout.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LIB_DIR = _REPO_ROOT / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


# --- check_secrets ---------------------------------------------------------

class TestCheckSecrets:
    def test_flags_openai_style_key(self):
        import check_secrets

        text = 'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789"\n'
        findings = check_secrets.scan_text("config.py", text)
        assert findings, "expected an OpenAI-style key to be flagged"
        assert findings[0].path == "config.py"
        assert findings[0].line == 1

    def test_flags_gemini_style_key(self):
        import check_secrets

        text = 'GEMINI_KEY = "AIzaSyA-1234567890abcdefghijklmnopqrstuvw"\n'
        findings = check_secrets.scan_text("env.py", text)
        assert findings, "expected a Gemini AIza... key to be flagged"

    def test_flags_private_key_block(self):
        import check_secrets

        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n"
        findings = check_secrets.scan_text("id_rsa", text)
        assert findings

    def test_pragma_allowlist_suppresses(self):
        import check_secrets

        text = (
            'EXAMPLE = "sk-abcdefghijklmnopqrstuvwxyz0123456789"  '
            "# pragma: allowlist secret\n"
        )
        findings = check_secrets.scan_text("docs.py", text)
        assert findings == [], "expected pragma allowlist to suppress finding"

    def test_clean_text_passes(self):
        import check_secrets

        text = "def hello():\n    return 'world'\n"
        assert check_secrets.scan_text("ok.py", text) == []


# --- check_file_sizes ------------------------------------------------------

class TestCheckFileSizes:
    def test_flags_oversize_harness_file(self, tmp_path: Path):
        import check_file_sizes

        # harness limit = 400 lines
        big = tmp_path / "harness" / "big.py"
        big.parent.mkdir()
        big.write_text("x = 1\n" * 401, encoding="utf-8")

        findings = check_file_sizes.check_paths(
            [Path("harness/big.py")], repo_root=tmp_path
        )
        assert findings, "401-line harness file should fail"
        assert "400" in findings[0].message

    def test_under_limit_passes(self, tmp_path: Path):
        import check_file_sizes

        small = tmp_path / "harness" / "small.py"
        small.parent.mkdir()
        small.write_text("x = 1\n" * 50, encoding="utf-8")

        findings = check_file_sizes.check_paths(
            [Path("harness/small.py")], repo_root=tmp_path
        )
        assert findings == []

    def test_tests_dir_uses_higher_limit(self, tmp_path: Path):
        import check_file_sizes

        # tests limit = 600 — 500 lines should pass, 601 should fail
        ok = tmp_path / "tests" / "ok.py"
        ok.parent.mkdir()
        ok.write_text("x = 1\n" * 500, encoding="utf-8")

        bad = tmp_path / "tests" / "bad.py"
        bad.write_text("x = 1\n" * 601, encoding="utf-8")

        findings_ok = check_file_sizes.check_paths(
            [Path("tests/ok.py")], repo_root=tmp_path
        )
        findings_bad = check_file_sizes.check_paths(
            [Path("tests/bad.py")], repo_root=tmp_path
        )
        assert findings_ok == []
        assert findings_bad

    def test_allowlist_grandfathers_existing_violations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import check_file_sizes

        big = tmp_path / "harness" / "coordinator.py"
        big.parent.mkdir()
        big.write_text("x = 1\n" * 700, encoding="utf-8")

        # The module ships an ALLOWLIST of known oversize files —
        # ensure ``harness/coordinator.py`` is in it.
        assert "harness/coordinator.py" in check_file_sizes.ALLOWLIST

        findings = check_file_sizes.check_paths(
            [Path("harness/coordinator.py")], repo_root=tmp_path
        )
        assert findings == [], "allowlisted file should not be flagged"


# --- check_forbidden -------------------------------------------------------

class TestCheckForbidden:
    def test_flags_bare_except(self):
        import check_forbidden

        text = textwrap.dedent(
            """
            def f():
                try:
                    g()
                except:
                    pass
            """
        ).lstrip()
        findings = check_forbidden.scan_text("harness/x.py", text)
        assert any("bare except" in f.message.lower() for f in findings)

    def test_flags_float16_compute_type(self):
        import check_forbidden

        text = 'WhisperModel("base", compute_type="float16")\n'
        findings = check_forbidden.scan_text("harness/voice_input.py", text)
        assert any("float16" in f.message.lower() for f in findings)

    def test_int8_float16_is_allowed(self):
        import check_forbidden

        text = 'WhisperModel("base", compute_type="int8_float16")\n'
        findings = check_forbidden.scan_text("harness/voice_input.py", text)
        assert not any("float16" in f.message.lower() for f in findings)

    def test_flags_file_url_in_ui(self):
        import check_forbidden

        text = 'view.setUrl(QUrl("file:///C:/monaco/index.html"))\n'
        findings = check_forbidden.scan_text("ui/main_window.py", text)
        assert any("file://" in f.message.lower() or "monaco" in f.message.lower()
                   for f in findings)

    def test_flags_git_add_dot(self):
        import check_forbidden

        text = "Run `git add .` to stage everything.\n"
        findings = check_forbidden.scan_text("docs/CONTRIBUTING.md", text)
        assert any("git add" in f.message.lower() for f in findings)

    def test_clean_code_passes(self):
        import check_forbidden

        text = 'def f():\n    try:\n        g()\n    except ValueError:\n        pass\n'
        findings = check_forbidden.scan_text("harness/x.py", text)
        assert findings == []

    def test_flags_print_in_harness(self):
        import check_forbidden

        text = 'def f():\n    print("hello")\n'
        findings = check_forbidden.scan_text("harness/voice_input.py", text)
        assert any("print()" in f.message for f in findings)

    def test_flags_print_in_ui(self):
        import check_forbidden

        text = '    print("oops")\n'
        findings = check_forbidden.scan_text("ui/main_window.py", text)
        assert any("print()" in f.message for f in findings)

    def test_print_allowed_in_tools(self):
        import check_forbidden

        text = 'print("diagnostic")\n'
        findings = check_forbidden.scan_text("tools/test_audio.py", text)
        assert not any("print()" in f.message for f in findings)

    def test_print_allowed_in_scripts(self):
        import check_forbidden

        text = 'print("installing")\n'
        findings = check_forbidden.scan_text("scripts/install_hooks.py", text)
        assert not any("print()" in f.message for f in findings)
