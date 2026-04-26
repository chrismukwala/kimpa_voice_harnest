# Plan: Phase 4 Stabilization — Audio Recovery, Device Config, and UX Follow-Ups

> Historical plan. Phase 5 replaced RealtimeSTT/OpenWakeWord with direct faster-whisper,
> WebRTC VAD, and push-to-talk support. Use `docs/PROGRESS.md` for current phase status and
> treat this document as background on why audio UX stabilization matters.

> **Created:** 2026-04-10
> **Status:** Implementation complete; hardware validation pending
> **Prerequisite:** Phase A0 is complete. Phases A and B must complete before C–E.

## TL;DR

This is reopened Phase 4 stabilization work, not a clean new feature phase. The code tasks in
Phases A0-E are now implemented. The remaining work is manual validation on real speakers and
microphones in the full Python 3.11 application environment.

---

## Phase A0: TTS Ownership and Playback Contract — DONE (2026-04-11)

Problem addressed:

- The coordinator synthesized TTS chunks, but playback only started after a manual UI action.
  That made silent playback ambiguous: it was unclear whether synthesis, playback, or device
  selection had failed.

Completed work:

1. Added Red-first contract tests for autoplay, speaking/listening state ownership, and stop /
   finish playback transitions.
2. Added explicit `Coordinator.begin_tts_playback()` and `finish_tts_playback()` methods so
   playback semantics live in one place.
3. Made `MainWindow` the playback-policy owner: `tts_chunks_ready` now autoplays immediately,
   and play/stop/space/escape all go through the same handlers.
4. Added playback session tokens in `TtsNavigator` so stale completion callbacks cannot cancel a
   newer playback session.

Outcome:

- Phase A can now focus on real audio-output diagnosis rather than ownership ambiguity.

---

## Phase A: Diagnose & Fix Audio Playback (real silence) — BLOCKING STABILIZATION

The `TtsNavigator._play_worker()` uses `sd.play(data, samplerate)` followed by `sd.wait()`. Possible causes of silence:

1. **sounddevice output device not set** — `sd.default.device` may not match the user's expected output. On multi-GPU / multi-audio-interface Windows systems, sounddevice often picks a wrong or virtual device.
2. **Kokoro generating empty/silent WAV** — espeak-ng might not be installed or on PATH, causing Kokoro to produce zero-length or silent audio silently.
3. **Playback error visibility still too weak** — ownership ambiguity is fixed in Phase A0, but
   `_play_worker` still only logs warnings and does not surface failures into the product UI.
4. **Sample rate mismatch** — `int(sr * speed)` at speed=1.0 is fine, but if the audio device doesn't support 24kHz, playback silently fails on some drivers.

### Steps

1. **Add a standalone TTS smoke test script** (`tools/test_audio.py`) that:
   - Lists all audio output devices via `sd.query_devices()`
   - Generates a simple sine wave and plays it through the default device
   - Generates a Kokoro TTS sample and plays it
   - Reports success/failure to stdout
   - This becomes a permanent diagnostic tool

2. **Add error surfacing in TtsNavigator** — currently `_play_worker` logs warnings but the user never sees them. Emit a new `playback_error(str)` signal that surfaces in the AI panel log.

3. **Add output device parameter** to `TtsNavigator._play_worker()` — pass `device=` to `sd.play()` so the device picker (Phase C) can control it.

### Status update (2026-04-11)

Completed:
- `tools/test_audio.py` added as a manual smoke tool with output-device listing, sine-wave probe,
  Kokoro probe, and `--list-only` mode.
- `TtsNavigator.playback_error(str)` added and surfaced into the visible UI via `MainWindow`.
- `TtsNavigator.set_output_device()` added and playback now forwards `device=` to
   `sounddevice.play()`.

Remaining:
- Run the smoke tool inside the full Python 3.11 app environment for real hardware validation.

### Files changed

- `harness/tts_navigator.py` — add `playback_error` signal, `_output_device` field, pass `device=` to `sd.play()`
- `tools/test_audio.py` — NEW

---

## Phase B: Diagnose & Fix STT (voice not detected) — IMPLEMENTED

The STT shows "listening" but never transcribes. Possible causes:

