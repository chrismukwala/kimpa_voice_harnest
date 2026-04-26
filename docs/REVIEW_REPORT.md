# Voice Harness — Code Review Report
_Generated: 2026-04-11_

> Historical review artifact. Several findings were later addressed or superseded by Phase 5 and
> the 2026-04-26 documentation sync. Use `docs/PROGRESS.md` as the current source of truth for
> phase status and current priorities.

## Executive Summary
The codebase is structurally sound with a well-organised 230-test suite and clean constraint compliance in most areas, but **two runtime bugs have silently shipped**: the `DiffPanel` renders as a floating orphan window rather than an embedded panel, and TTS auto-advance (`play_all()`) is never called from the UI so only one sentence plays per button press. These must be fixed before Phase 4 can be declared stable.

## Overall Severity Matrix
| Dimension      | Severity | Judge                  |
|----------------|----------|------------------------|
| Test Quality   | WARN     | judge-tests            |
| Architecture   | WARN     | judge-architecture     |
| Conventions    | WARN     | judge-conventions      |
| Progress/Gaps  | WARN     | judge-progress         |

## Priority Action List

### P1 — CRITICAL (block progress / silent failure)

- [ ] **[TESTS]** `tests/test_edit_applier.py::TestApplyEditsFuzzy::test_major_whitespace_difference_rejects` — **has no assertion**. Test body ends with a comment; it always passes regardless of behaviour. This silently allows regression on the security-critical 0.85 fuzzy threshold. Add `assert result.success is False` (or appropriate assertion based on intended rejection behaviour).

---

### P2 — HIGH (fix before Phase 4 is declared done)

- [ ] **[PROGRESS]** `ui/main_window.py` — `DiffPanel` is constructed with no parent (`DiffPanel()`) and is **never added to the main window layout or splitter**. When `show_diff()` calls `self.show()`, Qt renders it as a free-standing top-level window. Add `self._diff_panel` to the central splitter (e.g., as a bottom pane below the editor).

- [ ] **[PROGRESS]** `ui/main_window.py::_on_tts_play_requested()` calls `self._tts_nav.play_current()`, which leaves `_auto_advance = False`. Auto-advance only starts when `play_all()` sets `_auto_advance = True`. TTS will play one sentence and stop. Replace with `self._tts_nav.play_all()` (or gate appropriately).

- [ ] **[TESTS]** `tests/test_tts.py::TestSpeak` — mock target `@patch("harness.tts.KPipeline", create=True)` is non-functional. `_get_pipeline()` does a local `from kokoro import KPipeline`, so the effective binding is `sys.modules['kokoro'].KPipeline`, not `harness.tts.KPipeline`. Additionally, the module-level `_pipeline` singleton is never reset between tests, making test-order affect results. Fix: patch `sys.modules['kokoro']` (or `patch.dict`) before the module re-imports, and reset `harness.tts._pipeline = None` in test teardown.

- [ ] **[TESTS]** `harness/code_llm.py::chat()` — **zero tests**. Context truncation (`_MAX_CONTEXT_CHARS = 12000`), `ConnectError`/`ReadTimeout` → `RuntimeError` conversion, the system prompt, model name/timeout constants, and `options={"num_ctx": 4096}` flowing into the Ollama client are all unverified. Add tests with a mocked `ollama.Client`.

- [ ] **[TESTS]** `harness/coordinator.py::accept_edits()` — **zero tests** for the most security-sensitive function in the codebase. The path-escape guard (`real_file.startswith(real_root + os.sep)`), file write, git commit, `edits_applied` signal, `error_occurred` on failure, and rejection when `project_root` is `None` are all untested.

- [ ] **[TESTS]** `ui/main_window.py::DiffPanel` — **zero tests** for the entire class. `show_diff()`, `_accept_btn`, `_reject_btn` and `_on_edits_proposed()` in `MainWindow` are completely untested. This is the primary user-facing contract for code edits.

---

### P3 — MEDIUM (fix in current phase)

- [ ] **[ARCHITECTURE/CONVENTIONS]** `harness/coordinator.py` ~line 192 — `except Exception as exc:` is a bare catch-all that hides programming errors. AGENTS.md requires specific exceptions. Change to `except (RuntimeError, ValueError, OSError) as exc:` or document as an intentional safety net with `# noqa: BLE001`.

- [ ] **[ARCHITECTURE]** `harness/coordinator.py::accept_edits()` — does **not** call `edit_applier.validate_path()`; security validation is reimplemented inline. The dedicated `validate_path()` function exists but is dead code in production. Future hardening of `validate_path()` will not apply to the coordinator. Delegate to `edit_applier.validate_path(file_path, self._project_root)` unconditionally at the top of `accept_edits()`.

- [ ] **[CONVENTIONS]** `harness/tts.py` line 4 — `import wave` is unused (WAV writing is done via `soundfile.write`). Remove it.

- [ ] **[CONVENTIONS]** `harness/coordinator.py` line ~16 — `import git as _git` (third-party) sits in the local-import group. Move it above the `from harness import ...` imports.

- [ ] **[CONVENTIONS]** `main.py` — import ordering: `from PyQt6...` (third-party) and `from ui...` / `from harness...` (local) are not separated by a blank line.

