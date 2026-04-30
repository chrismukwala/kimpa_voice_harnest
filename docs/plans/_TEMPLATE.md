# Plan: <feature name>

> Plan-before-build template (Phase H5.1). Copy this file to
> `docs/plans/<short-slug>.md` for any non-trivial feature or refactor,
> fill in every section, then execute the plan in a fresh agent session.

## 1. Problem statement

What user-visible behaviour or constraint is missing today? Why now?
Link to the source issue, red-team finding, or review report entry.

## 2. Test list (Red-Green-Refactor)

Failing tests to write **first**, before any production code:

- [ ] `tests/test_<module>.py::test_<behaviour>` — describe the assertion.
- [ ] …

Each bullet should map to one observable behaviour. No production code
ships without a corresponding test row above.

## 3. Module touch-list

Files this plan will create or modify, with rough line budgets so the
agent can spot scope creep early:

| Path | Change | Budget |
|------|--------|--------|
| `harness/<module>.py` | new function `foo()` | ~30 LOC |
| `tests/test_<module>.py` | 3 new tests | ~40 LOC |

## 4. Risks / known gotchas

Constraints from `AGENTS.md` and `.github/instructions/` that this
work might trip over:

- VRAM budget (12 GB) — does this load a new model?
- Qt main-thread / WebEngine flags — does this touch UI?
- Coordinator message shape — does this change the queue contract?
- Any pinned dependency (e.g. `ctranslate2 == 4.4.0`) we must not bump?

## 5. Success criteria

Concrete commands the agent will run to declare the work done:

```bash
python -m pytest tests/ -v
python scripts/preflight.py
# any feature-specific smoke test
```

All commands must exit ``0`` and the new tests in section 2 must pass.

## 6. Out of scope

Explicitly list adjacent improvements this plan will **not** make, to
keep the diff reviewable.
