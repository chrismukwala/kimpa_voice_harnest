"""Editor panel — Monaco Editor via QWebEngineView + QWebChannel (Phase 2b).

Serves Monaco assets from a localhost HTTP server (daemon thread).
Python-JS bridge via QWebChannel for bidirectional content sync.
Maintains a Python-side cache so get_content() is synchronous.
"""

import json
import os
import pathlib
import functools
import socket
import threading
import http.server
import logging

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ASSETS_ROOT = pathlib.Path(__file__).parent.parent / "assets" / "monaco"

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------
_LANG_MAP = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "cpp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".java": "java",
    ".rb": "ruby",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".bat": "bat",
    ".ps1": "powershell",
    ".sql": "sql",
    ".r": "r",
    ".lua": "lua",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".vb": "vb",
    ".dart": "dart",
    ".toml": "ini",
    ".ini": "ini",
    ".cfg": "ini",
    ".dockerfile": "dockerfile",
    ".graphql": "graphql",
    ".gql": "graphql",
}


def _detect_language(path: str) -> str:
    """Map a file path to a Monaco language ID based on extension."""
    basename = os.path.basename(path).lower()
    if basename == "dockerfile":
        return "dockerfile"
    ext = os.path.splitext(path)[1].lower()
    return _LANG_MAP.get(ext, "plaintext")


# ---------------------------------------------------------------------------
# Localhost asset server
# ---------------------------------------------------------------------------
def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that suppresses request logs."""

    def log_message(self, format, *args):
        pass


def _start_asset_server(port: int) -> http.server.HTTPServer:
    handler = functools.partial(_SilentHandler, directory=str(_ASSETS_ROOT))
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="monaco-assets")
    thread.start()
    return server


# ---------------------------------------------------------------------------
# QWebChannel bridge
# ---------------------------------------------------------------------------
class _EditorBridge(QObject):
    """JS -> Python bridge for Monaco editor events."""

    editor_ready = pyqtSignal()
    content_changed_sig = pyqtSignal(str)

    @pyqtSlot()
    def onEditorReady(self):
        self.editor_ready.emit()

    @pyqtSlot(str)
    def onContentChanged(self, content: str):
        self.content_changed_sig.emit(content)


# ---------------------------------------------------------------------------
# Debug page (captures JS console -> Python log)
# ---------------------------------------------------------------------------
class _DebugPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        log.debug("[Monaco JS] %s (line %s)", message, line)


# ---------------------------------------------------------------------------
# Monaco HTML
# ---------------------------------------------------------------------------
def _get_monaco_html(port: int) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 100%; height: 100%; background: #1e1e1e; overflow: hidden; }}
  #editor {{ width: 100%; height: 100%; }}
</style>
</head>
<body>
<div id="editor"></div>

<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="http://localhost:{port}/min/vs/loader.js"></script>
<script>
  var _editor = null;
  var _bridge = null;
  var _suppressChange = false;

  function initApp(qt) {{
    new QWebChannel(qt.webChannelTransport, function(channel) {{
      _bridge = channel.objects.bridge;

      require.config({{ paths: {{ vs: 'http://localhost:{port}/min/vs' }} }});
      require(['vs/editor/editor.main'], function() {{
        _editor = monaco.editor.create(document.getElementById('editor'), {{
          value: '',
          language: 'plaintext',
          theme: 'vs-dark',
          fontSize: 14,
          fontFamily: 'Consolas, monospace',
          minimap: {{ enabled: true }},
          automaticLayout: true,
          wordWrap: 'off',
          renderWhitespace: 'selection',
          scrollBeyondLastLine: false,
          lineNumbers: 'on',
          roundedSelection: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
        }});

        _editor.onDidChangeModelContent(function(e) {{
          if (!_suppressChange) {{
            _bridge.onContentChanged(_editor.getValue());
          }}
        }});

        _bridge.onEditorReady();
      }});
    }});
  }}

  // Poll for qt.webChannelTransport
  var _attempts = 0;
  var _poll = setInterval(function() {{
    _attempts++;
    if (typeof qt !== 'undefined' && qt.webChannelTransport) {{
      clearInterval(_poll);
      initApp(qt);
    }} else if (_attempts > 200) {{
      clearInterval(_poll);
      console.error('qt.webChannelTransport not available after 10s');
    }}
  }}, 50);

  // API called from Python via runJavaScript
  function setEditorValue(text) {{
    if (_editor) {{
      _suppressChange = true;
      _editor.setValue(text);
      _suppressChange = false;
    }}
  }}

  function setEditorLanguage(langId) {{
    if (_editor) {{
      var model = _editor.getModel();
      if (model) monaco.editor.setModelLanguage(model, langId);
    }}
  }}

  function getEditorValue() {{
    return _editor ? _editor.getValue() : '';
  }}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# EditorPanel widget
# ---------------------------------------------------------------------------
class EditorPanel(QWidget):
    """Monaco-based code editor panel with QWebChannel bridge."""

    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path = None
        self._cached_content = ""
        self._monaco_ready = False
        self._pending_file = None  # (path, content) deferred until Monaco loads

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Path label ---
        self._path_label = QLabel("No file open")
        self._path_label.setStyleSheet(
            "background:#252526; color:#9cdcfe; font-family:Consolas,monospace;"
            " font-size:11px; padding:4px 8px;"
        )
        layout.addWidget(self._path_label)

        # --- HTTP server for Monaco assets ---
        self._port = _find_free_port()
        self._server = _start_asset_server(self._port)

        # --- QWebEngineView ---
        self._view = QWebEngineView()
        page = _DebugPage(self._view.page().profile(), self._view)
        self._view.setPage(page)
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True
        )
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

        # --- QWebChannel bridge ---
        self._bridge = _EditorBridge()
        self._bridge.editor_ready.connect(self._on_monaco_ready)
        self._bridge.content_changed_sig.connect(self._on_content_changed)

        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        # --- Load Monaco HTML ---
        html = _get_monaco_html(self._port)
        self._view.setHtml(html, QUrl(f"http://localhost:{self._port}/"))
        layout.addWidget(self._view)

    # ------------------------------------------------------------------
    # Public API (same contract as Phase 1 QPlainTextEdit version)
    # ------------------------------------------------------------------
    @property
    def path(self) -> str:
        return self._current_path if self._current_path else "No file open"

    def set_file(self, path: str, content: str):
        """Load a file's content into the editor."""
        self._current_path = path
        self._cached_content = content
        self._path_label.setText(path)

        if self._monaco_ready:
            self._push_to_monaco(path, content)
        else:
            self._pending_file = (path, content)

    def get_content(self) -> str:
        """Return the current editor content (from Python-side cache)."""
        return self._cached_content

    # ------------------------------------------------------------------
    # Internal: Monaco communication
    # ------------------------------------------------------------------
    def _push_to_monaco(self, path: str, content: str):
        lang = _detect_language(path)
        js = (
            f"setEditorValue({json.dumps(content)});"
            f" setEditorLanguage({json.dumps(lang)});"
        )
        self._view.page().runJavaScript(js)

    def _on_monaco_ready(self):
        self._monaco_ready = True
        log.info("Monaco editor ready on localhost:%d", self._port)
        if self._pending_file:
            path, content = self._pending_file
            self._pending_file = None
            self._push_to_monaco(path, content)

    def _on_content_changed(self, content: str):
        self._cached_content = content
        self.content_changed.emit()

    def shutdown(self):
        """Stop the localhost HTTP server and release resources."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
