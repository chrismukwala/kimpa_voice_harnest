# AGENTS.md — Voice Harness

> Quick-start context for any AI coding agent working on this project.
> See `docs/` for deep dives on architecture, progress, and decisions.

## What is this project?

Voice Harness is a standalone desktop voice-driven coding assistant that replaces VS Code entirely. The user speaks a command; the system transcribes it (STT), sends it plus file context to a hosted Code LLM, receives SEARCH/REPLACE edit blocks + prose, shows edits as a diff for accept/reject, and reads the prose aloud (TTS). STT and TTS run locally; the LLM uses Gemini 2.5 Pro via API.

## Tech stack

| Layer | Technology |
|---|---|
| UI framework | PyQt6 + PyQt6-WebEngine |
| Code editor | Monaco Editor 0.52.0 (AMD build) via QWebEngineView + QWebChannel |
| STT | RealtimeSTT (wraps faster-whisper large-v3 + Silero VAD) |
| Code LLM | Gemini 2.5 Pro via OpenAI SDK (hosted, 100k char context) |
| TTS | Kokoro-82M (CPU, Apache 2.0) |
| Edit format | Aider-style SEARCH/REPLACE blocks |
| Git | gitpython — auto-commit accepted changes |

## Dev environment

- **Python 3.11.x required** — 3.12+ breaks webrtcvad and OpenWakeWord
- **CUDA toolkit** — nvcc must be on PATH
- **espeak-ng** — must be installed and on PATH (Kokoro dependency)
- **Windows 11** — primary target platform (Razer Blade 16, RTX 4080 12GB)

## Key commands

```bash
# First-time setup (creates venv, installs CUDA PyTorch first, then deps)
python setup/install.py

# Run the app
python main.py

# Run all tests (TDD — do this before every commit)
python -m pytest tests/ -v

# Manual audio diagnostics (full .venv only)
python tools/test_audio.py
python tools/test_mic.py

# Run Phase 0 Monaco POC (standalone test)
python phase0_poc/monaco_poc.py
```

## Development workflow — Red/Green/Refactor TDD

1. **Red**: Write a failing test in `tests/` that describes the new behaviour.
2. **Green**: Write the minimum production code to make it pass.
3. **Refactor**: Clean up while all tests stay green.
4. Run `python -m pytest tests/ -v` — all tests must pass before committing.

Every new feature or bug fix starts with a test. Code without a test is unfinished.

## Project layout

```
voice_harnest/
├── main.py                    # Entry point (if __name__ == '__main__' guard required)
├── AGENTS.md                  # This file
├── pytest.ini                 # Pytest configuration
├── requirements.txt           # Deps — do NOT pip install directly; use setup/install.py
├── setup/
│   └── install.py             # 6-step installation wizard
├── harness/
│   ├── audio_devices.py       # sounddevice device enumeration helpers
│   ├── audio_settings.py      # QSettings-backed audio persistence seam
│   ├── coordinator.py         # Queue pipeline: STT → context_assembler → LLM → response_splitter → TTS
│   ├── voice_input.py         # Thin RealtimeSTT adapter — ONLY file that imports RealtimeSTT
│   ├── code_llm.py            # Gemini client (OpenAI SDK) + SEARCH/REPLACE parser
│   ├── tts.py                 # Kokoro: speak(text) → List[Tuple[str, bytes]]
│   └── tts_navigator.py       # TTS playback, navigation, speed, highlighting
├── tools/
│   ├── test_audio.py          # Manual TTS audio smoke test
│   └── test_mic.py            # Manual microphone/STT smoke test
├── ui/
│   ├── main_window.py         # 3-panel layout: file tree | editor | AI panel
│   ├── editor_panel.py        # QPlainTextEdit placeholder (Monaco in Phase 2b)
│   └── ai_panel.py            # Voice status, response log, audio settings, TTS UI
├── phase0_poc/
│   └── monaco_poc.py          # Monaco ↔ QWebChannel round-trip POC (PASSED)
├── tests/
│   ├── conftest.py            # Shared fixtures (qapp for UI tests)
│   ├── test_code_llm.py       # SEARCH/REPLACE parser + prose extraction tests
│   ├── test_tts.py            # Sentence splitter + speak contract tests
│   ├── test_voice_input.py    # VoiceInput adapter API tests
│   ├── test_coordinator.py    # Message format + pipeline tests
│   ├── test_audio_devices.py  # sounddevice enumeration tests
│   ├── test_audio_settings.py # persisted audio-settings seam tests
│   ├── test_editor_panel.py   # EditorPanel widget tests
│   └── test_ai_panel.py       # AiPanel widget + signal tests
├── assets/
│   └── monaco/min/            # Monaco 0.52.0 AMD build (loader.js + vs/)
└── docs/                      # Full project documentation
    ├── PROJECT.md             # Goals, requirements, scope
    ├── ARCHITECTURE.md        # Module map, data flow, key patterns
    ├── PROGRESS.md            # Living phase tracker — update as you complete work
    ├── SETUP.md               # Environment setup, known workarounds
    ├── CONVENTIONS.md         # Coding standards
    └── DECISIONS.md           # Architecture decisions and rationale
```

## Critical constraints — read before making changes

1. **PyTorch CUDA must install FIRST** — before RealtimeSTT or any other dep, or CPU-only torch gets locked in.
2. **ctranslate2 pinned to 4.4.0** — ≥4.5.0 requires cuDNN 9.2 which conflicts with this GPU setup.
3. **`--in-process-gpu` Chromium flag** — required for QWebEngineView on this dual-GPU laptop (Intel iGPU + RTX 4080 Optimus). Set via `QTWEBENGINE_CHROMIUM_FLAGS` before any Qt imports.
4. **`QTWEBENGINE_DISABLE_SANDBOX=1`** — required on Windows for QtWebEngine.
5. **Monaco must be served via localhost HTTP** — NOT `file://` (Web Worker restrictions) or custom `app://` scheme (QBuffer GC issues). This is proven in Phase 0 POC.
6. **Only `voice_input.py` imports RealtimeSTT** — thin adapter pattern so the library can be swapped.
7. **Coordinator message format**: `{"query": str, "context": str|None, "repo_map": str|None}` — never plain strings.
8. **`tts.py` returns `List[Tuple[str, bytes]]`** — sentence-split WAV chunks, required for Phase 4 arrow-key navigation.
9. **VRAM budget is 12GB** — faster-whisper must use `compute_type="int8_float16"` (NOT fp16). LLM runs in the cloud (Gemini 2.5 Pro) — no local VRAM needed.
10. **Apache 2.0 license** — see LICENSE file. Note: PyQt6 itself is GPL v3.

## After completing work

- Run `python -m pytest tests/ -v` — all tests must pass.
- Update `docs/PROGRESS.md` with what you changed and the new phase status.
- Commit with a conventional commit message: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`.
- Do NOT run `git add .` or `git add -A` — stage specific files only.
