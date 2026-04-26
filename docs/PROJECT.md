# Project: Voice Harness

## Vision

A standalone desktop coding assistant driven primarily by voice. Voice Harness replaces VS Code — it is the IDE. The user speaks, the system edits code and explains what it did.

## Goals

1. **Local voice loop** — STT and TTS run locally; the LLM currently uses a hosted Gemini API.
2. **Voice-first** — primary interaction is speech; keyboard/mouse is secondary.
3. **Safe editing** — all code changes shown as diffs; user accepts or rejects before applying.
4. **Fast feedback** — TTS starts reading the response while the LLM is still generating.
5. **Extensible** — phased architecture with stub interfaces so each layer can be upgraded independently.

## Requirements

### Functional

- Continuous voice-to-text transcription (sounddevice + WebRTC VAD + faster-whisper turbo)
- Push-to-talk support for controlled voice input
- Code LLM queries with file context and repo map (Gemini 2.5 Flash Lite via OpenAI-compatible SDK)
- SEARCH/REPLACE edit parsing with fuzzy fallback and syntax validation
- Diff view for accepting/rejecting edits (Monaco Diff Editor in Phase 3a)
- Text-to-speech response readback (Kokoro-82M, sentence-split and stream-capable)
- File browser (QTreeView + QFileSystemModel)
- Monaco code editor with syntax highlighting (Phase 2b)
- Git auto-commit on accepted changes (gitpython)
- Tree-sitter repo map for richer LLM context (Phase 3b)

### Non-Functional

- Runs on RTX 4080 Laptop 12GB VRAM — VRAM budget ~11.5GB
- End-to-end latency target: low enough that speaking, editing, and response readback feel fluid
- First TTS word target: begin playback while the response is still being generated
- Cold startup: 25-50 seconds (all models loading)
- Windows 11 primary target

### Hardware Reference

| Component | Spec |
|---|---|
| Laptop | Razer Blade 16 (2023) |
| GPU | NVIDIA RTX 4080 Laptop, 12GB VRAM |
| CPU | Intel i9-13950HX |
| RAM | 32GB DDR5 |
| OS | Windows 11 Home 25H2 |

## Tech Stack

| Component | Technology | Version | Notes |
|---|---|---|---|
| Language | Python | 3.11.x | Use 3.11 for audio dependency compatibility |
| UI | PyQt6 | >=6.6.0,<6.8.0 | GPL v3 |
| Browser engine | PyQt6-WebEngine | >=6.6.0,<6.8.0 | Separate pip package |
| Code editor | Monaco Editor | 0.52.0 | AMD build only |
| STT | faster-whisper turbo + WebRTC VAD | faster-whisper>=1.1.0 | Direct mic pipeline in `harness/voice_input.py` |
| Whisper backend | faster-whisper (via ctranslate2) | ctranslate2==4.4.0 | Pin: >=4.5.0 needs cuDNN 9.2 |
| LLM | Gemini 2.5 Flash Lite | openai>=1.30.0 | OpenAI-compatible Gemini endpoint |
| TTS | Kokoro | >=0.9.0 | GPU when CUDA is available, CPU fallback — needs espeak-ng |
| GPU compute | PyTorch + CUDA 12.1 | torch==2.3.0+cu121 | Must install FIRST |
| Git | gitpython | >=3.1.40 | |
| Code intel | tree-sitter | >=0.21.0 | Phase 3b |

## Licensing

- **PyQt6**: GPL v3 — must open-source under GPL v3 OR buy Riverbank commercial license (~£350/dev/yr)
- **Hosted LLM**: requires a Gemini API key and internet connection; STT/TTS remain local.
- **All other deps**: MIT, Apache 2.0, or BSD-3 — fully GPL v3 compatible

## Reference Projects

| Project | Relevance |
|---|---|
| [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) | Queue-based pipeline architecture |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | SEARCH/REPLACE edit format + repo-map concept |
| [signupss/ai-code-sherlock](https://github.com/signupss/ai-code-sherlock) | PyQt6 3-panel IDE reference |
