---
description: 'Qt + WebEngine constraints: --in-process-gpu, sandbox off, localhost-HTTP Monaco'
applyTo: 'ui/**/*.py, phase0_poc/**/*.py, main.py'
---

# Qt / WebEngine Instructions

These rules are required for QWebEngineView to run reliably on the target dual-GPU Windows
laptop (Intel iGPU + RTX 4080 Optimus) and to load Monaco Editor without Web Worker errors.

## Environment variables — set BEFORE any Qt import

In `main.py` (and any standalone script that creates a `QApplication`):

```python
import os
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--in-process-gpu"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
# Only AFTER the env vars above:
from PyQt6.QtWidgets import QApplication
```

- `--in-process-gpu` is mandatory on this dual-GPU laptop; without it the GPU process
  crashes during context creation.
- `QTWEBENGINE_DISABLE_SANDBOX=1` is required on Windows for QtWebEngine in this setup.

## Monaco serving

- Monaco Editor (`assets/monaco/min/`) must be served via a **localhost HTTP server**.
- Never load Monaco via `file://` — Web Worker security restrictions break the AMD loader.
- Never use a custom URL scheme (`app://`, `qrc://`) — `QBuffer` lifetime/GC issues cause
  intermittent blank pages. The Phase 0 POC ([phase0_poc/monaco_poc.py](../../phase0_poc/monaco_poc.py))
  established localhost HTTP as the only viable path.

## Main-window guard

`main.py` must wrap startup with `if __name__ == "__main__":`. PyQt6 + multiprocessing on
Windows will spawn ghost processes otherwise.

## Threading

- Qt widgets and signals belong to the GUI thread only.
- Long-running work (LLM calls, audio capture, model loading) runs on `QThread` workers
  or `concurrent.futures` executors; results return via signals.
- Do not block the GUI thread with `time.sleep`, blocking I/O, or model warm-up.

## Testing

- UI tests use the `qapp` fixture and `@pytest.mark.ui`.
- Do not instantiate `QApplication` directly in tests — use the fixture.

## Cross-references

- TDD discipline: [tdd.instructions.md](tdd.instructions.md).
