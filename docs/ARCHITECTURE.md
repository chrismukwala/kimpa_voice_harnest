# Architecture

## System Overview

Voice Harness is a PyQt6 desktop application with a queue-based pipeline coordinating voice input, LLM processing, edit review, and TTS output. The UI is a 3-panel IDE shell.

```
┌──────────────────────────────────────────────────────────────────┐
│                         MainWindow                               │
│  ┌──────────┐  ┌────────────────────┐  ┌───────────────────┐    │
│  │ File Tree │  │   Editor Panel     │  │    AI Panel       │    │
│  │ QTreeView │  │   Monaco Editor    │  │  - Status label   │    │
│  │           │  │                    │  │  - Response log   │    │
│  │           │  │                    │  │  - Manual input    │    │
│  │           │  │                    │  │  - Pause button    │    │
│  └──────────┘  └────────────────────┘  └───────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## Pipeline (Coordinator)

The `Coordinator` runs a background thread processing a queue of message dicts. This architecture was chosen to match the [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) pattern and enable streaming in later phases.

```
Mic → VoiceInput (sounddevice + WebRTC VAD + faster-whisper turbo)
        │
        ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Coordinator Pipeline (background thread)                │
   │                                                          │
   │  1. STT text arrives (or manual text input)              │
   │  2. context_assembler [stub: pass-through]               │
      │     → Builds: {"query", "context", "repo_map"}          │
      │  3. code_llm.chat_stream_raw() → Gemini Flash Lite       │
      │  4. Parse SEARCH/REPLACE edits from raw response          │
      │  5. Split spoken prose into TTS sentences                 │
      │  6. tts.speak_stream() → incremental WAV chunks           │
      │  7. Emit TTS chunks to UI playback owner                  │
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
- Owns the direct mic → text pipeline: `sounddevice.InputStream`, WebRTC VAD, and
     faster-whisper turbo
- Public API: `start()`, `stop()`, `pause()`, `resume()`, `on_text(callback)`
- Supports input-device reconfiguration, push-to-talk mode, error callbacks, status callbacks,
     and recording-state callbacks for coordinator wiring
- RealtimeSTT and wake-word support were removed in Phase 5

### `harness/audio_settings.py`
- Shared persistence seam for input device, output device, legacy wake-word setting, and LLM API
     key via `QSettings`
- Keeps persistence out of `AiPanel`

### `harness/audio_devices.py`
- Enumerates input/output devices through `sounddevice`
- Exposes default-device lookup for startup selection

### `harness/code_llm.py`
- Gemini 2.5 Flash Lite client via OpenAI-compatible SDK
- `chat(query, context, repo_map, api_key) → str` — full LLM response
- `chat_stream_raw(...)` — raw streaming deltas for edit capture and spoken-response streaming
- `parse_search_replace(text) → list[dict]` — lenient regex parser (6-8 chevrons)
- `extract_prose(text) → str` — strips edit blocks, returns TTS-ready prose
- Context budget: 100,000 chars (Gemini supports 1M tokens)

### `harness/tts.py`
- Kokoro wrapper running on GPU when CUDA is available, otherwise CPU
- `speak(text) → List[Tuple[str, bytes]]` — sentence-split WAV chunks
- `speak_stream(sentences)` — yields sentence WAV chunks as spoken prose becomes available
- `play_wav_bytes(wav_bytes)` — plays through default audio device
- The list-of-tuples return type enables Phase 4 arrow-key TTS navigation

### `harness/coordinator.py`
- QObject with Qt signals for UI updates
- Background thread processes queue items
- Builds message dicts with current file context and repo-map context
- Manages voice lifecycle: start/stop/pause/resume
- Owns semantic TTS lifecycle via `begin_tts_playback()` / `finish_tts_playback()`
- Owns microphone reconfiguration via `set_input_device()`; `set_wake_word_enabled()` is a
     compatibility no-op after Phase 5
- Emits explicit `recording_active_changed(bool)` for listening-state UI
- Does not play audio directly; it emits synthesized chunks for the UI playback owner

### `harness/tts_navigator.py`
- Executes sentence-level TTS playback on the UI side
- Emits completion when playback finishes
- Emits `playback_error(str)` so audio failures surface into the UI
- Supports an explicit output-device override from audio settings
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
├── faster-whisper turbo          ~0.8 GB  (int8_float16 — NOT fp16!)
├── OS + PyQt6 + Chromium         ~1.0 GB
└── Kokoro-82M                    ~0.3 GB  (GPU when available)
                                 ──────
                Total   ~2.1 GB   ✓ comfortable
```

**Gemini 2.5 Flash Lite runs in the cloud — no local VRAM needed for LLM.**
**Previously: Ollama + Qwen2.5-Coder:14b consumed ~9 GB, leaving only ~1.5 GB headroom.**

## Threading Model

- **Main thread**: Qt event loop (UI)
- **Coordinator thread**: Pipeline queue processing (daemon)
- **VoiceInput thread**: sounddevice/WebRTC VAD/faster-whisper loop (daemon)
- **Asset server thread**: localhost HTTP server for Monaco (daemon, Phase 2b)
- All background → UI communication via Qt signals (thread-safe)
