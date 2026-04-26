# Coding Conventions

## Language & Style

- Python 3.11 — use 3.11 features but nothing 3.12+
- Follow PEP 8 with 100-char line limit
- Use double quotes for strings (except where single quotes avoid escaping)
- Type hints on public function signatures; skip on internal/obvious locals
- Docstrings on modules and public classes/functions only — keep them short (1-3 lines)

## File Structure

- One class per file when the class is substantial (>50 lines)
- Use `__init__.py` to mark packages — keep them empty unless re-exporting
- Imports: stdlib → third-party → local, separated by blank lines
- Lazy imports for heavy libraries such as faster-whisper, WebRTC VAD, Kokoro, and torch to keep startup fast

## Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private/internal: prefix with `_`

## Git

- Commit messages: `type: short description` — types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- Stage specific files — never `git add .` or `git add -A`
- No `--force` pushes
- LF line endings enforced (`.gitattributes`: `* text=auto eol=lf`)

## Architecture Patterns

### Verifiable Python Design

Python changes also follow `.github/instructions/python-correctness.instructions.md`.

Prefer a functional-core, imperative-shell shape when it fits naturally: deterministic parsing,
validation, formatting, playback policy, edit matching, repo-map shaping, and VAD policy should be
easy to call from tests with explicit inputs and outputs. Keep side effects at focused boundaries,
especially Qt widgets/signals, threads, audio devices, GPU/model loading, filesystem edits, git, and
network clients.

Do not force functional style into PyQt lifecycles or hardware adapters when the existing class-based
boundary is clearer. The goal is verifiable behavior, not a blanket paradigm rewrite.

### Boundary Pattern
External libraries are kept behind focused module boundaries with minimal public APIs. The rest of the codebase should use those module APIs instead of importing heavy libraries directly.

Current adapters:
- `harness/voice_input.py` owns the sounddevice/WebRTC VAD/faster-whisper input pipeline
- `harness/tts.py` owns Kokoro synthesis
- `harness/code_llm.py` owns OpenAI-compatible Gemini calls

### Queue Pipeline
The coordinator uses a queue with dict messages. New pipeline stages are added as methods, not new threads. Signals connect the pipeline to the UI.

### Coordinator Message Format
Always: `{"query": str, "context": str | None, "repo_map": str | None}`. Never pass plain strings through the pipeline.

### TTS Return Type
`speak()` always returns `List[Tuple[str, bytes]]` — a list of (sentence, WAV data) pairs. Even if only one sentence, return a list. Phase 4 navigation depends on this.

## Error Handling

- Catch specific exceptions, not bare `except:`
- Pipeline errors emit `error_occurred` signal — never crash silently
- External service or hardware failures (Gemini unavailable, mic unavailable, output device unavailable) degrade gracefully with user-visible message
- Do NOT add error handling for scenarios that can't happen at the current phase

## Security

- LLM API keys must never be logged or committed
- SEARCH/REPLACE apply: `os.path.realpath()` check — target must resolve inside project root
- Never auto-edit `.env`, `*.pem`, `*.key`, `id_rsa*`, `.ssh/`, `.aws/`
- Scan added lines for `subprocess`, `eval`, `exec`, `os.system`, `__import__` — warn, don't block
- Git auto-commit: stage specific file only, run secret scanner before commit

## UI

- Dark theme: background `#1e1e1e`, text `#d4d4d4`, accent `#0e639c`
- Font: Consolas, monospace, 12px for editor, 11px for panels
- Status colors: idle=`#608b4e`, listening=`#4ec9b0`, processing=`#dcdcaa`, speaking=`#ce9178`

## Testing — Red/Green/Refactor TDD

This project follows a **Red → Green → Refactor** TDD workflow:

1. **Red**: Write a failing test that describes the desired behaviour.
2. **Green**: Write the minimum code to make the test pass.
3. **Refactor**: Clean up while keeping all tests green.

### Rules

- Every new feature or bug fix starts with a test — code without a test is unfinished.
- Run `python -m pytest tests/ -v` before committing. All tests must pass.
- Tests live in `tests/` mirroring `harness/` and `ui/` structure.
- Use `unittest.mock.patch` to isolate from heavy dependencies (OpenAI SDK, faster-whisper, WebRTC VAD, Kokoro, sounddevice).
- UI widget tests use the `qapp` fixture (session-scoped `QApplication`).
- Mark UI tests with `@pytest.mark.ui`.
- Tests must be fast — mock all I/O, network, and hardware. No real mic, GPU, or LLM calls in unit tests.
- Test file naming: `test_<module>.py` matching the source module.

### Test Commands

```bash
# Run all tests
python -m pytest tests/ -v

# Run only fast (non-UI) tests
python -m pytest tests/ -v -m "not ui"

# Run a single test file
python -m pytest tests/test_code_llm.py -v
```

## Documentation

- Update `docs/PROGRESS.md` after completing any phase or significant work
- Keep `AGENTS.md` accurate if project layout or constraints change
- No change-log prose in code comments — that's what git history is for
