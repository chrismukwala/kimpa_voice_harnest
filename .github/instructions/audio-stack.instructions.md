---
description: 'Audio stack constraints: Python 3.11, ctranslate2 4.4.0, int8_float16, espeak-ng'
applyTo: 'harness/voice_input.py, harness/tts.py, harness/audio_devices.py, harness/audio_settings.py, harness/tts_navigator.py, tools/test_audio.py, tools/test_mic.py'
---

# Audio Stack Instructions

These rules govern microphone capture, transcription, and text-to-speech. Violating them breaks
the validated GPU pipeline on the target hardware (RTX 4080 12 GB, dual-GPU laptop).

## Hard pins

- **Python 3.11.x only** — the audio stack (faster-whisper + ctranslate2 + Kokoro) is validated
  on 3.11. Do not raise the floor or test on 3.12.
- **`ctranslate2 == 4.4.0`** — pinned. ≥4.5.0 requires cuDNN 9.2 which conflicts with this setup.
- **`compute_type="int8_float16"`** for faster-whisper — never `float16`. The 12 GB VRAM budget
  also has Kokoro and Qt-WebEngine resident; fp16 OOMs.
- **espeak-ng must be on PATH** — Kokoro depends on it for phonemization. Surface a clear error
  at startup if missing; do not silently fall back.

## Module boundaries

- `harness/voice_input.py` owns microphone capture, WebRTC VAD framing, and faster-whisper
  transcription. Keep `sounddevice`, `webrtcvad`, and `faster_whisper` imports inside this
  module — do not leak them into `coordinator.py`, UI, or tests.
- `harness/tts.py` owns Kokoro synthesis. Its public contract: `speak(text: str)` returns
  `List[Tuple[str, bytes]]` — sentence-split WAV chunks, never a single buffer. Phase 4
  arrow-key navigation depends on this shape.
- `harness/audio_devices.py` handles `sounddevice` device enumeration; `audio_settings.py`
  is the QSettings-backed persistence seam. UI code reads/writes through these, not direct.

## Testing

- Mock `sounddevice`, `webrtcvad`, `faster_whisper`, and `kokoro` in unit tests — tests must
  run with no audio hardware and no GPU.
- Manual smoke checks live in [tools/test_audio.py](../../tools/test_audio.py) and
  [tools/test_mic.py](../../tools/test_mic.py); run them after touching this code.

## Cross-references

- Coordinator contract: [coordinator-contract.instructions.md](coordinator-contract.instructions.md).
