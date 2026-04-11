"""Shared fixtures for Voice Harness test suite."""

import os
import sys
import pytest

# Ensure env vars are set before any Qt imports (mirrors main.py).
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--in-process-gpu"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")


@pytest.fixture(scope="session")
def qapp():
    """Provide a single QApplication instance for all UI tests."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