- [ ] **[CONVENTIONS]** Missing `-> None` return type annotations on public methods: `harness/coordinator.py` (`set_file_context`, `refresh_repo_map`, `clear_file_context`), `harness/tts.py` (`play_wav_bytes`), `ui/editor_panel.py` (`set_file`, `shutdown`), `ui/main_window.py` (`DiffPanel.show_diff`, `MainWindow.set_root_path`).

- [ ] **[TESTS]** `harness/coordinator.py::start()` — no test verifies the worker thread is spawned or that `state_changed("listening")` fires. Add at minimum one smoke test that calls `start()` and checks `_worker_thread.is_alive()`.

- [ ] **[TESTS]** `harness/coordinator.py::begin_tts_playback()` / `finish_tts_playback()` — the `"speaking"` ↔ `"listening"` state machine transitions that drive AiPanel feedback are not tested.

- [ ] **[TESTS]** `harness/coordinator.py::refresh_repo_map()` — no test for happy path (repo map generated and stored) or error path (`OSError` logged and swallowed).

- [ ] **[TESTS]** `harness/coordinator.py::reject_edits()` — no coverage at all (a trivial no-op today, but that makes a test trivial to add).

- [ ] **[TESTS]** `harness/tts_navigator.py::_build_word_intervals()` / `_advance_word_highlight()` — word-highlight timing logic has no direct unit tests; an off-by-one or division error would be silently tolerated.

---

### P4 — LOW (nice to fix, won't block progress)

