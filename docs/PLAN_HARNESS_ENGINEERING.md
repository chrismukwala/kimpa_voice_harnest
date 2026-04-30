# Harness Engineering Implementation Plan

> Adapting the [harness-engineering field guide](https://github.com/jrenaldi79/harness-engineering)
> (and adjacent best practices from OpenAI, Anthropic, Augment, Factory.ai) to the Voice Harness
> repo. Scope: only practices that meaningfully improve *this* codebase given its current state.

## Guiding principle

> Mechanical enforcement > path-scoped rules > prose. "Agents write the code; linters write the law."

Voice Harness already follows several harness practices (TDD-required `AGENTS.md`, pinned
constraints, Judge / Red Team subagents ≈ adversarial review, conventions doc). This plan closes
the gaps without over-engineering.

---

## Phase H1 — Mechanical enforcement (highest ROI)

Goal: make it impossible to commit code that violates the rules already documented in
[AGENTS.md](../AGENTS.md) and [.github/copilot-instructions.md](../.github/copilot-instructions.md).

### H1.1 Pre-commit hook

Install a Python pre-commit hook (Windows-friendly, no Node required) that runs in <5s:

| Step | Check | Blocks? |
|------|-------|---------|
| 1 | `python -m pytest tests/ -q` (with SHA cache) | yes, on test failure |
| 2 | Secret scan (regex: API keys, OpenAI/Gemini tokens, private keys) | yes |
| 3 | File-size check (default 400 lines for `harness/**`, `ui/**`, `tests/**`) | yes |
| 4 | Forbidden-pattern scan (`git add .`, `git add -A`, bare `except:`, `file://` Monaco URLs, `compute_type="float16"`) | yes |
| 5 | Drift warning: `harness/*.py` changed without `docs/PROGRESS.md` touch | warn only |

Implementation:
- `scripts/hooks/pre_commit.py` — single Python entry point.
- `scripts/install_hooks.py` — copies/symlinks into `.git/hooks/pre-commit`.
- `scripts/lib/check_secrets.py`, `check_file_sizes.py`, `check_forbidden.py` — each with a top-of-file `CONFIG` dict (configurable, not hardcoded).
- SHA-based test cache: write `HEAD` to `.test-passed` after green run; skip pytest when SHA matches and no `.py` changed since.

### H1.2 Pre-push hook

| Step | Check | Blocks? |
|------|-------|---------|
| 1 | Full `pytest tests/ -v` (skipped if `.test-passed` matches `HEAD`) | yes |
| 2 | `pip-audit` against `requirements.txt` | warn only |

### H1.3 Smart test caching

Per-developer `.test-passed` file (gitignored) storing the SHA of the last commit where the
suite went green. Avoids re-running tests on every push when nothing changed.

**Deliverables:** `scripts/hooks/`, `scripts/lib/`, `scripts/install_hooks.py`, `.test-passed` in
`.gitignore`, `docs/SETUP.md` updated with `python scripts/install_hooks.py` step.

---

## Phase H2 — Path-scoped instructions (progressive disclosure)

Goal: split the single `python-correctness.instructions.md` into multiple focused files that
auto-load only when relevant, keeping the agent's context lean.

Create under `.github/instructions/` (each with YAML frontmatter `applyTo:`):

| File | applyTo | Purpose |
|------|---------|---------|
| `python-correctness.instructions.md` | `**/*.py` | (existing) |
| `tdd.instructions.md` | `harness/**/*.py, ui/**/*.py` | Red-Green-Refactor rules, mock heavy deps, what makes a "good" failing test |
| `audio-stack.instructions.md` | `harness/voice_input.py, harness/tts.py, harness/audio_*.py, tools/test_*.py` | Python 3.11, ctranslate2 4.4.0 pin, `int8_float16`, sounddevice/VAD details, espeak-ng |
| `qt-webengine.instructions.md` | `ui/**/*.py, phase0_poc/**/*.py, main.py` | `--in-process-gpu`, `QTWEBENGINE_DISABLE_SANDBOX=1`, localhost-HTTP-only Monaco, env vars before Qt imports |
| `coordinator-contract.instructions.md` | `harness/coordinator.py, harness/code_llm.py, tests/test_coordinator.py, tests/test_code_llm*.py` | message shape `{"query","context","repo_map"}`, SEARCH/REPLACE format, `tts.speak() -> List[Tuple[str, bytes]]` |
| `tests.instructions.md` | `tests/**/*.py` | mock policy, `qapp` fixture, `@pytest.mark.ui` marker, no real network/audio |

**Deliverables:** 5 new instructions files. Each ≤60 lines. Move duplicated constraints out of
`AGENTS.md` and `copilot-instructions.md` into the relevant scoped file (single source of truth).

---

## Phase H3 — Documentation hygiene

Goal: keep `AGENTS.md` and `docs/` in sync with code without manual effort.

### H3.1 Auto-generated module index

Add `<!-- AUTO:modules -->` ... `<!-- /AUTO:modules -->` markers in [AGENTS.md](../AGENTS.md)
"Project layout" section. A Python script (`scripts/lib/generate_docs.py`) walks `harness/`,
`ui/`, `tools/`, `tests/`, `setup/`, extracts the module-level docstring (first line), and
regenerates the table.

Currently missing from the layout block: `harness/edit_applier.py`, `harness/git_ops.py`,
`harness/llm_tools.py`, `harness/model_manager.py`, `harness/repo_map.py`, plus several
`tests/test_*.py` files. The generator fixes drift permanently.

### H3.2 Drift detector

`scripts/lib/validate_docs.py` — exits non-zero if any `harness/*.py` changed in the staged diff
without a matching note in `docs/PROGRESS.md` (warning only in pre-commit; can be hard-fail in
CI later).

### H3.3 Trim & index AGENTS.md

Current `AGENTS.md` is ~150 lines — within budget. Action: keep ≤200 lines and ensure it ends
with a **Docs Map** linking to:

| Topic | File |
|-------|------|
| Architecture | [docs/ARCHITECTURE.md](ARCHITECTURE.md) |
| Conventions | [docs/CONVENTIONS.md](CONVENTIONS.md) |
| Decisions | [docs/DECISIONS.md](DECISIONS.md) |
| Setup | [docs/SETUP.md](SETUP.md) |
| Progress | [docs/PROGRESS.md](PROGRESS.md) |
| Audio UX plan | [docs/PLAN_AUDIO_UX.md](PLAN_AUDIO_UX.md) |
| Review report | [docs/REVIEW_REPORT.md](REVIEW_REPORT.md) |
| Red Team report | [docs/RED_TEAM_REPORT.md](RED_TEAM_REPORT.md) |

**Deliverables:** marker pairs in `AGENTS.md`, `scripts/lib/generate_docs.py`,
`scripts/lib/validate_docs.py`, Docs Map block.

---

## Phase H4 — Quality gates as tests

Goal: encode the "complexity red flags" from the field guide as automated checks rather than
prose.

| Gate | Limit | Where enforced |
|------|-------|---------------|
| File length | 400 lines (harness/ui), 600 (tests) | pre-commit (H1.1) |
| Function length | 60 lines | new test in `tests/test_repo_hygiene.py` using `ast` |
| Imports per module | ≤15 | same |
| Bare `except:` | banned | `check_forbidden.py` |
| `print(` in `harness/`, `ui/` | banned (logging only) | `check_forbidden.py`, allowlist `tools/`, `scripts/` |

`tests/test_repo_hygiene.py` walks the AST of `harness/` and `ui/` and asserts these
invariants — runs as part of the normal pytest suite, so every developer (and CI) catches it.

---

## Phase H5 — Spec-driven & subagent workflow alignment

Already partly in place via the existing `.github/agents/judge.agent.md` and `redteam.agent.md`.
Add:

### H5.1 Plan-before-build template

`docs/plans/_TEMPLATE.md` — every non-trivial feature gets a plan file with:
1. Problem statement
2. Test list (failing tests to write first)
3. Module touch-list with line budgets
4. Risks / known gotchas
5. Success criteria (commands the agent will run to verify)

This formalises Boris Cherny's "spec → execute in fresh session" pattern that the codebase
already half-uses (`PLAN_AUDIO_UX.md`).

### H5.2 Session-start validation

A short `scripts/preflight.py` an agent (or human) runs at session start:
- check Python version is 3.11.x
- check `ctranslate2 == 4.4.0`
- check espeak-ng on PATH
- check `nvcc` on PATH
- print active venv, last commit SHA, `pytest --collect-only` count

Surfaces drift between local env and the pinned constraints in `AGENTS.md`.

---

## Phase H6 — Readiness self-assessment (optional, low priority)

Adapt the 8-pillar / 5-level rubric to a Voice-Harness-flavoured checklist in
`docs/READINESS.md`. Mostly documentation; gives future contributors a yardstick. Defer until
H1–H4 are landed.

---

## Out of scope (don't implement)

- Node-based tooling (`lint-staged`, `prettier`, `eslint`) — repo is Python-only.
- BMAD / Superpowers / Claude Code plugin install — Voice Harness uses GitHub Copilot in VS Code, not Claude Code; the plugin layer doesn't apply. Reuse the *patterns*, not the plugins.
- Git worktree parallelism — single-developer project, no current need.
- Multi-LLM adversarial review tooling — already covered by the Judge / Red Team subagents.
- `<!-- AUTO:tree -->` ASCII tree — workspace tree is small enough to maintain by hand once H3.1 lands.

---

## Sequencing & TDD discipline

Each phase ships behind failing tests where possible:

1. **H1.1 first** — write `tests/test_hooks.py` that imports `scripts/lib/check_forbidden.py` and asserts it flags a known-bad string. Then implement. Then wire into `.git/hooks/pre-commit`.
2. **H4 next** — `tests/test_repo_hygiene.py` is pure Python and immediately catches existing violations; fix or grandfather them via an `ALLOWLIST` constant.
3. **H2** — instructions files have no tests; just verify Copilot picks them up by inspecting the agent context window.
4. **H3** — `tests/test_doc_generation.py` round-trips the AUTO markers (generate → parse → re-generate → assert idempotent).
5. **H5** — template + preflight script.

After every phase: run `python -m pytest tests/ -v`, update [docs/PROGRESS.md](PROGRESS.md), commit with `chore: harness Hx.y …`.

---

## Estimated phase order of value

| Phase | Effort | Value | Order |
|-------|--------|-------|-------|
| H1 hooks + smart cache | M | very high | 1 |
| H4 hygiene tests | S | high | 2 |
| H2 path-scoped instructions | S | high | 3 |
| H3 doc generation + drift | M | medium | 4 |
| H5 plan template + preflight | S | medium | 5 |
| H6 readiness rubric | S | low | 6 |

---

## Open questions for the user

1. Hard-block on file-size violations, or warn only at first?
2. Should pre-push run the *full* suite (including `@pytest.mark.ui`) or only the fast lane?
3. OK to add `pip-audit` to `requirements.txt` (dev only)?
4. Want a CI workflow (`.github/workflows/ci.yml`) running the same checks on PRs, or keep it local-only for now?
