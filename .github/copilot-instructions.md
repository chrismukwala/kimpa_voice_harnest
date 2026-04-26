# Copilot Instructions — Voice Harness

This is a standalone desktop voice-driven coding assistant built with Python 3.11, PyQt6, and Monaco Editor.

## Key constraints

- Python 3.11.x only — this is the validated target for the audio stack.
- PyTorch (CUDA 12.1) must be installed BEFORE any other dependency.
- `ctranslate2` is pinned to 4.4.0 — do not upgrade.
- Keep mic capture, WebRTC VAD, and faster-whisper details inside `harness/voice_input.py`.
- Coordinator messages are always `{"query": str, "context": str|None, "repo_map": str|None}`.
- `tts.speak()` must return `List[Tuple[str, bytes]]` — never a single buffer.
- Monaco is served via localhost HTTP server — never `file://` or custom URL schemes.
- Set `QTWEBENGINE_CHROMIUM_FLAGS="--in-process-gpu"` and `QTWEBENGINE_DISABLE_SANDBOX=1` before Qt imports.

## Code style

- PEP 8, 100-char line limit, double quotes.
- Type hints on public functions only.
- Catch specific exceptions — no bare `except:`.
- Stage specific files in git — never `git add .`.
- Commit format: `type: description` (feat, fix, refactor, docs, test, chore).

## TDD workflow

- **Red → Green → Refactor** — every feature/fix starts with a failing test.
- For Python changes, follow `.github/instructions/python-correctness.instructions.md`.
- Run `python -m pytest tests/ -v` before committing — all tests must pass.
- Mock heavy dependencies (OpenAI SDK, faster-whisper, WebRTC VAD, Kokoro, sounddevice) — tests must be fast.
- UI tests use the `qapp` fixture and `@pytest.mark.ui`.

## After changes

Update `docs/PROGRESS.md` with what was completed.

## Full documentation

See `AGENTS.md` (project root) and `docs/` directory for architecture, decisions, setup, and conventions.
