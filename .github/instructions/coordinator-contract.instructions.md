---
description: 'Coordinator + LLM contracts: message shape, SEARCH/REPLACE blocks, TTS chunk shape'
applyTo: 'harness/coordinator.py, harness/code_llm.py, harness/llm_tools.py, harness/edit_applier.py, tests/test_coordinator.py, tests/test_code_llm.py, tests/test_code_llm_tools.py, tests/test_llm_tools.py, tests/test_edit_applier.py'
---

# Coordinator Contract Instructions

The coordinator wires STT → context assembly → LLM → response splitter → TTS. Its contracts
are load-bearing; downstream UI, navigation, and edit-apply logic depend on them.

## Inbound message shape

Every message the coordinator receives must be a dict with exactly these keys:

```python
{"query": str, "context": str | None, "repo_map": str | None}
```

- `query`: the user's transcribed utterance (non-empty string).
- `context`: optional concatenated file context (already trimmed to fit the LLM window).
- `repo_map`: optional repo-map summary string.

Never accept a bare string. Never add extra keys without updating both `coordinator.py` and
`tests/test_coordinator.py` in the same change.

## LLM edit format

- The LLM emits Aider-style **SEARCH/REPLACE** blocks for code changes, plus prose for the
  spoken response. The parser in [harness/code_llm.py](../../harness/code_llm.py) splits
  edits from prose; do not invent a different separator.
- Edits apply via [harness/edit_applier.py](../../harness/edit_applier.py); accepted edits
  are auto-committed via [harness/git_ops.py](../../harness/git_ops.py).

## TTS chunk shape

`harness/tts.py::speak(text)` MUST return `List[Tuple[str, bytes]]`:

- one entry per spoken sentence,
- `str` = the sentence text (for highlighting / arrow-key navigation),
- `bytes` = the WAV payload for that sentence.

Never collapse to a single buffer. Phase 4 navigation, captioning, and rate control all rely
on per-sentence chunks.

## LLM provider

Currently **Gemini 2.5 Flash Lite** via the OpenAI SDK (hosted, ~100 k char context). When
swapping providers, keep the OpenAI-SDK-compatible surface so tests stay valid.

## Cross-references

- TDD: [tdd.instructions.md](tdd.instructions.md).
- Audio chunk consumers: [audio-stack.instructions.md](audio-stack.instructions.md).