- [ ] **[ARCHITECTURE]** `harness/coordinator.py::accept_edits()` fallback git path uses `os.path.basename(file_path)` (the prohibited pattern per constraint #14). Although this code path is only reached when `git.Repo()` itself fails, remove the fallback staging call entirely; log a warning and emit `edits_applied` without attempting `auto_commit`.

- [ ] **[ARCHITECTURE]** `harness/code_llm.py` — `REQUEST_TIMEOUT = 300.0` diverges from the 120 s stated in AGENTS.md constraint #11. Either align the value or update AGENTS.md to reflect the intentional 5-minute timeout.

- [ ] **[ARCHITECTURE]** `requirements.txt` — `gitpython>=3.1.40` appears twice (lines 32 and 35). Remove the duplicate.

- [ ] **[TESTS]** `tests/test_tts_navigator.py::test_play_all_auto_advances` uses `time.sleep(0.05)` to wait for a background thread — brittle on slow CI runners. Replace with a threading event or mock the worker thread.

- [ ] **[TESTS]** `tests/test_git_ops.py::test_detects_git_repo` calls `subprocess.run(["git", "init", ...])` without guarding against systems where `git` is not on PATH. Add `pytest.importorskip` or a `shutil.which("git")` skipif.

- [ ] **[CONVENTIONS]** Missing or thin docstrings on public functions: `harness/audio_settings.py` (6 methods), `harness/coordinator.py` (`pause_listening`, `resume_listening`, `clear_file_context`), `ui/main_window.py` (`MainWindow` class), `main.py` (`main()`).

- [ ] **[CONVENTIONS]** `ui/ai_panel.py::set_audio_devices` — `selected_input` and `selected_output` params have no type annotation. Add `Optional[int] = None`.

- [ ] **[CONVENTIONS]** `ui/editor_panel.py` stdlib imports not in alphabetical order within group.

- [ ] **[PROGRESS]** `docs/PROGRESS.md` Phase 4 detailed log is truncated mid-bullet. Implemented features (`stop()`, `set_speed()`, word-highlight timer, keyboard shortcuts, `playback_finished` signal) are not documented. Complete the log.

- [ ] **[TESTS]** `ui/ai_panel.py::set_recording_active()` recording-dot animation and visibility logic is untested. `highlight_word()` is also untested.

---

## Context for Fix Agent

**Active phase:** Phase 4 (STABILIZING) — the last fully-completed phase is 3b.

**Do NOT change:**
- `ctranslate2==4.4.0` pin in `requirements.txt`
- The `--in-process-gpu` Chromium flag in `main.py`
- The localhost HTTP serving strategy in `editor_panel.py`
- The `harness/voice_input.py` thin-adapter boundary (only file that imports RealtimeSTT)
- Coordinator message format `{"query", "context", "repo_map"}` — ADR-006

**Load-bearing constraints (verified passing):**
- Coordinator `_context_lock` protects `_current_file_content`, `_current_file_path`, `_repo_map` — DO NOT refactor these without preserving the lock
- `tts.speak()` return type `List[Tuple[str, bytes]]` — required for TtsNavigator; do not change the signature
- `edit_applier._FUZZY_THRESHOLD = 0.85` — DO NOT lower; the P1 test fix must assert False (rejection) for inputs below this threshold
- `repo_map._MAX_MAP_CHARS = 4000` — hard budget for 4096-token LLM context window
- Thread safety: `TtsNavigator._play_worker()` must remain a daemon thread

**Deferred features (out of scope for this fix pass):**
- Suspicious code scan / secret scanner / `ast.parse` gate (Phase 3a deferred)
- Wake word OpenWakeWord integration (Phase 4 future work)
- Hardware validation (requires physical device)

---

## Raw Sub-Agent Reports

<details>
<summary>Test Judge Report (judge-tests)</summary>

**Overall Verdict: WARN**









## Raw Sub-Agent Reports

<details>



**Overall Verdict: WARN** — ~230 tests, well-structured and mock-disciplined, but a vacuous test and four untested security-critical code paths represent meaningful gaps.

### TDD Compliance
Tests map cleanly to ADR decisions, consistent with TDD. However, `Coordinator` lifecycle methods (`accept_edits`, `start`, `begin_tts_playback`, `finish_tts_playback`, `refresh_repo_map`) and the entire `DiffPanel` widget have no tests at all.

### Contract Coverage
- **Coordinator message format:** EXCELLENT — `TestMessageFormat` covers all three keys including `test_message_keys_are_exactly_three`.
- **`tts.speak()`:** ADEQUATE but fragile — mock target `@patch("harness.tts.KPipeline", create=True)` is non-functional; `_pipeline` singleton not reset between tests.
- **`edit_applier.py`:** GOOD with one critical gap — `test_major_whitespace_difference_rejects` has **no assertion**.
- **`git_ops.py`:** ADEQUATE — staging and `no git add .` verified; commit message format not checked.
- **`repo_map.py`:** EXCELLENT — truncation, 6+ languages, symlink escape all tested.
- **`tts_navigator.py`:** GOOD — clamps, signals, `play_all`, speed, error signal tested; `_build_word_intervals` and `_advance_word_highlight` not directly tested.

### Mock Discipline

| Dependency | Mocked? | Notes |
|---|---|---|
| Ollama (`ollama.Client`) | NO — `chat()` never called | CRITICAL gap |
| RealtimeSTT | YES | Good |
| Kokoro / KPipeline | Unreliable | Non-functional patch target |
| `sounddevice` | YES | Good |
| `soundfile` | YES | Good |
| `git.Repo` | YES | Good |
| `tree_sitter_languages` | YES | Good |
| Qt / QApplication | YES | Good |

### Numbered Findings

1. **CRITICAL:** `test_major_whitespace_difference_rejects` — no assertion, always passes.
2. **HIGH:** `TestSpeak` mock target non-functional; `_pipeline` singleton not reset.
3. **HIGH:** `code_llm.chat()` — zero tests.
4. **HIGH:** `coordinator.accept_edits()` — zero tests on most security-sensitive function.
5. **HIGH:** `DiffPanel` — zero tests for entire class.
6. **MEDIUM:** `coordinator.start()` — no test for thread spawn.
7. **MEDIUM:** `test_play_all_auto_advances` — `time.sleep(0.05)` brittle timing.
8. **MEDIUM:** `begin_tts_playback()` / `finish_tts_playback()` — state machine untested.
9. **MEDIUM:** `_build_word_intervals()` / `_advance_word_highlight()` — no direct tests.
10. **LOW:** `test_detects_git_repo` — not guarded by `shutil.which("git")`.
11. **LOW:** `coordinator.refresh_repo_map()` — no happy path or error path test.
12. **LOW:** `ai_panel.set_recording_active()` — animation untested.

### Summary

| Metric | Count |
|---|---|
| Test functions (estimated) | ~230 |
| Production modules with zero coverage | 0 at module level |
| Public functions with zero coverage | 15+ |
| CRITICAL | 1 |
| HIGH | 4 |
| MEDIUM | 4 |
| LOW | 4 |

</details>

<details>
<summary>Architecture Judge Report (judge-architecture)</summary>

**Overall Verdict: WARN** — One constraint violated (#9: `validate_path` not called from `accept_edits`); five additional lower-severity findings.

### Findings

1. **HIGH | `harness/coordinator.py`** — `accept_edits()` does not call `edit_applier.validate_path()`. Inline `os.path.realpath` containment check only runs inside `if self._project_root:` — omitted when `project_root` is `None`. Fix: call `edit_applier.validate_path(file_path, self._project_root)` unconditionally.

2. **MEDIUM | `harness/coordinator.py` ~line 192** — `except Exception as exc:` violates specific-exceptions rule. Fix: `except (RuntimeError, OSError, ValueError) as exc:`.

3. **MEDIUM | `harness/coordinator.py::accept_edits`** — fallback git path uses `os.path.basename(file_path)` (constraint #14 prohibited pattern). Fix: remove fallback `auto_commit` call; log warning and emit `edits_applied` instead.

4. **LOW | `harness/tts_navigator.py`** — `play_current()` called from Qt main thread; audio I/O correctly delegates to daemon thread. Constraint wording says "on daemon thread." Update AGENTS.md or restructure.

5. **LOW | `requirements.txt`** — `gitpython>=3.1.40` listed twice. Remove duplicate.

6. **LOW | `harness/code_llm.py`** — `REQUEST_TIMEOUT = 300.0` vs 120 s in AGENTS.md constraint #11. Align value or update AGENTS.md.

### Constraint Checklist

| # | Constraint | Status |
|---|---|:---:|
| 1 | Only `voice_input.py` imports RealtimeSTT | ✓ |
| 2 | Coordinator messages format | ✓ |
| 3 | `tts.speak()` return type | ✓ |
| 4 | Monaco served via localhost HTTP | ✓ |
| 5 | `QTWEBENGINE_CHROMIUM_FLAGS` + `QTWEBENGINE_DISABLE_SANDBOX` before Qt | ✓ |
| 6 | `ctranslate2==4.4.0` pinned | ✓ |
| 7 | PyTorch CUDA installed first | ✓ |
| 8 | `project_root` param present and wired | ✓ |
| 9 | `edit_applier.validate_path()` called from `accept_edits()` | ✗ |
| 10 | Repo map truncated to 4000 chars | ✓ |
| 11 | LLM timeout set + errors caught | ✓ ⚠ (300s not 120s) |
| 12 | Thread safety: `_context_lock` around context fields | ✓ |
| 13 | `play_current()` audio I/O on daemon thread | ✓ ⚠ |
| 14 | Git staging uses repo-relative paths | ✓ ⚠ (basename in dead fallback) |

</details>

<details>
<summary>Conventions Judge Report (judge-conventions)</summary>

**Overall Verdict: WARN** — Two HIGH issues (unguarded `except Exception` and unused `import wave`) plus recurring missing `-> None` annotations.

### Findings by File

**`main.py`:** Import ordering (third-party/local not separated by blank line); `main()` missing docstring.

**`harness/coordinator.py`:** `except Exception as exc:` (HIGH); `import git as _git` in wrong group (MEDIUM); 3 public methods missing `-> None` (`set_file_context`, `refresh_repo_map`, `clear_file_context`); 3 public methods missing docstrings (`pause_listening`, `resume_listening`, `clear_file_context`).

**`harness/tts.py`:** `import wave` unused — HIGH, remove it; `play_wav_bytes` missing `-> None`.

**`harness/audio_settings.py`:** 6 public methods lack docstrings.

**`ui/main_window.py`:** `MainWindow` class no class docstring; `DiffPanel.show_diff` and `MainWindow.set_root_path` missing `-> None`; `coordinator` and `audio_settings` params in `__init__` lack type hints.

**`ui/editor_panel.py`:** stdlib imports not alphabetical; `set_file` and `shutdown` missing `-> None`.

**`ui/ai_panel.py`:** `set_audio_devices` — `selected_input` and `selected_output` lack type annotations (`Optional[int] = None`).

**Clean files (no violations):** `harness/__init__.py`, `harness/voice_input.py`, `harness/code_llm.py`, `harness/tts_navigator.py`, `harness/edit_applier.py`, `harness/git_ops.py`, `harness/repo_map.py`, `harness/audio_devices.py`, `ui/__init__.py`.

### Summary Table

| File | HIGH | MEDIUM | LOW | Total |
|---|---|---|---|---|
| `main.py` | 0 | 1 | 1 | **2** |
| `harness/coordinator.py` | 1 | 3 | 0 | **4** |
| `harness/tts.py` | 1 | 1 | 0 | **2** |
| `harness/audio_settings.py` | 0 | 0 | 1 | **1** |
| `ui/main_window.py` | 0 | 2 | 1 | **3** |
| `ui/editor_panel.py` | 0 | 2 | 1 | **3** |
| `ui/ai_panel.py` | 0 | 1 | 0 | **1** |
| 9 other files | 0 | 0 | 0 | **0** |
| **Totals** | **2** | **10** | **3** | **15** |

</details>

<details>
<summary>Progress Judge Report (judge-progress)</summary>

**Overall Verdict: WARN** — Core architecture sound, most claimed-DONE phases correctly implemented, but two functional bugs prevent a clean PASS.

### Phase-by-Phase Checklist

**Phase 0 — Monaco POC:** All claims verified ✓

**Phase 1 — Core Voice Loop:** All claims verified ✓

**Phase 2a — IDE Shell:** All claims verified ✓

**Phase 2b — Monaco Upgrade:** All claims verified ✓

**Phase 3a — Core Editing Flow:**
- `edit_applier.py` and `git_ops.py` ✓ | Fuzzy threshold 0.85 ✓ | `EditResult.used_fuzzy` ✓
- `DiffPanel` widget exists ✓
- `DiffPanel` embedded in MainWindow layout ✗ **FINDING #1**
- `coordinator.accept_edits()` calls `edit_applier.validate_path()` ⚠ **FINDING #2**
- All other claims (stale guard, handler leak, error signals) ✓

**Phase 3b — Repo Map:** All claims verified ✓

**Phase 4 — TTS UX (STABILIZING):**
- `TtsNavigator` with all nav/speed/word-highlight methods ✓
- `play_all()` implemented in navigator ✓
- `play_all()` actually called from MainWindow ✗ **FINDING #3**
- All UI wiring, shortcuts, dark theme ✓
- PROGRESS.md Phase 4 log complete ⚠ **FINDING #4**

### Numbered Findings

1. **HIGH:** `DiffPanel()` constructed with `parent=None`, never added to splitter. `show_diff()` → free-floating top-level window.

2. **MEDIUM:** `edit_applier.validate_path()` dead code in production — `accept_edits()` reimplements validation inline.

3. **MEDIUM:** `_on_tts_play_requested()` calls `play_current()` (leaves `_auto_advance=False`). `play_all()` never called. TTS plays one sentence and stops.

4. **LOW:** PROGRESS.md Phase 4 log truncated mid-bullet; `stop()`, `set_speed()`, word-highlight timer, shortcuts, `playback_finished` signal undocumented.

### Deferred (no DONE marker)
- Suspicious code scan, secret scanner, `ast.parse` gate (Phase 3a deferred)
- Hardware validation (Phase 4)

### Actual Phase Boundary
Phase 3b is the last truly completed phase. Phase 4 is STABILIZING with two broken behaviours immediately visible in manual testing.

</details> The repo explicitly requires Red, then Green, then Refactor in [AGENTS.md](AGENTS.md#L46-L50), and repeats that commitment in [docs/PROGRESS.md](docs/PROGRESS.md#L55-L69). But the current audio tests only cover sentence splitting, play invocation, sample-rate scaling, and basic lifecycle or logging in [tests/test_tts.py](tests/test_tts.py#L65-L113), [tests/test_tts_navigator.py](tests/test_tts_navigator.py#L155-L289), and [tests/test_voice_input.py](tests/test_voice_input.py#L40-L85). They do not cover output device propagation, input device propagation, recorder construction options, wake-word mode switches, or surfaced playback failures, while the implementation still hardcodes default-device behavior and a placeholder wake word in [harness/tts.py](harness/tts.py#L64-L70), [harness/tts_navigator.py](harness/tts_navigator.py#L140-L156), and [harness/voice_input.py](harness/voice_input.py#L66-L79). As written, the plan would almost certainly drift into fix-first coding.

2. High: Phase C is sequenced too late for good test design. Device selection appears in Phase A and Phase B, but there is no checked-in settings layer or persistence test surface today, and the current UI tests only exercise status display, manual query, pause toggle, and TTS transport in [ui/ai_panel.py](ui/ai_panel.py#L157-L194), [ui/main_window.py](ui/main_window.py#L322-L333), [tests/test_ai_panel.py](tests/test_ai_panel.py#L102-L184), and [tests/test_main_window.py](tests/test_main_window.py#L343-L409). If you add explicit input and output device handling before you define how selections are stored, restored, and validated, you will either duplicate configuration plumbing or hide it behind hard-to-test UI state. From a TDD perspective, the settings contract should exist before the fixes depend on it.

3. Medium: The diagnostics part of Phases A and B is aimed at the wrong layer unless it is split carefully. Some narrow logging assertions already exist for VoiceInput in [tests/test_voice_input.py](tests/test_voice_input.py#L61-L85), and coordinator errors are already surfaced into the UI in [ui/main_window.py](ui/main_window.py#L143-L144) with error-path coverage in [tests/test_coordinator.py](tests/test_coordinator.py#L351-L385). But TTS playback failures in [harness/tts_navigator.py](harness/tts_navigator.py#L140-L156) only log warnings and do not emit a structured signal or result that tests can assert. Unit and integration tests should verify behavior boundaries such as selected device passed through, failure surfaced to coordinator or UI, and fallback behavior on invalid saved devices. Real device enumeration, audible playback, microphone pickup quality, and wake-word reliability belong in a manual audio self-test or smoke tool, not in pytest.

4. Medium: Phase D does not yet have a state contract that can drive a flashing recording indicator. The coordinator only exposes four coarse states in [harness/coordinator.py](harness/coordinator.py#L32-L38), and the current UI tests only cover listening, processing, and speaking labels in [tests/test_ai_panel.py](tests/test_ai_panel.py#L17-L30) plus pause and resume behavior in [tests/test_coordinator.py](tests/test_coordinator.py#L99-L109). That is not the same thing as actively recording or voice detected. If the indicator is built on top of logging or polling, the tests will be brittle. The correct Red phase is a dedicated recording-state or speech-detected signal, with deterministic tests around its transitions, before any animation work.

5. Medium: Phase E is not testable as stated because the current TTS contract is sentence-level only. The repo-level contract still says TTS returns List[Tuple[str, bytes]] in [AGENTS.md](AGENTS.md#L104) and that Phase 4 already shipped sentence navigation and chunk playback in [docs/PROGRESS.md](docs/PROGRESS.md#L19) and [docs/PROGRESS.md](docs/PROGRESS.md#L195-L225). Coordinator, navigator, and UI all assume sentence chunks in [harness/coordinator.py](harness/coordinator.py#L38), [harness/tts_navigator.py](harness/tts_navigator.py#L24-L36), [ui/ai_panel.py](ui/ai_panel.py#L189-L194), and [tests/test_main_window.py](tests/test_main_window.py#L343-L352). Word-by-word highlighting therefore needs its own contract-migration phase first: a timing-bearing chunk model, monotonic timing validation, mapping from playback position to word range, and UI rendering tests. The quality of estimated timings itself should be judged by manual acceptance tests, not by unit tests against real audio.

6. Medium: Playback completion semantics are not stabilized enough for Phases A and E. In [harness/coordinator.py](harness/coordinator.py#L263-L275), tts_finished is emitted in a finally block immediately after synthesis, while actual playback completion is handled later in [ui/main_window.py](ui/main_window.py#L322-L333). The existing tests cover chunk emission and transport wiring in [tests/test_coordinator.py](tests/test_coordinator.py#L441-L477) and [tests/test_main_window.py](tests/test_main_window.py#L343-L409), but they do not lock down the distinction between synthesis complete, playback started, playback failed, and playback finished. That ambiguity will make playback diagnostics and word-highlighting progression much harder to test cleanly.

**Assumption**

This review is only about TDD and test quality, not whether the audio fixes are needed. It also assumes you want to preserve the current thin-adapter boundary around RealtimeSTT in [AGENTS.md](AGENTS.md#L102-L104).

**Recommended plan revision**

1. Add a Phase A0 that introduces failing contract tests for audio configuration and surfaced errors in TTS playback, VoiceInput, and coordinator state, plus a separate manual audio self-test for real hardware diagnostics.
2. Move device picker and persistence up so configuration is defined and tested before Phase A and Phase B depend on explicit device indices.
3. Add a small state-contract phase before the recording indicator, with tests for recording-start, recording-stop, and speech-detected transitions.
4. Split word highlighting into two phases: first migrate the TTS chunk contract to include timing metadata under failing tests, then add UI highlighting with deterministic unit tests and manual acceptance checks for timing quality.

</details>

<details>
<summary>Architecture Judge Report</summary>

Overall severity: HIGH.

The broad A/B before C-E sequencing is directionally right, but the plan is missing two architectural preconditions: a clear TTS playback owner and a coordinator-owned microphone reconfiguration path.

1. HIGH: Phase A may be targeting the wrong TTS failure mode. The current pipeline synthesizes chunks in [harness/coordinator.py](harness/coordinator.py#L263-L273), then hands playback ownership to the UI by design in [docs/PROGRESS.md](docs/PROGRESS.md#L212-L214). But [ui/main_window.py](ui/main_window.py#L322-L325) only loads chunks and enables controls; actual playback is only triggered manually from the Play button or Space shortcut in [ui/main_window.py](ui/main_window.py#L173) and [ui/main_window.py](ui/main_window.py#L349-L355). That is inconsistent with the voice-first, fast-feedback goals in [docs/PROJECT.md](docs/PROJECT.md#L12-L13). Before spending Phase A effort on device diagnostics, the plan needs an explicit playback policy: autoplay after synthesis, or manual playback by design.

2. HIGH: Phase B/C do not define how mic-side configuration changes become effective. The recorder is constructed once inside [harness/voice_input.py](harness/voice_input.py#L69-L83), while pause and resume only stop and restart the existing recorder in [harness/voice_input.py](harness/voice_input.py#L47-L59). Changing input device or wake-word behavior after startup therefore needs recorder re-creation, not just a setter. Because coordinator owns voice lifecycle in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#L81) and instantiates VoiceInput in [harness/coordinator.py](harness/coordinator.py#L46-L47), the plan should add an explicit reconfigure path through coordinator rather than wiring UI changes straight into a long-lived recorder.

3. MEDIUM: The diagnostics design is asymmetric with the existing pipeline. Surfacing playback errors from navigator is architecturally correct because playback lives in [harness/tts_navigator.py](harness/tts_navigator.py#L128-L157). But STT diagnostics in the plan are still console logging only, while the app’s user-visible error channel lives on [harness/coordinator.py](harness/coordinator.py#L32-L39), and VoiceInput is intentionally just the thin RealtimeSTT adapter in [AGENTS.md](AGENTS.md#L102) and [harness/voice_input.py](harness/voice_input.py#L11-L18). If Phase B stops at logging, recorder-start failures, wake-word failures, and input-device errors still will not surface through the product pipeline.

4. MEDIUM: Phase B’s wake-word default change is a product-mode change, not just a debug switch. Wake word detection is still a documented functional requirement in [docs/PROJECT.md](docs/PROJECT.md#L19), while the custom wake word remains deferred in [docs/PROGRESS.md](docs/PROGRESS.md#L231). Making wake word optional is sensible for diagnostics, but changing the default to off changes baseline interaction semantics. That should be modeled as explicit audio or session configuration owned above VoiceInput, not as an implicit adapter default.

5. MEDIUM: Phase C puts too much platform and persistence responsibility into the panel. [ui/ai_panel.py](ui/ai_panel.py#L14-L20) and [ui/ai_panel.py](ui/ai_panel.py#L157-L189) are currently a thin signal-emitting view, while [ui/main_window.py](ui/main_window.py#L155-L173) handles orchestration. The plan’s device enumeration and QSettings persistence in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L76-L86) would make the panel own OS audio discovery and saved state even though the application has not established a real settings owner beyond app naming in [main.py](main.py#L43-L44). A small audio settings service is a better fit, with the panel remaining presentation plus signals.

6. MEDIUM: Phase E is acceptable only as a heuristic UI feature, not as a new TTS contract or pipeline milestone. The hard contract today is sentence-level chunks from [harness/tts.py](harness/tts.py#L35-L46), which is also a stated project constraint in [AGENTS.md](AGENTS.md#L104). [harness/tts_navigator.py](harness/tts_navigator.py#L71-L157) manages chunk playback, not word-timed synthesis, so timer-based highlighting will drift under stop, next, speed changes, and device buffering. That does not make Phase E wrong, but it should be documented as approximate UI decoration only and kept last.

7. LOW: The plan duplicates audio-device logic before formalizing it. [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L24-L38) and [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L55-L67) propose standalone tools that query devices directly, then [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L76-L77) introduces a shared audio_devices module later. That is workable, but it invites two different sources of truth for filtering and default-device behavior.

**Recommended plan revision**

Keep the A/B before C-E gate from [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L199), but insert a short architecture step ahead of it.

1. Add a Phase A0 that decides TTS ownership: either restore autoplay from MainWindow and let playback state come from navigator completion, or explicitly change the product to manual playback and update docs to match.
2. Add a shared audio settings layer before the UI picker. It should own input device, output device, and wake-word mode, plus persistence.
3. Route runtime diagnostics through the existing app pipeline: navigator can emit playback errors directly, and VoiceInput should expose status and error callbacks that coordinator turns into user-visible signals.
4. Apply mic-side config changes by recreating the recorder under coordinator control; apply speaker-side config changes in navigator on the next playback.
5. Leave Phase D where it is. Keep Phase E last and document it as approximate highlighting only.

</details>

<details>
<summary>Conventions Judge Report</summary>

Overall severity: MEDIUM.

No obvious PEP 8 naming or formatting blocker stands out in the current audio/UI files; the real convention risk is responsibility creep, public-API drift, and weak seams between UI, persistence, and device control.

1. HIGH: Phases C through E overload UI modules that are already acting as composite controllers. [ui/ai_panel.py](ui/ai_panel.py#L11-L209) already owns status display, response log, TTS preview, transport controls, manual input, and pause state. [ui/main_window.py](ui/main_window.py#L100-L331) already wires file tree, editor sync, diff flow, TTS navigation, and keyboard shortcuts. The plan then adds device pickers and persistence [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L71-L103), flashing or animation [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L107-L118), and HTML word-highlighting plus extra signal wiring [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L127-L153). That is a maintainability trap: view code becomes settings storage, animation state, and playback presentation logic. If this plan goes ahead, it should first extract an audio-settings widget and a dedicated TTS preview widget instead of continuing to grow these two files.

2. HIGH: The plan does not define a clean coordinator-level seam for input-device and wake-word control. Startup currently composes only a `Coordinator` and `MainWindow` in [main.py](main.py#L48-L49). `Coordinator` privately constructs `VoiceInput` in [harness/coordinator.py](harness/coordinator.py#L43-L46), while `MainWindow` only talks to coordinator public methods and its own `TtsNavigator` in [ui/main_window.py](ui/main_window.py#L155-L177). But the plan says to wire AI-panel device signals in `MainWindow` and add `VoiceInput.set_device(...)` and wake-word config in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L60-L67) and [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L88-L92). Without explicit `Coordinator.set_input_device(...)` and `Coordinator.set_wake_word_enabled(...)` APIs, the likely implementation path is reaching into `coordinator._voice`, which would violate the current encapsulation and make tests brittle.

3. MEDIUM: Phases A and C deepen an already split TTS playback surface instead of consolidating it. The repo still exposes `play_wav_bytes()` in [harness/tts.py](harness/tts.py#L64-L70), and it is still separately tested in [tests/test_tts.py](tests/test_tts.py#L96-L110). Actual app playback now lives in `TtsNavigator` in [harness/tts_navigator.py](harness/tts_navigator.py#L116-L152) and is wired from [ui/main_window.py](ui/main_window.py#L166-L177). The plan explicitly extends navigator-based playback and leaves `tts.py` unchanged in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L31-L37) and [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L163-L165). That will leave two playback APIs with different device and error behavior. From a maintainability perspective, choose one playback path and either remove `play_wav_bytes()` or mark it as diagnostic-only and keep it out of the main contract.

4. MEDIUM: The plan targets modules that already drift from the project’s public-API typing and exception-handling conventions. The repo standard requires type hints on public signatures and specific exceptions in [docs/CONVENTIONS.md](docs/CONVENTIONS.md#L8) and [docs/CONVENTIONS.md](docs/CONVENTIONS.md#L52). In [harness/voice_input.py](harness/voice_input.py#L17-L60), the public methods `__init__`, `on_text`, `start`, `stop`, `pause`, and `resume` do not have full return annotations, and the audio control paths catch broad `Exception`. [harness/tts_navigator.py](harness/tts_navigator.py#L141-L148) also catches broad `Exception` inside playback. Phases A and B add more public surface in exactly these files [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L31-L37), [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L60-L67). The plan should explicitly include a small cleanup pass so new methods like `set_device`, `set_output_device`, or new signal handlers do not extend the current convention debt.

5. MEDIUM: The testing and documentation scope is under-specified relative to the new surface area. The project requires tests-first and documentation updates in [AGENTS.md](AGENTS.md#L53), [AGENTS.md](AGENTS.md#L111), and [docs/CONVENTIONS.md](docs/CONVENTIONS.md#L105-L106). The plan adds new modules and tools in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L24-L38), [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L55-L67), and [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L75-L103), plus persisted settings and changed wake-word behavior. But Phase C’s tests only call out device enumeration and signal wiring in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L94), even though the relevant current coverage is already split across [tests/test_voice_input.py](tests/test_voice_input.py#L9), [tests/test_tts_navigator.py](tests/test_tts_navigator.py#L37), [tests/test_ai_panel.py](tests/test_ai_panel.py#L10), and [tests/test_main_window.py](tests/test_main_window.py#L328). The plan should explicitly require tests for persistence, coordinator-level setters, runtime error surfacing, and timer cleanup, plus updates to `PROGRESS` and `AGENTS`, and likely `SETUP` if the diagnostic scripts become part of the expected workflow.

6. LOW: Phase E has the highest maintenance cost per unit of value in the current architecture. The current TTS contract is simple chunk-level navigation and playback in [harness/tts_navigator.py](harness/tts_navigator.py#L71-L152), and the preview is just a plain label updated by [ui/ai_panel.py](ui/ai_panel.py#L49) and [ui/ai_panel.py](ui/ai_panel.py#L189-L194). The plan adds estimated word timings, a highlight timer, HTML rebuilding, and extra MainWindow wiring in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L135-L145). Because Kokoro does not provide real word timestamps, this creates a fragile heuristic contract that must stay in sync with playback speed, stop/next behavior, punctuation, and escaping. That is not a conventions violation by itself, but it is a clear maintainability risk and should not be mixed into the same increment as core audio reliability.

Recommended plan revision: keep A and B, but add a short “audio-seam cleanup” step first: define coordinator-level audio settings APIs, consolidate playback responsibility, and normalize public type hints and exception handling in the touched modules. Then do C only if the settings persistence lives outside `AiPanel` and the UI additions are extracted into smaller widgets; keep D to a single simple indicator, and defer E until there is either a real timing source or a clearly experimental, off-by-default implementation.

</details>

<details>
<summary>Progress Judge Report</summary>

Overall severity: HIGH.

1. HIGH: This is not a clean next stage. Phases A and B in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L13) and [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L42) are framed as blocking because TTS is silent and STT does not transcribe, but the project already marks the underlying capabilities as done in [docs/PROGRESS.md](docs/PROGRESS.md#L19) and [docs/PROGRESS.md](docs/PROGRESS.md#L190), while still listing continuous STT and TTS readback as requirements in [docs/PROJECT.md](docs/PROJECT.md#L20) and [docs/PROJECT.md](docs/PROJECT.md#L24). The code matches that concern: STT is created with a hardcoded wake word in [harness/voice_input.py](harness/voice_input.py#L69) and [harness/voice_input.py](harness/voice_input.py#L73), and TTS playback still uses the default device and only logs failures in [harness/tts_navigator.py](harness/tts_navigator.py#L117), [harness/tts_navigator.py](harness/tts_navigator.py#L146), and [harness/tts_navigator.py](harness/tts_navigator.py#L149). From a roadmap perspective, A and B should reopen a prior phase or become a Phase 4 stabilization phase, not read as forward feature progress.

2. HIGH: The wake-word story is already inconsistent, so Phase B is mixing defect recovery with scope redefinition. [docs/PROJECT.md](docs/PROJECT.md#L19) still describes wake word detection as a functional requirement and ties the custom Hey Harness model to Phase 4, while [docs/PROGRESS.md](docs/PROGRESS.md#L231) defers custom wake word to the future, and the implementation still hardcodes hey_jarvis in [harness/voice_input.py](harness/voice_input.py#L73). The proposal to default wake word off in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L197) may be sensible for debugging, but if that becomes the normal recovery path it should be documented as a temporary rollback of expected behavior, not folded into a new stage as if the product requirement were settled.

3. MEDIUM: Phases C through E are not one stage. Phase C in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L71) is a reasonable post-recovery enhancement because current playback and listening rely on defaults in [harness/tts_navigator.py](harness/tts_navigator.py#L117) and [harness/voice_input.py](harness/voice_input.py#L69), and there is no existing device-selection or settings layer in the codebase. Phase D and Phase E in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L107) and [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L127) are different: they are new UX scope beyond the completed Phase 4 definition in [docs/PROGRESS.md](docs/PROGRESS.md#L19). They also lack supporting state or model hooks. The current UI only exposes idle, listening, processing, and speaking in [harness/coordinator.py](harness/coordinator.py#L32) and [ui/ai_panel.py](ui/ai_panel.py#L158), so a flashing recording indicator would actually be a listening indicator unless recorder-level state is added. Current TTS navigation is sentence-level only in [harness/tts_navigator.py](harness/tts_navigator.py#L30) and [ui/ai_panel.py](ui/ai_panel.py#L49), so word highlighting is clearly a later enhancement, not part of blocking recovery.

4. MEDIUM: The completion framing needs an integration-validation layer. The reason this plan exists is stated in [docs/PLAN_AUDIO_UX.md](docs/PLAN_AUDIO_UX.md#L9), yet the current evidence behind DONE is mostly mocked unit coverage rather than real mic and speaker validation: Kokoro is mocked in [tests/test_tts.py](tests/test_tts.py#L75), voice startup is mocked in [tests/test_voice_input.py](tests/test_voice_input.py#L45), and TTS playback is mocked in [tests/test_tts_navigator.py](tests/test_tts_navigator.py#L171). That is good test practice, but docs should distinguish code complete under mocks from runtime validated on hardware. Without that distinction, the roadmap turns missing integration proof into a fake new phase.

5. LOW: The documentation set already carries conflicting phase-status narratives. [docs/REVIEW_REPORT.md](docs/REVIEW_REPORT.md#L8) still says Phase 4 should not move forward before fixes, while the current implementation has already moved to application-level TTS shortcut wiring in [ui/main_window.py](ui/main_window.py#L167) and [ui/main_window.py](ui/main_window.py#L189). Before adding another staged plan, reconcile or clearly mark historical review artifacts so the roadmap does not present multiple incompatible truths about whether Phase 4 is done, blocked, or partially repaired.

**Recommended Plan Revision**

1. Rename Phases A and B to Phase 4 Stabilization: Audio Integration Recovery, and change progress wording so Phase 4 is not treated as fully closed until real-device STT and TTS smoke checks pass.
2. Reconcile [docs/PROJECT.md](docs/PROJECT.md#L19) with [docs/PROGRESS.md](docs/PROGRESS.md#L231) so wake-word scope is explicit: required now, deferred, or debug-optional. Pick one and document it consistently.
3. Move Phase C into the next true feature phase after A and B succeed, unless device misselection is confirmed as the root cause during recovery.
4. Remove Phases D and E from the blocking plan and track them as optional UX backlog items until stable audio and richer state or timing signals exist.

</details>
