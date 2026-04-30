# Voice Harness Readiness Rubric

> **Phase H6 deliverable** of the [Harness Engineering plan](PLAN_HARNESS_ENGINEERING.md).
> Self-assessment yardstick for "how production-ready is the agent-coding harness for *this*
> repo". Adapted from the harness-engineering 8-pillar / 5-level model.
>
> Update this file when a pillar level changes. Bump scores up only with evidence (commit SHA,
> test run, or doc link). Bump down freely — drift is the default.

## Levels

| Level | Name | Meaning |
|-------|------|---------|
| 0 | **Absent** | Not implemented. Agents can violate the rule without any signal. |
| 1 | **Documented** | Rule exists in prose (`AGENTS.md`, instructions, plan). No automation. |
| 2 | **Tested** | Violation is caught by an automated test or check, but only if invoked manually. |
| 3 | **Enforced locally** | Violation is blocked by pre-commit / pre-push hook on the developer machine. |
| 4 | **Enforced in CI** | Same check runs on every push/PR in a hosted runner; cannot be skipped. |

Voice Harness target baseline: **Level 3 across all pillars**, Level 4 once a CI workflow lands
(see Out of scope / Open question 4 in `PLAN_HARNESS_ENGINEERING.md`).

## Pillars

### 1. Mechanical enforcement

Forbidden patterns, secret scanning, file-size limits, banned commands (`git add .`). <!-- pragma: allow forbidden -->

- **Current:** Level 3 — `scripts/hooks/pre_commit.py` + `scripts/hooks/pre_push.py` block on
  secrets, forbidden patterns (`bare except:`, `file://` Monaco URLs, `compute_type="float16"`,
  `print(` in `harness/`/`ui/`, `git add .`, `git add -A`), and file-size caps. <!-- pragma: allow forbidden -->
- **Gap to L4:** No `.github/workflows/ci.yml` yet.
- **Evidence:** `scripts/lib/check_secrets.py`, `check_forbidden.py`, `check_file_sizes.py`,
  `tests/test_hooks.py`.

### 2. Test discipline (TDD)

Red → Green → Refactor; every behaviour change ships behind a failing test first.

- **Current:** Level 3 — `pytest tests/ -q` runs in pre-commit (SHA-cached via
  `scripts/lib/test_cache.py`) and full suite in pre-push. 561+ tests, all green at last log.
- **Gap to L4:** No CI runner; relies on developer hooks.
- **Evidence:** `pytest.ini`, `.test-passed`, `tests/conftest.py`, `tests/test_hooks.py`,
  `.github/instructions/tdd.instructions.md`.

### 3. Documentation hygiene

`AGENTS.md` and `docs/` stay in sync with code without manual upkeep.

- **Current:** Level 3 — `scripts/lib/generate_docs.py` rewrites the AUTO module index;
  `scripts/lib/validate_docs.py` warns on `harness/*.py` staged without `docs/PROGRESS.md`.
- **Gap to L4:** Drift warning is warn-only; could be hard-fail in CI.
- **Evidence:** `tests/test_doc_generation.py`, `<!-- AUTO:modules -->` block in `AGENTS.md`.

### 4. Quality gates as tests

Function length, imports per module, banned constructs encoded as pytest assertions.

- **Current:** Level 3 — `tests/test_repo_hygiene.py` walks the AST of `harness/` and `ui/`
  asserting function ≤60 lines, top-level imports ≤15, no `print()`. Runs in pre-commit
  pytest cache.
- **Gap to L4:** No CI mirror.
- **Evidence:** `tests/test_repo_hygiene.py`, `.github/instructions/python-correctness.instructions.md`.

### 5. Path-scoped instructions (progressive disclosure)

Constraints auto-loaded only for the files they govern, keeping agent context lean.

- **Current:** Level 1 — 6 `.github/instructions/*.instructions.md` with `applyTo:` scopes.
  Pure documentation; correctness depends on Copilot honouring frontmatter.
- **Gap to L2+:** No automated test asserts each instructions file has valid frontmatter or
  that `applyTo` globs match real files. (`tests/test_instructions_files.py` does structural
  checks — sufficient for L2.)
- **Evidence:** `.github/instructions/`, `tests/test_instructions_files.py`.
- **Effective level:** **2** when counting the structural test.

### 6. Spec-driven & subagent workflow

Plan-before-build template; session-start env preflight; Judge / Red Team adversarial review.

- **Current:** Level 2 — `docs/plans/_TEMPLATE.md` + `scripts/preflight.py`
  (`scripts/lib/preflight.py` library) + `.github/agents/judge.agent.md` and `redteam.agent.md`.
  Preflight is opt-in (developer runs it manually at session start).
- **Gap to L3:** Preflight not wired into hooks (env drift currently silent).
- **Evidence:** `tests/test_preflight.py` (19 tests), `docs/REVIEW_REPORT.md`,
  `docs/RED_TEAM_REPORT.md`.

### 7. Dependency & environment pinning

Python 3.11.x, `ctranslate2 == 4.4.0`, CUDA torch installed first, espeak-ng + nvcc on PATH.

- **Current:** Level 2 — pins documented in `AGENTS.md` and `setup/install.py`;
  `scripts/preflight.py` checks them. `pip-audit` runs warn-only in pre-push.
- **Gap to L3:** Preflight is not blocking; nothing prevents committing a `requirements.txt`
  edit that raises `ctranslate2`.
- **Evidence:** `requirements.txt`, `setup/install.py`, `scripts/lib/preflight.py`,
  `tests/test_preflight.py`.

### 8. Adversarial review (Judge / Red Team)

Multi-perspective audits before declaring a phase done.

- **Current:** Level 1 — `.github/agents/judge.agent.md` (4 specialist judges) and
  `redteam.agent.md` (5 hostile critics) exist; outputs land in `docs/REVIEW_REPORT.md` and
  `docs/RED_TEAM_REPORT.md`. Invocation is manual.
- **Gap to L2:** No automated trigger; reports can go stale.
- **Evidence:** `docs/REVIEW_REPORT.md`, `docs/RED_TEAM_REPORT.md`.

## Scorecard

| Pillar | Level | Target | Status |
|--------|-------|--------|--------|
| 1 Mechanical enforcement | 3 | 4 | green, awaiting CI |
| 2 Test discipline | 3 | 4 | green, awaiting CI |
| 3 Documentation hygiene | 3 | 4 | green |
| 4 Quality gates | 3 | 4 | green |
| 5 Path-scoped instructions | 2 | 3 | acceptable; no CI value |
| 6 Spec-driven workflow | 2 | 3 | preflight opt-in |
| 7 Dependency pinning | 2 | 3 | preflight opt-in |
| 8 Adversarial review | 1 | 2 | manual cadence |

**Aggregate:** 19 / 32. Median pillar level **2.5**. The path to a clean L3 across the board is:

1. Wire `scripts/preflight.py` into `scripts/hooks/pre_commit.py` (cheap; lifts pillars 6 & 7).
2. Add `.github/workflows/ci.yml` mirroring pre-commit + pre-push (lifts 1–4 to L4).
3. Schedule the Judge agent to re-run on phase-completion commits (lifts 8 to L2).

These are deliberately deferred — not on the critical path for product work, and the local
hooks already catch regressions.

## Re-assessment cadence

- After every `chore: harness Hx.y` commit.
- After any change to `requirements.txt`, `pytest.ini`, or `.github/`.
- After every Judge / Red Team run that reports a regression.
