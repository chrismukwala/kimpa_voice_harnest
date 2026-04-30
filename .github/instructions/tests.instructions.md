---
description: 'Test-file conventions: mock policy, qapp fixture, no real network or audio'
applyTo: 'tests/**/*.py'
---

# Test File Instructions

Tests must be fast, deterministic, and runnable on any machine — no GPU, no microphone, no
network. The full suite should complete in seconds.

## Mock policy

Always mock these dependencies in unit tests:

- `openai` SDK clients (Gemini access).
- `faster_whisper` `WhisperModel`.
- `webrtcvad.Vad`.
- `kokoro` and any TTS engine handle.
- `sounddevice` (`InputStream`, `OutputStream`, `query_devices`).
- Qt audio output (`QAudioSink`, `QMediaPlayer`).
- `git.Repo` mutations against the real working copy — use `tmp_path` git repos when needed.
- Filesystem mutation outside `tmp_path` / `tmp_path_factory`.

Tests that depend on real audio hardware, GPU, or live HTTP calls do not belong here — put
them in `tools/test_*.py` as manual smoke checks.

## Fixtures and markers

- UI tests use the shared `qapp` fixture from `tests/conftest.py` and the `@pytest.mark.ui`
  marker. Do not instantiate `QApplication` yourself.
- Use `tmp_path` / `tmp_path_factory` for any file or repo creation.
- Use `monkeypatch` for environment variables and `os` shims.

## Test shape

- One behavior per test. Name the test for the observable outcome
  (`test_split_sentences_preserves_question_marks`), not the implementation
  (`test_re_split_call`).
- Arrange / Act / Assert structure with blank lines separating the sections when it aids
  readability.
- Prefer parametrize over loops when checking many cases of the same behavior.
- Assert on return values, emitted signals, or recorded mock calls — not on private state.

## Speed and determinism

- Each test should run in <100 ms. Mark anything slower with `@pytest.mark.slow` and document
  why it cannot be faster.
- Seed any randomness explicitly. Avoid wall-clock comparisons; freeze time with fakes.

## Running

- Narrow during iteration: `python -m pytest tests/test_<module>.py -q`.
- Full sweep before commit: `python -m pytest tests/ -v` — must be green.

## Cross-references

- TDD workflow: [tdd.instructions.md](tdd.instructions.md).
- Python correctness: [python-correctness.instructions.md](python-correctness.instructions.md).
