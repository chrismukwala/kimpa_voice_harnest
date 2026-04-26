---
description: 'Python correctness guidance for test-first, verifiable Voice Harness changes'
applyTo: '**/*.py, tests/**/*.py'
---

# Python Correctness Instructions

Use these rules when changing Python source or tests in Voice Harness.

## Design Posture

- Prefer a functional-core, imperative-shell design where it fits naturally.
- Put deterministic transformations and policy decisions in small functions that accept explicit
  inputs and return explicit outputs.
- Keep side effects at module boundaries: Qt signals/widgets, audio devices, GPU/model loading,
  file edits, git operations, environment variables, and network calls.
- Do not force functional style into PyQt object lifecycles, signal wiring, thread ownership, or
  hardware adapters when the existing object-oriented boundary is clearer.
- Prefer dataclasses, enums, and named result objects when they make invalid states harder to
  represent or make tests easier to read.

## Test-First Workflow

- Start every feature or bug fix with a failing pytest test that names the behavior being added or
  protected.
- Test behavior and outcomes, not private implementation details.
- Add tests at the smallest useful layer first; add integration/UI coverage only when behavior
  crosses module boundaries.
- Use mocks for OpenAI SDK calls, faster-whisper, WebRTC VAD, Kokoro, sounddevice, Qt audio output,
  filesystem mutation outside tmp paths, and git operations.
- For hardware or audio behavior that cannot be fully automated, add unit tests around the policy
  seam and document the manual smoke check in the final response or progress notes.

## Verifiable Code

- Prefer explicit parameters over reading global state, process environment, or singleton objects
  inside business logic.
- Return values that tests can inspect instead of burying decisions in UI callbacks or emitted
  signals when a small policy helper would make the behavior testable.
- Keep parsing, formatting, validation, diff/edit matching, repo-map shaping, sentence splitting,
  playback policy, and VAD threshold decisions deterministic where possible.
- Use dependency injection for clients, model loaders, devices, clocks, and file-system access when
  a test would otherwise need real external resources.
- When fixing a bug, add a regression test that would have failed before the fix.

## Verification

- Run the narrowest relevant pytest target first while iterating.
- Before completing code changes, run `python -m pytest tests/ -v` unless the user explicitly asks
  for a narrower check or the environment cannot run it.
- Report any tests or manual checks that could not be run, including why.