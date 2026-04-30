---
description: 'Red-Green-Refactor TDD discipline for Voice Harness production code'
applyTo: 'harness/**/*.py, ui/**/*.py'
---

# TDD Instructions

Production code under `harness/` and `ui/` is written test-first. Skip these rules only for
trivial typo fixes.

## Red → Green → Refactor

- **Red**: write a pytest test in `tests/` that names the new behavior and currently fails.
  Run it and confirm it fails for the *right* reason (assertion, not import error).
- **Green**: write the minimum production code to make that test pass. Resist adding
  unrequested features, branches, or abstractions while green.
- **Refactor**: clean up names, extract helpers, remove duplication, with all tests still green.

## What makes a good failing test

- Names a single observable behavior (`test_coordinator_emits_response_for_query`).
- Asserts on return values, emitted signals, or recorded calls — not on internal attributes.
- Uses the smallest fixture that exercises the seam (pure function > widget > full pipeline).
- Mocks heavy dependencies so it runs in <100 ms: OpenAI SDK, faster-whisper, WebRTC VAD,
  Kokoro, sounddevice, Qt audio output, real network, real filesystem outside `tmp_path`,
  and git operations against the real repo.
- For UI behavior, uses the `qapp` fixture and `@pytest.mark.ui` marker.

## Regression discipline

- When fixing a bug, first add a test that reproduces it (fails on `main`), then fix.
- Keep the regression test even after the fix lands — it documents the contract.

## Verification before commit

- Run the narrow target while iterating: `python -m pytest tests/test_<module>.py -q`.
- Run the full suite before committing: `python -m pytest tests/ -v`. All tests must pass.
- Report any test or manual check that could not be run, and why.

## Cross-references

- General Python correctness: [python-correctness.instructions.md](python-correctness.instructions.md).
- Test-file conventions: [tests.instructions.md](tests.instructions.md).
