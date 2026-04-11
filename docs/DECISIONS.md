# Architecture Decisions

> Key decisions and their rationale. Each entry records what was decided, why, and what alternatives were rejected.

---

## ADR-001: Standalone app instead of VS Code extension

**Decision**: Build a standalone desktop app that replaces VS Code entirely.

**Rationale**: Full control over the voice pipeline, no extension API limitations, direct access to audio devices, and ability to customize every UI element. A VS Code extension would be constrained by the extension sandbox, limited to the webview API for custom UI, and would fight with VS Code's own audio handling.

**Alternatives rejected**: VS Code extension, Electron app (too heavy on top of PyQt6's Chromium).

---

## ADR-002: PyQt6 + Monaco via QWebEngineView

**Decision**: Use PyQt6 for the native shell and embed Monaco Editor via QWebEngineView.

**Rationale**: PyQt6 provides a mature, well-documented desktop framework with native system tray, menus, and file dialogs. Monaco provides professional code editing with syntax highlighting for all languages, minimap, intellisense stubs, and diff view — all for free. QWebEngineView embeds Chromium which can run Monaco.

**Trade-offs**: GPL v3 license requirement from PyQt6. Chromium adds ~200MB to install size.

---

## ADR-003: Localhost HTTP server for Monaco (not file:// or app://)

**Decision**: Serve Monaco assets via `http.server.HTTPServer` on `127.0.0.1:<random_port>` in a daemon thread.

**Rationale**: Proven in Phase 0 POC. The two alternatives both failed:
- `file://` blocks Monaco Web Workers (same-origin policy — workers can't load from file:// URLs)
- `app://` custom scheme via `QWebEngineUrlSchemeHandler` loaded the page but rendered blank (suspected QBuffer garbage collection issue — content was served but Chromium couldn't read it)

**Risk**: Localhost port is accessible to other processes on the same machine. Mitigated by binding to `127.0.0.1` only and serving read-only Monaco assets (no user data exposed).

---

## ADR-004: RealtimeSTT with thin adapter pattern

**Decision**: Use RealtimeSTT as the STT library but wrap it in a thin adapter (`voice_input.py`) with a minimal public API.

**Rationale**: RealtimeSTT bundles VAD + faster-whisper + microphone capture in one library, reducing integration work. However, it's semi-abandoned (infrequent updates, aging dependencies). The thin adapter pattern means only `voice_input.py` imports RealtimeSTT — if it breaks or a better library appears, only that one ~80-line file needs rewriting.

**Adapter API**: `start()`, `stop()`, `pause()`, `resume()`, `on_text(callback)` — nothing else.

---

## ADR-005: Aider-style SEARCH/REPLACE edit format

**Decision**: Use SEARCH/REPLACE blocks (the format from Aider) for LLM code edits.

**Rationale**: Well-tested format that Qwen2.5-Coder understands reliably. More precise than unified diffs (LLMs often generate invalid diffs). Easier to parse with regex. Each block is self-contained — no line numbers to get wrong.

**Parser details**: Lenient regex (6-8 chevrons, case-insensitive), strip enclosing fenced code blocks, fuzzy fallback via `difflib.SequenceMatcher` at 0.85 threshold. `EditResult.used_fuzzy` flag indicates when fuzzy matching was used, enabling UI warnings.

---

## ADR-006: Coordinator message format with future-proof stubs

**Decision**: From Phase 1, the coordinator uses `{"query": str, "context": str|None, "repo_map": str|None}` message dicts with stub pipeline stages (`context_assembler`, `response_splitter`).

**Rationale**: Red Team Agent 11 identified that a plain-string pipeline in Phase 1 would require a coordinator rewrite in Phase 3 when context and repo maps are added. By specifying the full message format and stub stages from day 1, later phases activate existing code rather than refactoring.

---

## ADR-007: TTS returns List[Tuple[str, bytes]]

**Decision**: `tts.speak(text)` returns a list of `(sentence, wav_bytes)` tuples, not a single audio buffer.

**Rationale**: Phase 4 adds arrow-key navigation to replay individual sentences of an AI response. This requires the TTS output to be sentence-addressable from the start. Building it as a single buffer in Phase 1 and splitting it later would require re-synthesis or complex audio slicing.

---

## ADR-008: int8_float16 whisper (not fp16)

**Decision**: Use `compute_type="int8_float16"` for faster-whisper large-v3.

**Rationale**: VRAM budget is 12GB total. fp16 whisper uses ~3.1GB, which when combined with a local LLM would leave little headroom. int8_float16 uses ~1.5GB — a safer choice regardless of what else shares the GPU. (Originally chosen to fit alongside Qwen2.5-Coder:14b ~9 GB; still preferred after LLM moved to cloud in ADR-011.)

**Quality impact**: Minimal — int8 quantization on Whisper has negligible WER degradation for English speech.

---

## ADR-009: --in-process-gpu Chromium flag

**Decision**: Set `QTWEBENGINE_CHROMIUM_FLAGS="--in-process-gpu"` to collapse the GPU process into the main process.

**Rationale**: The Razer Blade 16 has dual GPUs (Intel iGPU + NVIDIA RTX 4080 via Optimus). Chromium's default multi-process GPU architecture fails to create a shared context for virtualization on this hardware. `--in-process-gpu` bypasses the IPC shared context issue by running GPU operations in the main process.

**Alternatives rejected**: `--disable-gpu` (removes all GPU acceleration), `--use-gl=swiftshader` (incompatible with `--disable-gpu`), various `--disable-gpu-*` combinations (all failed).

**Additional requirement**: Python.exe must be pinned to "High Performance (NVIDIA)" in Windows Graphics Settings to avoid Intel iGPU selection.

---

## ADR-010: Python 3.11 requirement

**Decision**: Require Python 3.11.x — do not support 3.12+.

**Rationale**: Two critical dependencies lack Python 3.12 wheels:
- `webrtcvad` (used by RealtimeSTT for voice activity detection) — no 3.12 wheels, compile fails
- `openwakeword` — compatibility issues with 3.12+ numpy/onnxruntime versions

The `webrtcvad-wheels` variant provides pre-built Windows wheels for 3.11 but not 3.12.

---

## ADR-011: Gemini 2.5 Pro via OpenAI SDK (replacing Ollama)

**Decision**: Replace local Ollama + Qwen2.5-Coder:14b with hosted Gemini 2.5 Pro, accessed via the `openai` Python SDK pointed at Google's OpenAI-compatible endpoint.

**Rationale**: Running both faster-whisper STT (~1.5 GB) and Qwen2.5-Coder:14b (~9 GB) on a 12 GB GPU left only ~1.5 GB headroom, causing VRAM pressure and slow inference. Moving the LLM to a hosted service frees ~9 GB VRAM, dramatically improves inference speed, and unlocks a much larger context window (100k chars vs 4k tokens).

**Why Gemini 2.5 Pro**: Strong coding performance, generous free tier, 1M token context window. The OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) means the `openai` SDK works directly — no Gemini-specific SDK needed.

**Why OpenAI SDK**: Maximum provider portability. If the user wants to switch to OpenAI, Anthropic (via proxy), or any OpenAI-compatible endpoint, only `MODEL` and `BASE_URL` constants need changing.

**API key management**: Persisted in QSettings (`"llm/api_key"`). Env var `GEMINI_API_KEY` as fallback. UI text field in AI panel's LLM Settings section. Coordinator emits `error_occurred` if no key is configured — no blocking dialog.

**Trade-off**: The app is no longer fully offline. STT and TTS remain local. The LLM requires an internet connection and an API key.

**Alternatives rejected**:
- Keep Ollama — VRAM too tight, inference too slow for interactive use
- Gemini Python SDK (`google-genai`) — less portable, extra dependency for same outcome
- Anthropic Claude — no OpenAI-compatible endpoint without a proxy
