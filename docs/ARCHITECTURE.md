# Architecture

## System Overview

Voice Harness is a PyQt6 desktop application with a queue-based pipeline coordinating voice input, LLM processing, and TTS output. The UI is a 3-panel IDE shell.

```
┌──────────────────────────────────────────────────────────────────┐
│                         MainWindow                               │
│  ┌──────────┐  ┌────────────────────┐  ┌───────────────────┐    │
│  │ File Tree │  │   Editor Panel     │  │    AI Panel       │    │
│  │ QTreeView │  │   (QPlainTextEdit  │  │  - Status label   │    │
│  │           │  │    → Monaco in 2b) │  │  - Response log   │    │
│  │           │  │                    │  │  - Manual input    │    │
│  │           │  │                    │  │  - Pause button    │    │
│  └──────────┘  └────────────────────┘  └───────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## Pipeline (Coordinator)

The `Coordinator` runs a background thread processing a queue of message dicts. This architecture was chosen to match the [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) pattern and enable streaming in later phases.

```
Mic → VoiceInput (RealtimeSTT)
        │
        ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Coordinator Pipeline (background thread)                │
   │                                                          │
   │  1. STT text arrives (or manual text input)              │
   │  2. context_assembler [stub: pass-through]               │
   │     → Builds: {"query", "context", "repo_map"}          │
   │  3. code_llm.chat() → Gemini 2.5 Pro → full response text  │
   │  4. response_splitter [stub: pass-through]               │
   │     → Separates prose from SEARCH/REPLACE blocks         │
   │  5. tts.speak(prose) → List[Tuple[str, bytes]]          │
   │  6. Emit TTS chunks to UI playback owner                 │
   └─────────────────────────────────────────────────────────┘
        │
        ▼
   Qt Signals → UI updates → TtsNavigator playback
```

### Message Format (from day 1)

```python
{
    "query": str,           # User's spoken or typed request
    "context": str | None,  # Currently open file contents
    "repo_map": str | None, # Tree-sitter symbol map (Phase 3b)
}
```

This format is intentionally over-specified for Phase 1 so that Phase 3 doesn't require a coordinator rewrite.

## Module Responsibilities

### `harness/voice_input.py`
- **Only file that imports RealtimeSTT** — thin adapter pattern
- Public API: `start()`, `stop()`, `pause()`, `resume()`, `on_text(callback)`
- Supports input-device reconfiguration, wake-word enable/disable, error callbacks, and
     recording-state callbacks for coordinator wiring
- If RealtimeSTT needs replacing, only this ~80-line file changes

### `harness/audio_settings.py`
- Shared persistence seam for input device, output device, and wake-word mode via `QSettings`
- Keeps persistence out of `AiPanel`

### `harness/audio_devices.py`
- Enumerates input/output devices through `sounddevice`
- Exposes default-device lookup for startup selection

### `harness/code_llm.py`
- Gemini 2.5 Pro client via OpenAI-compatible SDK
- `chat(query, context, repo_map, api_key) → str` — full LLM response
- `parse_search_replace(text) → list[dict]` — lenient regex parser (6-8 chevrons)
- `extract_prose(text) → str` — strips edit blocks, returns TTS-ready prose
- Context budget: 100,000 chars (Gemini supports 1M tokens)

### `harness/tts.py`
- Kokoro wrapper running on CPU (82M params, fast enough)
- `speak(text) → List[Tuple[str, bytes]]` — sentence-split WAV chunks
- `play_wav_bytes(wav_bytes)` — plays through default audio device
- The list-of-tuples return type enables Phase 4 arrow-key TTS navigation

### `harness/coordinator.py`
- QObject with Qt signals for UI updates
- Background thread processes queue items
- `context_assembler` and `response_splitter` are currently pass-through stubs
- Manages voice lifecycle: start/stop/pause/resume
- Owns semantic TTS lifecycle via `begin_tts_playback()` / `finish_tts_playback()`
- Owns microphone reconfiguration via `set_input_device()` / `set_wake_word_enabled()`
- Emits explicit `recording_active_changed(bool)` for listening-state UI
- Does not play audio directly; it emits synthesized chunks for the UI playback owner

### `harness/tts_navigator.py`
- Executes sentence-level TTS playback on the UI side
- Emits completion when playback finishes
- Emits `playback_error(str)` so audio failures surface into the UI
- Supports an explicit output-device override for future audio settings
- Emits heuristic word-highlighting updates during playback
- Guards against stale completion from interrupted playback sessions

### `ui/main_window.py`
- QSplitter with 3 panels: QTreeView (220px) | EditorPanel (700px) | AiPanel (380px)
- Wires coordinator signals → AI panel display
- Wires file tree double-click → editor load + coordinator context update
- Owns playback policy: autoplay on fresh chunks, manual replay, and stop / completion wiring
- Applies persisted audio settings to coordinator and TTS navigator on startup

### `ui/editor_panel.py`
- Phase 1: QPlainTextEdit with Consolas font, dark theme
- Phase 2b: Replaced entirely with Monaco QWebEngineView + QWebChannel
- `set_file(path, content)` and `get_content()` API stays the same

### `ui/ai_panel.py`
- Status label: idle (green) / listening (cyan) / processing (yellow) / speaking (orange)
- Read-only response log (QPlainTextEdit)
- Manual text input with Send button (fallback when mic unavailable)
- Pause Listening toggle button (red when active, green when paused)
- Emits `text_submitted(str)` and `pause_toggled(bool)` signals
- Contains collapsible audio settings, a flashing listening indicator, and HTML TTS word
     highlighting

## Monaco Integration (Phase 0 proven, Phase 2b wiring)

Monaco is served via a localhost HTTP server (daemon thread), NOT via `file://` or custom URL schemes.

```
┌─────────────────────────────────────┐
│  Python (main process)              │
│  ┌───────────────────────────┐      │
│  │ http.server.HTTPServer    │      │
│  │ 127.0.0.1:<random_port>  │──────│── serves assets/monaco/min/
│  └───────────────────────────┘      │
│  ┌───────────────────────────┐      │
│  │ QWebEngineView            │      │
│  │  setHtml(html,            │      │
│  │    baseUrl=localhost:port) │      │
│  │  QWebChannel ↔ JS bridge  │      │
│  └───────────────────────────┘      │
└─────────────────────────────────────┘
```

### Why not file:// or app://?
- `file://` blocks Monaco Web Workers (same-origin policy)
- `app://` custom scheme via `QWebEngineUrlSchemeHandler` had QBuffer garbage collection issues — content loaded but page rendered blank
- Localhost HTTP works reliably. Proven in Phase 0 POC.

## VRAM Layout

```
RTX 4080 Laptop — 12GB VRAM
├── faster-whisper large-v3       ~1.5 GB  (int8_float16 — NOT fp16!)
├── OS + PyQt6 + Chromium         ~1.0 GB
└── Kokoro-82M                    0.0 GB   (CPU)
                                 ──────
                         Total   ~2.5 GB   ✓ comfortable
```

**Gemini 2.5 Pro runs in the cloud — no local VRAM needed for LLM.**
**Previously: Ollama + Qwen2.5-Coder:14b consumed ~9 GB, leaving only ~1.5 GB headroom.**

## Threading Model

- **Main thread**: Qt event loop (UI)
- **Coordinator thread**: Pipeline queue processing (daemon)
- **VoiceInput thread**: RealtimeSTT blocking loop (daemon)
- **Asset server thread**: localhost HTTP server for Monaco (daemon, Phase 2b)
- All background → UI communication via Qt signals (thread-safe)
