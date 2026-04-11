"""Tests for ui/editor_panel.py — EditorPanel widget."""

import pytest

from ui.editor_panel import EditorPanel, _detect_language


@pytest.mark.ui
class TestEditorPanel:
    """Verify EditorPanel's public API."""

    def test_initial_path(self, qapp):
        panel = EditorPanel()
        assert panel.path == "No file open"

    def test_set_file(self, qapp):
        panel = EditorPanel()
        panel.set_file("/some/file.py", "print('hello')")

        assert panel.path == "/some/file.py"
        assert panel.get_content() == "print('hello')"

    def test_get_content_empty(self, qapp):
        panel = EditorPanel()
        assert panel.get_content() == ""

    def test_set_file_overwrites_previous(self, qapp):
        panel = EditorPanel()
        panel.set_file("/a.py", "first")
        panel.set_file("/b.py", "second")

        assert panel.path == "/b.py"
        assert panel.get_content() == "second"

    def test_content_changed_signal_exists(self, qapp):
        panel = EditorPanel()
        # Signal must exist and be connectable.
        received = []
        panel.content_changed.connect(lambda: received.append(True))

    def test_set_file_deferred_before_ready(self, qapp):
        """set_file before Monaco loads should still cache content."""
        panel = EditorPanel()
        panel.set_file("/x.py", "cached = True")
        assert panel.get_content() == "cached = True"

    def test_shutdown_stops_server(self, qapp):
        """shutdown() should stop the HTTP server cleanly."""
        panel = EditorPanel()
        assert panel._server is not None
        panel.shutdown()
        assert panel._server is None

    def test_shutdown_idempotent(self, qapp):
        """Calling shutdown() twice should not raise."""
        panel = EditorPanel()
        panel.shutdown()
        panel.shutdown()  # should not raise


class TestLanguageDetection:
    """Verify file extension → Monaco language ID mapping."""

    def test_python(self):
        assert _detect_language("/foo/bar.py") == "python"

    def test_javascript(self):
        assert _detect_language("app.js") == "javascript"

    def test_typescript(self):
        assert _detect_language("component.tsx") == "typescript"

    def test_rust(self):
        assert _detect_language("main.rs") == "rust"

    def test_go(self):
        assert _detect_language("handler.go") == "go"

    def test_json(self):
        assert _detect_language("package.json") == "json"

    def test_markdown(self):
        assert _detect_language("README.md") == "markdown"

    def test_yaml(self):
        assert _detect_language("config.yml") == "yaml"

    def test_html(self):
        assert _detect_language("index.html") == "html"

    def test_css(self):
        assert _detect_language("style.css") == "css"

    def test_unknown_defaults_to_plaintext(self):
        assert _detect_language("Makefile") == "plaintext"

    def test_case_insensitive(self):
        assert _detect_language("Script.PY") == "python"
