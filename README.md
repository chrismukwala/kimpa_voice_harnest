# Voice Harness

A standalone desktop **voice-driven coding assistant** built with Python 3.11, PyQt6, and Monaco Editor. Speak a command — the system transcribes it, sends it with file context to a Code LLM, shows edits as a diff for accept/reject, and reads the response aloud.

> **Status: Alpha — actively looking for testers!** See [Call for Testers](#-call-for-testers) below.

## Features

- **Voice-first workflow** — speak naturally; keyboard/mouse is secondary
- **Monaco code editor** — full syntax highlighting via embedded Monaco 0.52.0
- **AI-powered edits** — SEARCH/REPLACE blocks parsed from LLM output, shown as diffs
- **Accept / Reject** — review every change before it touches your code
- **Git auto-commit** — accepted edits are committed automatically
- **Local STT** — RealtimeSTT + faster-whisper large-v3 (runs on GPU)
- **Local TTS** — Kokoro-82M with sentence-level navigation and speed control
- **Repo map** — tree-sitter symbol index for richer LLM context
- **Cloud LLM** — Gemini 2.5 Pro via OpenAI SDK (100k char context)

## Tech Stack

| Layer | Technology |
|---|---|
| UI | PyQt6 + PyQt6-WebEngine |
| Editor | Monaco Editor 0.52.0 (AMD build, localhost HTTP) |
| STT | RealtimeSTT (faster-whisper large-v3 + Silero VAD) |
| LLM | Gemini 2.5 Pro via OpenAI SDK |
| TTS | Kokoro-82M (CPU, Apache 2.0) |
| Edit format | Aider-style SEARCH/REPLACE blocks |
| VCS | gitpython auto-commit |

## Requirements

- **Python 3.11.x** — 3.12+ breaks webrtcvad and OpenWakeWord
- **Windows 11** — primary target (Linux/macOS untested)
- **NVIDIA GPU** with CUDA 12.1 toolkit (nvcc on PATH)
- **espeak-ng** installed and on PATH (Kokoro dependency)
- **12 GB+ VRAM** recommended (tested on RTX 4080 Laptop)

## Quick Start

```bash
# Clone the repo
git clone https://github.com/chrismukwala/kimpa_voice_harnest.git
cd kimpa_voice_harnest

# Run the install wizard (creates venv, installs CUDA PyTorch first, then deps)
python setup/install.py

# Set your Gemini API key
# Create a .env file with: GEMINI_API_KEY=your-key-here

# Run the app
python main.py

# Run tests
python -m pytest tests/ -v
```

## Project Layout

```
voice_harnest/
├── main.py                 # Entry point
├── harness/                # Core modules (STT, LLM, TTS, coordinator, etc.)
├── ui/                     # PyQt6 UI (main window, editor, AI panel)
├── assets/monaco/          # Monaco Editor 0.52.0 AMD build
├── tests/                  # 210+ tests (TDD — Red/Green/Refactor)
├── setup/install.py        # 6-step install wizard
├── tools/                  # Manual audio diagnostics
├── phase0_poc/             # Monaco ↔ QWebChannel POC (passed)
└── docs/                   # Architecture, decisions, progress, setup
```

## Development

This project follows **Red → Green → Refactor** TDD:

1. Write a failing test
2. Write minimum code to pass
3. Refactor while tests stay green
4. `python -m pytest tests/ -v` before every commit

See [AGENTS.md](AGENTS.md) for full contributor guidelines.

## 🧪 Call for Testers

**We need your help!** Voice Harness is in alpha and we're looking for testers to try it on real hardware and report issues.

### What we need tested

- **Installation** — Does `setup/install.py` complete cleanly on your system?
- **Audio pipeline** — Does STT transcription work with your microphone?
- **TTS playback** — Does Kokoro read responses aloud correctly?
- **Monaco editor** — Does the editor render and respond to input?
- **Edit flow** — Do SEARCH/REPLACE diffs display and apply correctly?
- **GPU compatibility** — Any CUDA or QtWebEngine GPU issues?

### How to test

1. Follow the [Quick Start](#quick-start) above
2. Open a small project directory and try voice commands
3. Try manual text input via the AI panel if STT isn't working
4. Report issues at [GitHub Issues](https://github.com/chrismukwala/kimpa_voice_harnest/issues)

### What to include in bug reports

- OS version and GPU model
- Python version (`python --version`)
- CUDA toolkit version (`nvcc --version`)
- Full error traceback or screenshot
- Steps to reproduce

### Known limitations

- Windows 11 only (Linux/macOS untested)
- Requires NVIDIA GPU with CUDA 12.1
- Python 3.11 only (3.12+ not supported)
- Phase 4 (TTS UX) is stabilizing — audio device switching may have rough edges

## License

Licensed under the [Apache License 2.0](LICENSE).

## Author

Chris Mukwala — [@chrismukwala](https://github.com/chrismukwala)