1. **Wake word model not downloading/loading** — OpenWakeWord's "hey_jarvis" model may fail silently, causing the recorder to perpetually wait for a wake word it can never detect.
2. **Wrong input device** — same as TTS but for microphone; `use_microphone=True` picks the OS default which might be wrong.
3. **Silero VAD sensitivity too low** — `0.4` might be too low for the user's mic/environment.
4. **RealtimeSTT model download stalling** — first run downloads large-v3 whisper model (~3GB), which could time out.

### Steps

1. **Add console logging to `_listen_loop()`** — log when the recorder is created, when `start()` is called, when `text()` returns, and any exceptions.

2. **Add a standalone STT smoke test script** (`tools/test_mic.py`) that:
   - Lists all input devices via `sd.query_devices()`
   - Records 3 seconds of audio from the default device and prints amplitude stats
   - Optionally tests RealtimeSTT transcription

3. **Make wake word optional** — add a config flag to disable wake word detection (always-on mode) since it's a common failure point. Default to wake-word-off for initial debugging.

4. **Pass `input_device_index`** to `AudioToTextRecorder` — needed for device picker (Phase C).

### Files changed

- `harness/voice_input.py` — add logging, optional wake word flag, `input_device_index` param
- `tools/test_mic.py` — NEW

### Status update (2026-04-11)

Completed:
- `_listen_loop()` now logs recorder creation, start, and transcription flow.
- Wake-word gating is now configurable and defaults to off for stabilization.
- `VoiceInput` now accepts an explicit input-device override.
- `tools/test_mic.py` added for manual input-device diagnostics and optional STT transcription.

---

## Phase C: Audio Device Picker UI — IMPLEMENTED

### Steps

1. **Create a shared audio settings seam** so device persistence does not live in `AiPanel`:
   - Persist selected input and output devices via `QSettings`
   - Keep `AiPanel` as a view and signal source only

2. **Create `harness/audio_devices.py`** — utility module:
   - `list_input_devices() -> List[dict]` — returns `[{"index": int, "name": str, "channels": int}, ...]` via `sd.query_devices()`, filtered to input-capable devices
   - `list_output_devices() -> List[dict]` — same for output-capable devices
   - `get_default_input() -> int`
   - `get_default_output() -> int`

3. **Add device selection to `AiPanel`** — two `QComboBox` dropdowns:
   - "Input Device" (microphone) — populated from `list_input_devices()`
   - "Output Device" (speakers) — populated from `list_output_devices()`
   - Place above the status label in a collapsible "Audio Settings" section
   - Emit signals: `input_device_changed(int)`, `output_device_changed(int)`
   - Persistence should be handled by the shared settings seam, not by the panel itself

4. **Wire input device to VoiceInput** — add `set_device(device_index: int)` method to `VoiceInput`; pass `input_device_index=` to `AudioToTextRecorder`

5. **Wire output device to TtsNavigator** — add `set_output_device(device_index: int)` method; pass `device=` to `sd.play()` in `_play_worker`

6. **Wire in MainWindow** — connect AI panel device signals → coordinator/navigator

7. **Tests**: test `audio_devices.py` with mocked `sounddevice`, test signal wiring

### Files changed

- `harness/audio_devices.py` — NEW: device enumeration utility
- `harness/voice_input.py` — add `set_device()` method
- `harness/tts_navigator.py` — add `set_output_device()` method
- `ui/ai_panel.py` — device picker dropdowns + signals
- `ui/main_window.py` — wire device signals
- `tests/test_audio_devices.py` — NEW

### Status update (2026-04-11)

Completed:
- Shared `QSettings` persistence seam added before any picker UI.
- Input/output device pickers now live in a collapsible audio-settings section in `AiPanel`.
- `MainWindow` now loads persisted audio settings, applies them to coordinator/navigator, and
   writes changes back through the settings seam.

---

## Phase D: Flashing Recording Indicator — IMPLEMENTED

### Steps

