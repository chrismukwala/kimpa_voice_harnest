# Project: Voice Harness

## Vision

A standalone desktop coding assistant driven entirely by voice. Voice Harness replaces VS Code — it is the IDE. The user speaks, the system edits code and explains what it did.

## Goals

1. **Fully local** — no cloud APIs, no telemetry, no internet required after setup.
2. **Voice-first** — primary interaction is speech; keyboard/mouse is secondary.
3. **Safe editing** — all code changes shown as diffs; user accepts or rejects before applying.
4. **Fast feedback** — TTS starts reading the response while the LLM is still generating.
5. **Extensible** — phased architecture with stub interfaces so each layer can be upgraded independently.

## Requirements

### Functional

- Wake word detection ("Hey Harness" — custom trained in Phase 4; `hey_jarvis` placeholder until then; temporarily disable-able during stabilization)
- Continuous voice-to-text transcription (RealtimeSTT + faster-whisper large-v3)
- Code LLM queries with file context and repo map (Ollama + Qwen2.5-Coder:14b)
- SEARCH/REPLACE edit parsing with fuzzy fallback and syntax validation
- Diff view for accepting/rejecting edits (Monaco Diff Editor in Phase 3a)
- Text-to-speech response readback (Kokoro-82M, sentence-split for streaming)
- File browser (QTreeView + QFileSystemModel)
- Monaco code editor with syntax highlighting (Phase 2b)
- Git auto-commit on accepted changes (gitpython)
- Tree-sitter repo map for richer LLM context (Phase 3b)

### Non-Functional

- Runs on RTX 4080 Laptop 12GB VRAM — VRAM budget ~11.5GB
- End-to-end latency: 7-17 seconds (stop speaking → diff visible)
- First TTS word: 4-7 seconds with streaming
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
| Language | Python | 3.11.x | 3.12+ breaks webrtcvad/OpenWakeWord |
| UI | PyQt6 | >=6.6.0,<6.8.0 | GPL v3 |
| Browser engine | PyQt6-WebEngine | >=6.6.0,<6.8.0 | Separate pip package |
| Code editor | Monaco Editor | 0.52.0 | AMD build only |
| STT | RealtimeSTT | >=0.3.104 | Semi-abandoned — thin adapter pattern |
| Whisper backend | faster-whisper (via ctranslate2) | ctranslate2==4.4.0 | Pin: >=4.5.0 needs cuDNN 9.2 |
| Wake word | OpenWakeWord | >=0.6.0 | CC BY-NC-SA 4.0 on pre-built models |
| LLM | Ollama + Qwen2.5-Coder:14b | ollama>=0.2.0 | Pin Ollama ≤0.19.x (0.20.x VRAM regression) |
| TTS | Kokoro | >=0.9.0 | CPU-only (82M params) — needs espeak-ng |
| GPU compute | PyTorch + CUDA 12.1 | torch==2.3.0+cu121 | Must install FIRST |
| Git | gitpython | >=3.1.40 | |
| Code intel | tree-sitter | >=0.21.0 | Phase 3b |

## Licensing

- **PyQt6**: GPL v3 — must open-source under GPL v3 OR buy Riverbank commercial license (~£350/dev/yr)
- **OpenWakeWord pre-built models**: CC BY-NC-SA 4.0 — cannot distribute commercially; custom-trained models have no restriction
- **All other deps**: MIT, Apache 2.0, or BSD-3 — fully GPL v3 compatible

## Reference Projects

| Project | Relevance |
|---|---|
| [KoljaB/RealtimeSTT](https://github.com/KoljaB/RealtimeSTT) | STT library — semi-abandoned, thin adapter pattern |
| [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) | Queue-based pipeline architecture |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | SEARCH/REPLACE edit format + repo-map concept |
| [signupss/ai-code-sherlock](https://github.com/signupss/ai-code-sherlock) | PyQt6 3-panel IDE reference |
