# Copilot Instructions — Voice Harness

Standalone desktop voice-driven coding assistant: Python 3.11 + PyQt6 + Monaco Editor.
Local STT (faster-whisper) and TTS (Kokoro); hosted Code LLM (Gemini 2.5 Flash Lite).

## Universal rules

- **TDD discipline** — Red → Green → Refactor. Every feature/fix starts with a failing test.
  Run `python -m pytest tests/ -v` before committing; all tests must pass.
- **Code style** — PEP 8, 100-char line limit, double quotes, type hints on public functions,
  no bare `except:`, specific exceptions only.
- **Git hygiene** — stage specific files; never `git add .` or `git add -A`. Commit format: <!-- pragma: allow forbidden -->
  `type: description` (feat, fix, refactor, docs, test, chore).
- **Pre-commit hook** — installed via `python scripts/install_hooks.py`; it runs the test
  cache, secret scan, file-size limits, and forbidden-pattern checks. Do not bypass with
  `--no-verify`.
- **After changes** — update [docs/PROGRESS.md](../docs/PROGRESS.md).

## Path-scoped instructions (auto-load by file path)

Specific constraints live in [.github/instructions/](instructions/), each scoped via
`applyTo`:

| Scope | File |
|-------|------|
| Any Python source | [python-correctness.instructions.md](instructions/python-correctness.instructions.md) |
| `harness/`, `ui/` production code | [tdd.instructions.md](instructions/tdd.instructions.md) |
| Audio modules + STT/TTS tools | [audio-stack.instructions.md](instructions/audio-stack.instructions.md) |
| `ui/`, `phase0_poc/`, `main.py` | [qt-webengine.instructions.md](instructions/qt-webengine.instructions.md) |
| Coordinator + LLM + edit applier | [coordinator-contract.instructions.md](instructions/coordinator-contract.instructions.md) |
| `tests/` | [tests.instructions.md](instructions/tests.instructions.md) |

## Project documentation

[AGENTS.md](../AGENTS.md) is the entry point. Deep dives in [docs/](../docs/): architecture,
conventions, decisions, setup, progress, plans.