1. **Add `QTimer`-based flashing to status label in `AiPanel`** — when state is `"listening"`:
   - Toggle between cyan (#4ec9b0) and dark background every 500ms
   - Stop flashing when state changes away from "listening"
   - Use `QTimer.timeout` connected to a `_toggle_flash()` slot

2. **Add a pulsing red dot** — small `QLabel` with a red circle (●) that pulses opacity via `QPropertyAnimation` when in "listening" state

3. **Tests**: verify flash timer starts/stops on state transitions

### Files changed

- `ui/ai_panel.py` — flash timer, pulsing dot animation
- `tests/test_ai_panel.py` — flash state transition tests

### Status update (2026-04-11)

Completed:
- `AiPanel` now exposes an explicit recording-active path.
- The listening indicator now flashes with a `QTimer` and shows a pulsing red dot when the mic
   is actively listening.

---

## Phase E: Word-by-Word TTS Highlighting — IMPLEMENTED

### Steps

1. **Add word timing estimation to `TtsNavigator`** — since Kokoro doesn't provide word-level timestamps, estimate them:
   - Calculate total duration from WAV sample count / sample rate
   - Split sentence into words
   - Distribute duration proportionally by word length (character count as proxy)
   - Emit `word_highlight(int, int)` signal (word_index, word_count) at timed intervals using a `QTimer`

2. **Add `_highlight_timer` to `TtsNavigator`** — starts when a chunk begins playing:
   - Pre-compute word boundaries and timestamps
   - `QTimer` fires at each word boundary, emitting `word_highlight`

3. **Update `AiPanel._tts_sentence` display** — convert from `QLabel` to `QTextEdit` or use HTML:
   - On `word_highlight(idx, total)`: rebuild the sentence HTML with the current word wrapped in `<span style="background:#ce9178; color:white">word</span>`
   - All other words in default color

4. **Wire in `MainWindow`** — connect `TtsNavigator.word_highlight` → `AiPanel.highlight_word`

5. **Tests**: verify word timing calculation, signal emission, and HTML generation

### Files changed

- `harness/tts_navigator.py` — word timing estimation, `_highlight_timer`, `word_highlight` signal
- `ui/ai_panel.py` — HTML-based sentence display with word highlighting
- `ui/main_window.py` — wire `word_highlight` signal
- `tests/test_tts_navigator.py` — word timing + signal tests
- `tests/test_ai_panel.py` — HTML highlight rendering tests

### Status update (2026-04-11)

Completed:
- `TtsNavigator` now estimates word timings from WAV duration and playback speed.
- Word highlights are emitted during playback and rendered as HTML in `AiPanel`.
- `MainWindow` now clears highlights on stop/finish and keeps them aligned with navigator state.

---

## All Relevant Files (Summary)

| File | Action | Phases |
|---|---|---|
| `harness/tts_navigator.py` | Edit | A, C, E |
| `harness/voice_input.py` | Edit | B, C |
| `harness/tts.py` | No changes | — |
| `harness/audio_devices.py` | **NEW** | C |
| `ui/ai_panel.py` | Edit | C, D, E |
| `ui/main_window.py` | Edit | C, E |
| `tools/test_audio.py` | **NEW** | A |
| `tools/test_mic.py` | **NEW** | B |
| `tests/test_audio_devices.py` | **NEW** | C |
| `tests/test_ai_panel.py` | Edit | D, E |
| `tests/test_tts_navigator.py` | Edit | A, E |

---

## Verification Checklist

1. `python tools/test_audio.py` — confirm sine wave and Kokoro TTS produce audible sound
2. `python tools/test_mic.py` — confirm microphone captures audio with non-zero amplitude
3. `python -m pytest tests/ -v` — all existing + new tests pass
4. Launch app → select correct input/output devices from dropdowns
5. Speak → verify transcription appears in AI panel
6. After LLM responds → verify TTS audio plays through selected output device
7. During TTS playback → verify word highlighting animates in sentence preview
8. During "listening" state → verify status label flashes cyan
9. Close and reopen app → verify device selections persist

Current status:
- Item 3 is complete in automated tests.
- Items 1, 2, and 4-9 still require manual validation in the full `.venv` on Python 3.11.x.

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Playback policy lives in `MainWindow` | Coordinator owns semantic speaking/listening state, while `TtsNavigator` executes audio and reports completion. |
| Output-device override lives in `TtsNavigator` | Future audio settings only need to call one playback API; the worker snapshots the chosen device before playback starts. |
| Word timing is estimated, not exact | Kokoro doesn't expose phoneme-level timestamps. Proportional character-length distribution is a good-enough heuristic. Can improve later with forced alignment. |
| espeak-ng is a hard Kokoro dependency | If not installed, TTS silently fails. The diagnostic script (`tools/test_audio.py`) will detect and report this. |
| Wake word defaults to OFF for debugging | This is a temporary recovery mode only until coordinator-owned audio settings make the supported modes explicit. |
| Device selection persisted via `QSettings` | Lightweight, no config file needed. |
| Phases A and B first | No point adding UI features for audio that doesn't work. |
