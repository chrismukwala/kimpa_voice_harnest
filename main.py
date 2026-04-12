"""Voice Harness — entry point."""

import os
import sys

# Env vars that must be set before any Qt / torch imports.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--in-process-gpu"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
# OLLAMA_HOST removed — now using hosted Gemini via OpenAI SDK.

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from ui.main_window import MainWindow
from harness.coordinator import Coordinator


def _apply_dark_theme(app: QApplication) -> None:
    """Apply a VS Code–inspired dark theme palette."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2d2d2d"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#333333"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#569cd6"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#094771"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#666666"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#666666"))
    app.setPalette(palette)
    app.setStyleSheet(
        "QToolTip { color:#d4d4d4; background:#252526; border:1px solid #3c3c3c; }"
    )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Voice Harness")
    _apply_dark_theme(app)

    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    coordinator = Coordinator(project_root=root)
    window = MainWindow(coordinator)

    # Default file tree root to CWD (overridden by CLI arg or project open).
    window.set_root_path(root)

    window.show()

    coordinator.set_ptt_mode(True)  # PTT + two-stage confirmation is the default input mode
    coordinator.start()
    code = app.exec()

    coordinator.stop()
    sys.exit(code)


if __name__ == "__main__":
    main()
