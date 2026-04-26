# Progress Tracker

> **Living document** — update this file after completing any work on the project.

## Phase Summary

| Phase | Status | Description |
|---|---|---|
| Phase 0 | **DONE** | Monaco ↔ QWebChannel POC gate — PASSED |
| Pre-work | **DONE** | Install wizard (`setup/install.py`) |
| Phase 1 | **DONE** | Core voice loop + 3-panel UI + coordinator pipeline |
| Testing | **DONE** | Retrofit TDD test suite for Phase 0-1 code (65 tests) |
| Preflight | **DONE** | Phase 02 preflight — concurrency, deps, integration hardening |
| Phase 2a | **DONE** | IDE shell — file tree → editor → LLM context |
| Phase 2b | **DONE** | Monaco upgrade (gated on Phase 0 PASS ✓) |
| Phase 2 QA | **DONE** | Post-review hardening (4-agent audit corrections) |
| Phase 3a | **DONE** | SEARCH/REPLACE editing flow + diff view + git auto-commit |
| Phase 3b | **DONE** | Tree-sitter repo map context enhancement |
| Phase 4 | **STABILIZING** | Audio recovery, device config, indicator, and highlighting are implemented; hardware validation and UX smoothing are pending |
| LLM Migration | **DONE** | Ollama → Gemini 2.5 Flash Lite via OpenAI SDK |
| Phase 5 | **IMPLEMENTED / NEEDS UX STABILIZATION** | 3-model pipeline: whisper-turbo STT, Gemini Flash Lite LLM, Kokoro GPU-capable TTS |
| Current Focus | **OPEN** | Make speaking, listening, interruption, and TTS playback feel seamless instead of clunky |

## Detailed Log

### Red-Team Remediation Pass — DONE (2026-04-26)

Addressed the April 26 red-team report across security, resilience, performance, UX, and
dependency hardening.

Completed work:
- Hardened edit acceptance: `_project_root=None` now allows only the active editor file, project
  containment uses `commonpath`, and `validate_path()` is part of the production guard.
- Hardened LLM context handling: open-file content is clearly delimited as untrusted data and
  nested SEARCH/REPLACE markers are neutralized before request construction.
- Protected stored Gemini API keys with a DPAPI-backed settings format on Windows, with no
  plaintext QSettings writes.
- Fixed STT resilience: Whisper uses the validated `int8_float16` CUDA compute type, preload
  failures are re-emitted after UI callbacks are registered, mic-open failures retry before stop,
  and unit tests can disable background preload.
- Restored real streaming behavior by handing live LLM chunks to the TTS sentence splitter and
  synthesizer while the full response is still accumulating for edit parsing.
- Serialized Kokoro synthesis with a lock and made per-sentence TTS synthesis failures non-fatal.
- Added queue backpressure for submitted queries and moved initial repo-map generation off the
  pipeline worker's startup path.
- Improved UI workflow: diff panel is inline, critical errors use a banner, dead wake-word UI is
  disabled with a tooltip, STT preview auto-submits after a short delay, F2 provides in-window PTT,
  arrow/space/escape TTS shortcuts are gated while text widgets have focus, stale diff path checks
  are Windows case-insensitive, and the API key field has a clear action.
- Tightened dependency bounds and documented the ctranslate2/onnxruntime CUDA and DLL constraints.
- Removed remote URL access from Monaco's WebEngine view and stopped forcing
  `KMP_DUPLICATE_LIB_OK=TRUE` at startup.
- Adjusted `git_ops.is_git_repo()` so temp folders are not treated as repositories just because a
  parent directory has `.git` metadata.

Verification:
- `python -m pytest tests/test_voice_input.py -v` — 43 passed.
- `python -m pytest tests/ -v` — 414 passed, 1 skipped.

### Agent Instruction Sync: Scoped Python Correctness — DONE (2026-04-26)

- Added `.github/instructions/python-correctness.instructions.md` scoped to Python source and
  tests.
- Captured the project preference for test-first, verifiable Python changes: functional-core logic
  where useful, explicit side-effect boundaries, dependency injection for external resources, and
  behavior-focused pytest coverage.
- Linked the scoped guidance from `AGENTS.md`, `.github/copilot-instructions.md`, and
  `docs/CONVENTIONS.md` without duplicating the full rules in always-on context.

### Phase 0: Monaco POC Gate — DONE (2025-04-08)

- Created `phase0_poc/monaco_poc.py`
- Went through ~5 rewrites due to GPU and content delivery issues
- **Failed approaches**: `app://` custom URL scheme (QBuffer GC), `file://` (Web Worker block), multiple `--disable-gpu` flag combos
- **Working solution**: Localhost HTTP server (daemon thread) + `setHtml()` with localhost base URL + `--in-process-gpu` Chromium flag
- Windows Graphics Settings: Python.exe pinned to "High Performance (NVIDIA)"
- Round-trip confirmed: Python → JS inject → Monaco setValue → JS readback → Python signal match
- Result: **PASS — ROUND-TRIP OK**

### Pre-work: Install Wizard — DONE (2025-04-08)

- Created `setup/install.py` — 6-step wizard (was 7; Ollama model pull removed in LLM Migration)
- Steps: assert Python 3.11 → check system deps → create venv → CUDA PyTorch first → pin ctranslate2 → requirements.txt → validation suite
- External review: replaced `curl` subprocess with `urllib.request.urlopen`

### Phase 1: Core Voice Loop — DONE (2025-04-09)

Historical note: this phase originally used RealtimeSTT and local Ollama. Later phases replaced
those with direct faster-whisper/WebRTC VAD and hosted Gemini.

Files created:
- `main.py` — entry point with env var setup and `if __name__ == '__main__'` guard
- `harness/voice_input.py` — thin RealtimeSTT adapter
- `harness/code_llm.py` — LLM client + SEARCH/REPLACE parser + prose extractor (originally Ollama; migrated to Gemini in LLM Migration phase)
- `harness/tts.py` — Kokoro wrapper: `speak()` → sentence-split WAV chunks
- `harness/coordinator.py` — queue pipeline with stub context_assembler and response_splitter
- `ui/main_window.py` — 3-panel layout (file tree | editor | AI panel)
- `ui/editor_panel.py` — QPlainTextEdit placeholder
- `ui/ai_panel.py` — voice status, response log, manual input, pause button

Architecture stubs wired: coordinator message format `{"query", "context", "repo_map"}`, TTS returns `List[Tuple[str, bytes]]`, voice_input is only RealtimeSTT importer.

### Testing: TDD Retrofit — DONE (2025-04-09)

Adopted Red/Green/Refactor TDD workflow. Retroactively wrote 65 tests covering all Phase 1 modules:

Files created:
- `pytest.ini` — pytest configuration with `ui` and `slow` markers
- `tests/conftest.py` — session-scoped `qapp` fixture for PyQt6 widget tests
- `tests/test_code_llm.py` — 15 tests: SEARCH/REPLACE parser (single/multi/lenient chevrons/case-insensitive/fenced blocks/edge cases), prose extraction, chat message building with mocked Ollama
- `tests/test_tts.py` — 12 tests: sentence splitting, speak() return-type contract, play_wav_bytes sounddevice call
- `tests/test_voice_input.py` — 7 tests: adapter API surface (callback registration, initial state, safe stop/pause/resume, start idempotence)
- `tests/test_coordinator.py` — 12 tests: message format contract (ADR-006), file context management, submit_text, lifecycle (stop sentinel, initial state), _process_message pipeline (LLM call, TTS skip/call)
- `tests/test_editor_panel.py` — 4 tests: initial path, set_file, get_content, overwrite
- `tests/test_ai_panel.py` — 11 tests: status label states, response/transcription append, text_submitted signal, empty submit guard, pause/resume toggle

All external dependencies mocked (Ollama, RealtimeSTT, Kokoro, sounddevice). Tests run in ~7s.

Going forward, all new work follows Red → Green → Refactor TDD.

### Preflight: Phase 02 Hardening — DONE (2025-04-09)

Five-pass red-team review identified 7 concrete risks. All high-priority items fixed:

1. **Coordinator thread safety** — Added `threading.Lock` to protect `_current_file_content`/`_current_file_path`/`_repo_map`. Context is now snapshotted under lock at enqueue time, preventing stale reads from the worker thread.
2. **Coordinator shutdown** — Replaced bare `_running` flag with `threading.Event` (`_stop_event`). `stop()` now joins the worker thread with a 5-second timeout. Pipeline loop uses `queue.get(timeout=1.0)` so it checks the stop event regularly.
3. **LLM timeout** — `code_llm.chat()` now creates an `ollama.Client(timeout=120)` instead of using the module-level `ollama.chat()`. Catches `ConnectError`/`ReadTimeout` and wraps them as `RuntimeError`.
4. **OLLAMA_HOST consistency** — Normalized to `http://127.0.0.1:11434` in both `main.py` and `tests/conftest.py` to match the scheme used by `setup/install.py` validation.
5. **requirements.txt gaps** — Added missing `sounddevice` (imported by `tts.py`), `pytest` (used by test suite), and `numpy` (used in test fixtures).
6. **File tree root init** — `main.py` now calls `window.set_root_path()` with `sys.argv[1]` or `os.getcwd()` before showing the window.
7. **Integration tests** — Added `tests/test_main_window.py` (6 tests): panel creation, root path init, signal wiring, editor-coordinator sync, manual query flow. Total suite: 77 tests, all passing.

### Phase 2a: IDE Shell — DONE (2025-04-09)

Goal: Open files from tree, load into editor + LLM context.

Completed work:
- File tree double-click → editor load → coordinator context already wired in Phase 1
- Added binary file detection (`_is_binary_file`): checks first 8 KB for null bytes, rejects binary files
- Added file size guard (`_MAX_FILE_SIZE = 1 MB`): skips files over 1 MB
- Extracted `_load_file_by_path()` from `_on_file_double_click()` for testability
- 5 new tests in `test_main_window.py`: binary detection, text pass-through, oversized rejection, edge cases

### Phase 2b: Monaco Upgrade — DONE (2025-04-09)

Goal: Replace QPlainTextEdit with Monaco via QWebEngineView.

Completed work:
- Rewrote `ui/editor_panel.py` — QPlainTextEdit replaced with Monaco QWebEngineView + QWebChannel
- Localhost HTTP server (daemon thread) serves `assets/monaco/min/` on a random port
- `_EditorBridge` QObject: JS → Python events (`onEditorReady`, `onContentChanged`)
- Python-side cache: `get_content()` is synchronous, cache updated via QWebChannel on every keystroke
- `set_file()` defers content push if Monaco hasn't finished loading yet (`_pending_file`)
- `_suppressChange` flag in JS prevents feedback loops during programmatic `setValue()`
- Language auto-detection: `_detect_language()` maps 50+ file extensions to Monaco language IDs
- Added `content_changed` signal — MainWindow uses this instead of reaching into `_editor._editor.textChanged`
- `_DebugPage` captures JS console.log → Python logger for diagnostics
- `_SilentHandler` suppresses HTTP request logs
- 18 new tests: 6 EditorPanel API tests + 12 language detection tests
- All 96 tests passing (was 77)

### Phase 3a: Core Editing Flow — DONE (2025-04-09)

Goal: AI suggests edits via SEARCH/REPLACE blocks → user accepts/rejects via diff view → auto-commit.

Completed work:
- **`harness/edit_applier.py`** — New module: `apply_edits()` with exact match + fuzzy fallback (difflib SequenceMatcher, threshold 0.6), `validate_path()` security gates (rejects absolute paths, traversal, empty paths)
- **`harness/git_ops.py`** — New module: `auto_commit()` stages specific file only via gitpython, `is_git_repo()` detection
- **Coordinator response_splitter activated** — `_process_message()` now calls `parse_search_replace()` on LLM output, runs `edit_applier.apply_edits()`, emits `edits_proposed` signal with `{file_path, edits, original, modified}` dict
- **New coordinator signals** — `edits_proposed(dict)`, `edits_applied(str)` for UI binding
- **`accept_edits()` / `reject_edits()`** on Coordinator — accept writes file + git auto-commit, reject is a no-op
- **`DiffPanel` widget** in `ui/main_window.py` — unified diff display (difflib), Accept/Reject buttons, shows/hides on edits_proposed
- **MainWindow wiring** — `edits_proposed` → DiffPanel, accept → write + reload editor + git commit, reject → hide, `edits_applied` → status bar
- **`requirements.txt`** — Added `gitpython>=3.1.40`
- **41 new tests**: 20 edit_applier (8 path validation, 7 exact match, 3 fuzzy match, 2 EditResult), 7 git_ops (repo detection, staging, commit, error handling), 9 coordinator (response_splitter, accept/reject), 5 MainWindow diff flow
- Total suite: **149 tests passing** (was 108)

### Phase 3a Planned → Deferred

Security features planned but deferred to a hardening pass:
- Suspicious code scan (deny list)
- Secret scanner before git commit
- ast.parse syntax gate on SEARCH/REPLACE output

### Phase 3a QA: Red-Team Corrections — DONE (2025-04-09)

Four-agent parallel red-team review of Phase 3a. Seven findings fixed:

1. **Path security gate activated** — `edit_applier.validate_path()` was dead code; `coordinator.accept_edits()` now validates file paths against `project_root` (rejects edits outside project root). `Coordinator.__init__` accepts `project_root` param, `main.py` passes it.
2. **Git commit path fixed** — Was passing `os.path.basename(file_path)` which broke for nested files (e.g. `harness/code_llm.py` → staged `code_llm.py`). Now resolves repo root via `git.Repo(search_parent_directories=True)` and stages `os.path.relpath(file_path, repo_root)`.
3. **Accept error handling** — `accept_edits()` now returns `bool`, catches `OSError`/`PermissionError` on write, checks `auto_commit` return value, emits `error_occurred` on failure. UI only reloads editor on success.
4. **Proposal handler leak fixed** — `_on_edits_proposed()` now disconnects old button handlers before connecting new ones via `_disconnect_diff_buttons()`. Prevents accumulated handlers from multiple rapid proposals.
5. **Stale proposal guard** — `_on_accept_edits()` checks if the active file still matches the proposal's `file_path`; rejects with status bar message if user switched files.
6. **Fuzzy threshold aligned to ADR-005** — Changed `_FUZZY_THRESHOLD` from 0.6 → 0.85 to match documented `~0.85 threshold`. Added `EditResult.used_fuzzy` flag. Coordinator includes `used_fuzzy` in proposal metadata.
7. **ADR-005 updated** — Documented `used_fuzzy` flag and removed stale "user confirmation" text.

New tests (11 added, 160 total passing):
- `test_accept_returns_false_on_write_error` — unwritable path
- `test_accept_emits_error_on_git_failure` — git commit fails
- `test_accept_rejects_path_outside_project` — security boundary
- `test_accept_uses_repo_relative_path_for_git` — nested file staging
- `test_multiple_proposals_do_not_accumulate_handlers` — rapid proposals
- `test_accept_rejects_stale_proposal_on_file_switch` — file switch guard
- `test_accept_does_not_reload_editor_on_failure` — failure path
- `test_threshold_matches_adr` — fuzzy threshold assertion
- `test_similar_functions_do_not_cross_match` — fuzzy collision
- `test_exact_match_does_not_set_fuzzy_flag` — fuzzy flag
- `test_fuzzy_flag` — EditResult dataclass

### Phase 3b: Context Enhancements — DONE (2025-04-10)

Goal: Richer LLM context via tree-sitter repo map.

Completed work:
- **`harness/repo_map.py`** — New module: tree-sitter symbol index for LLM context
  - `is_indexable(path)` — allowlist filter for `.py`, `.js`, `.ts`, `.go`, `.rs`, `.c`, `.cpp`, `.h`, `.hpp`, `.java`
  - `extract_symbols(source, language)` — parses source with tree-sitter-languages, walks AST to extract functions, classes, methods, structs, enums, traits, interfaces
  - `generate_repo_map(root_dir, exclude_dirs)` — walks project tree, skips excluded dirs (`.git`, `__pycache__`, `node_modules`, `.venv`, `dist`, `build`, etc.), skips files over 100 KB, produces compact symbol listing
  - Output truncated to 4000-char budget (~1000 tokens) to fit 4096-token LLM context window
  - Graceful degradation: returns empty if `tree-sitter-languages` not installed
  - Supports nested symbols (e.g. methods inside classes, functions inside impl blocks)
  - Multi-language name extraction: `child_by_field_name("name")` primary, declarator chain for C/C++, type field for Rust impl blocks, fallback to first identifier child
- **Coordinator integration** — `refresh_repo_map()` method generates map under context lock, called automatically at start of `_pipeline_loop` (background thread), fills `_repo_map` slot in message dict
- **`requirements.txt`** — Replaced `tree-sitter>=0.21.0` with `tree-sitter-languages>=1.10.0` (bundles pre-compiled grammars)
- **40 new tests**: 12 is_indexable, 6 _should_exclude, 3 _format_symbols, 6 extract_symbols (mocked tree-sitter), 9 generate_repo_map (tmp_path + mocked extraction), 4 coordinator integration (refresh, error handling, pipeline loop call)
- Total suite: **200 tests passing** (was 160)

### Phase 3b QA: Review Corrections — DONE (2025-04-10)

Four-agent parallel review identified 7 findings. All high/medium items fixed:

1. **Symlink escape guard** — `generate_repo_map()` now resolves each file path and checks `is_relative_to(root)`, preventing symlinked files from escaping the project root.
2. **Repo map propagation test** — New test verifies that a populated `_repo_map` actually appears in messages from `_enqueue()` — the core Phase 3b integration contract.
3. **Non-Python extract_symbols coverage** — 8 new tests covering JS function, TS interface, Go func, Rust struct, Java class+method, C function (declarator chain), C++ class.
4. **Context truncation** — `code_llm.chat()` now truncates context to `_MAX_CONTEXT_CHARS` (12000 chars) to prevent crowding out the repo map in the 4096-token window.
5. **Specific exception handling** — `refresh_repo_map()` now catches `(OSError, ValueError, RuntimeError)` instead of bare `Exception`.
6. **qapp fixture** — `TestCoordinatorRepoMap` now uses `qapp` fixture and `@pytest.mark.ui` to prevent potential PyQt6 crashes.
- Total suite: **210 tests passing** (was 200)

### Phase 4: TTS UX + Polish — IMPLEMENTED (reopened 2026-04-11)

Goal: Full TTS UX with sentence navigation, playback controls, speed adjustment, and dark theme.

Completed work:
- **`harness/tts_navigator.py`** — New module: TTS sentence navigation + playback
  - `TtsNavigator(QObject)` — manages `List[Tuple[str, bytes]]` chunks with nav + playback
  - `load(chunks)` — loads new chunks, resets to index 0, emits `chunk_changed`
  - `next()` / `prev()` — arrow-key navigation with clamping at boundaries
  - `play_current()` — plays current chunk via sounddevice on a daemon thread
  - `play_all()` — auto-advancing play from current to end
  - `stop()` — stops playback, cancels auto-advance
  - `set_speed(float)` — adjusts playback speed (0.25–3.0x) by scaling sample rate
  - Signals: `chunk_changed(int, str)`, `playback_finished()`, `speed_changed(float)`
  - Properties: `current_index`, `chunk_count`, `is_playing`, `speed`, `current_text`
- **`ui/ai_panel.py`** — TTS playback controls added
  - ◄ Prev | ▶ Play | ■ Stop | ► Next buttons (disabled until chunks load)
  - Speed −/+ buttons with speed label (e.g. "1.5x")
  - Chunk counter label (e.g. "2 / 5")
  - Sentence preview label showing current TTS text
  - New signals: `tts_play_requested`, `tts_stop_requested`, `tts_prev_requested`, `tts_next_requested`, `tts_speed_change_requested(float)`
  - Public methods: `enable_tts_controls(bool)`, `update_chunk_info(idx, total, text)`, `update_speed_display(float)`
- **Coordinator TTS refactor** — `tts_chunks_ready(list)` signal replaces inline `play_wav_bytes` loop
  - `_process_message()` now emits synthesized chunks via signal instead of blocking on playback
  - Playback is fully controlled by UI layer via `TtsNavigator`, not coordinator
- **MainWindow wiring (Phase 4)**
  - `tts_chunks_ready` → loads navigator + enables controls
  - Navigator `chunk_changed` → updates AI panel sentence display + counter
  - AI panel buttons → navigator play/stop/prev/next
  - Speed +/− → navigator `set_speed()` → AI panel speed label
  - `keyPressEvent` keyboard shortcuts: ← prev, → next, Space play/pause, Escape stop
- **Dark theme** — VS Code–inspired `QPalette` applied globally in `main.py`
  - All widget colors match `#1e1e1e`/`#252526`/`#d4d4d4` dark theme
  - Disabled state uses `#666666` text
  - Tooltips styled consistently
- **49 new tests**: 26 TtsNavigator (init, nav, signals, playback, speed), 12 AiPanel TTS controls, 3 coordinator TTS signal, 6 MainWindow TTS wiring + keyboard shortcuts, 2 dark theme space/escape shortcuts
- Total suite: **259 tests passing** (was 210)

### Phase 4 Stabilization: Playback Ownership Contract — DONE (2026-04-11)

Reason for reopen:
- Runtime audio behavior is not yet verified on real hardware, and Phase 4's original
  manual-playback wiring made TTS silence ambiguous to diagnose.

Completed work:
- Added explicit `Coordinator.begin_tts_playback()` / `finish_tts_playback()` lifecycle
  methods so speaking/listening state tracks actual playback rather than synthesized chunks.
- Moved playback policy ownership into `MainWindow`: incoming `tts_chunks_ready` now loads
  chunks and autoplays immediately.
- Routed play/stop/space/escape through one playback-policy seam so UI-triggered replay and
  stop actions update coordinator state consistently.
- Updated `TtsNavigator` with playback session tokens so stale completion callbacks from an
  interrupted playback cannot finish a newer playback session.
- Kept replay controls enabled after completion so the user can replay the last response
  without waiting for a new LLM turn.
- Added 7 Red-first contract tests across coordinator and main-window playback ownership.
- Full suite after the change: **271 passed, 1 skipped**.

Next stabilization target:
- Run the manual audio smoke tools inside the full Python 3.11 app environment.

### Phase 4 Stabilization: Playback Error Surfacing — DONE (2026-04-11)

Completed work:
- Added `TtsNavigator.playback_error(str)` so playback failures are surfaced as a product event,
  not just a log warning.
- `MainWindow` now routes playback failures into the AI response log and status bar for visible
  diagnosis during audio recovery.
- Added `tools/test_audio.py` as a manual TTS smoke tool: output-device listing, sine-wave probe,
  and Kokoro probe through the same sounddevice path used by playback.
- Added 3 tests covering navigator playback-error emission and UI surfacing.
- Full suite after the change: **274 passed, 1 skipped**.

Verification notes:
- The new smoke tool was added successfully but could not be exercised in the current
  `.venv-poc` environment because it does not include `sounddevice`.
- Real speaker validation remains pending in the full `.venv` on Python 3.11.x.

### Phase 4 Stabilization: Explicit Output Device Override — DONE (2026-04-11)

Completed work:
- Added `TtsNavigator.output_device` and `set_output_device()` so playback can target a specific
  output device before the device-picker UI is built.
- `play_current()` now snapshots the selected output device and passes it through to
  `sounddevice.play(..., device=...)` on the worker thread.
- Kept the output-device override at the navigator boundary so the later settings seam can wire
  into one focused playback API.
- Added 3 Red-first navigator tests for default output-device state, device selection, and
  `device=` propagation into playback.
- Full suite after the change: **277 passed, 1 skipped**.

Remaining:
- Run `tools/test_audio.py --device <index>` inside the full Python 3.11 app environment to
  validate real speaker output on a selected device.

### Phase 4 Stabilization: Audio Config + UX Completion — IMPLEMENTED (2026-04-11)

Completed work:
- Added `harness/audio_settings.py` as the shared `QSettings` persistence seam for input device,
  output device, and wake-word mode.
- Added `harness/audio_devices.py` for input/output device enumeration and default-device lookup.
- Reworked `VoiceInput` to support input-device reconfiguration, optional wake-word gating,
  visible error callbacks, recording-state callbacks, and `_listen_loop()` diagnostics.
- Added coordinator-owned mic reconfiguration APIs and a `recording_active_changed(bool)` signal.
- Added the collapsible audio-settings UI in `AiPanel` with input/output device pickers and a
  wake-word toggle, while keeping persistence outside the widget.
- Added the flashing listening indicator and pulsing red dot in `AiPanel` using an explicit
  recording-state contract instead of overloading the status label alone.
- Added word-by-word TTS highlighting with timer-based heuristic timing in `TtsNavigator`, plus
  HTML rendering in `AiPanel`.
- Wired audio settings, recording state, and word highlighting through `MainWindow`.
- Added `tools/test_mic.py` for manual microphone diagnostics: device listing, amplitude stats,
  and optional one-shot transcription.
- Added new test coverage for `audio_devices`, `audio_settings`, `voice_input`, `coordinator`,
  `ai_panel`, `tts_navigator`, and `main_window`.
- Full suite after the change: **317 passed, 1 skipped**.

Remaining validation blocker:
- `.venv-poc` does not include the full audio stack (`sounddevice`, faster-whisper, WebRTC VAD). Real STT/TTS
  hardware validation still must run in the full `.venv` on Python 3.11.x.

### Phase 4: Deferred to Future

Features planned but pushed to a future phase:
- Code explanation vs. summarization LLM modes
- Application icons

### Phase 5: 3-Model Streaming Pipeline — IMPLEMENTED / NEEDS UX STABILIZATION (2026-04-11)

Goal: Replace RealtimeSTT wrapper with direct faster-whisper, add streaming LLM → TTS pipeline
for reduced end-to-end latency, move Kokoro to GPU, drop wake word support.

Completed work:
- **`harness/voice_input.py`** — Full rewrite: replaced RealtimeSTT wrapper with direct
  faster-whisper WhisperModel("turbo") + WebRTC VAD + sounddevice.InputStream
  - Lazy model loading: `WhisperModel("turbo", device="cuda", compute_type="int8_float16")`
  - WebRTC VAD (aggressiveness=3, 30ms frames at 16kHz)
  - Ring buffer for 0.3s pre-speech audio capture
  - 0.5s post-speech silence detection (down from 1.2s)
  - Removed wake word support entirely
  - Same public API preserved: `start()`, `stop()`, `pause()`, `resume()`, `on_text()`, etc.
  - 32 tests across 5 classes (API, model, VAD, transcription, callback safety)
- **`harness/code_llm.py`** — Added streaming capabilities for `gemini-2.5-flash-lite`
  - `chat_stream_raw()` — generator using `stream=True` for Gemini API, yields raw text deltas
  - `chat_stream()` — convenience wrapper that filters raw deltas through `split_sentences_streaming()`
  - `split_sentences_streaming()` — sentence boundary detection from streaming text deltas,
    filters out SEARCH/REPLACE blocks mid-stream
  - `_build_messages()` — extracted shared helper from `chat()` and `chat_stream()`
  - 19 new tests: 7 for sentence splitter, 5 for chat_stream, 7 for chat_stream_raw (incl. error paths)
- **`harness/tts.py`** — GPU mode + streaming generator
  - `TTS_DEVICE = "cuda"` — Kokoro runs on GPU (~0.3 GB VRAM)
  - `_get_pipeline()` now passes `device=TTS_DEVICE` to KPipeline
  - `speak_stream(sentences: Iterator[str])` — yields `(sentence, wav_bytes)` one at a time
    as sentences arrive, enabling playback before LLM finishes
  - 4 new tests: 3 for speak_stream, 1 for TTS_DEVICE
- **`harness/coordinator.py`** — Streaming pipeline rearchitecture
  - `_process_message()` rewritten: `chat_stream_raw()` → `_capturing_stream()` closure
    (accumulates raw deltas for edit parsing) → `split_sentences_streaming()` (prose filtering) →
    `speak_stream()` → incremental `tts_chunk_ready` signals
  - New signal: `tts_chunk_ready(str, object)` — emits each (sentence, wav_bytes) individually
  - Raw response preserved in `_capturing_stream()` closure so `parse_search_replace()` sees
    SEARCH/REPLACE blocks and edit detection works correctly
  - `tts_chunks_ready` emitted at end with full list for backward compatibility
  - `set_wake_word_enabled()` is now a no-op
  - 5 new streaming pipeline tests
- **`harness/tts_navigator.py`** — Incremental loading support
  - `append_chunk(sentence, wav_bytes)` — adds one chunk at a time for streaming playback
  - Sets index to 0 and emits `chunk_changed` on first append
  - 5 new tests for append_chunk behavior
- **`requirements.txt`** — Updated dependencies
  - Added `faster-whisper>=1.1.0` (replaces RealtimeSTT)
  - Removed `RealtimeSTT>=0.3.104` and `openwakeword>=0.6.0`

VRAM budget (estimated):
- whisper-large-v3-turbo (int8_float16): ~0.8 GB
- Kokoro-82M (GPU): ~0.3 GB
- OS/Qt overhead: ~1.0 GB
- **Total: ~2.1 GB of 12 GB available**

Full suite after the change: **375 passed, 1 skipped**.

Current assessment (2026-04-26):
- The core technical pieces are in place, but the voice experience still needs product-level
  smoothing. Last hands-on use felt clunky and unpleasant, especially around speaking cadence,
  listening state, TTS timing, and playback flow.
- Treat the next pass as audio UX stabilization rather than new feature expansion: observe the
  real interaction loop, remove awkward waits, make interruptions predictable, and make spoken
  feedback feel calm and continuous.
- Documentation has been realigned around the current stack: direct faster-whisper/WebRTC VAD
  STT, Gemini Flash Lite through the OpenAI-compatible SDK, Kokoro TTS, and no wake-word support.
- Known follow-up before calling the product smooth: run full Python 3.11 hardware validation,
  verify `setup/install.py` validation against the current dependency list, and audit whether the
  intended LLM/TTS streaming path is genuinely incremental during real use.

### Phase 2 QA: Post-Review Hardening — DONE (2025-04-09)

Four-agent audit (architecture, testing, UI, ops) identified 6 findings. Corrections applied:

1. **Monaco HTTP server shutdown** — Added `EditorPanel.shutdown()` that calls `self._server.shutdown()`. `MainWindow.closeEvent()` calls it on window close. Prevents orphaned daemon threads serving HTTP after exit.
2. **Voice input exception logging** — Replaced bare `except Exception: pass` in `stop()`, `pause()`, `resume()` with `log.warning(..., exc_info=True)`. Device failures and recorder-state bugs are now visible in logs.
3. **File-open UI feedback** — `_load_file_by_path()` now shows status bar messages for binary files, oversized files, and unreadable paths. Users see why a file didn't open instead of silent no-ops.
4. **Ollama error-path test coverage** — Added 3 tests: `ConnectError` → `RuntimeError`, `ReadTimeout` → `RuntimeError`, malformed response → `KeyError`. These confirm the resilience path documented in `code_llm.py`.
5. **Editor lifecycle tests** — Added `test_shutdown_stops_server`, `test_shutdown_idempotent`, `test_close_shuts_down_editor`.
6. **Voice input logging tests** — Added `test_stop_logs_recorder_error`, `test_pause_logs_recorder_error`, `test_resume_logs_recorder_error`.
7. **Status bar feedback tests** — Added `test_load_binary_shows_statusbar`, `test_load_oversized_shows_statusbar`, `test_load_missing_file_shows_statusbar`.

Total suite: 108 tests passing (was 96).

### LLM Migration: Ollama → Gemini 2.5 Flash Lite — DONE (2026-04-12)

Goal: Replace local Ollama LLM (~9 GB VRAM) with hosted Gemini via the OpenAI-compatible SDK to free GPU resources for STT.

Completed work:
- **`harness/code_llm.py`** — Full rewrite: replaced `ollama`/`httpx` with `openai` SDK. Current model is `gemini-2.5-flash-lite`. Base URL set to `https://generativelanguage.googleapis.com/v1beta/openai/`. `chat()` now requires `api_key` param. Context budget increased from 12,000 → 100,000 chars. Timeout reduced to 120s (hosted inference is faster than local). Error handling: `AuthenticationError` → `RuntimeError("Invalid API key")`, `APIConnectionError`/`APITimeoutError` → `RuntimeError("LLM unavailable")`.
- **`harness/coordinator.py`** — Added `_api_key` field + `set_api_key()` method. `_process_message()` resolves key from field or `GEMINI_API_KEY` env var. Emits `error_occurred` if no key configured.
- **`harness/audio_settings.py`** — Added `api_key()`/`set_api_key()` with QSettings persistence under `"llm/api_key"`.
- **`ui/ai_panel.py`** — Added LLM Settings collapsible section with password-masked API key field + Save button. Emits `api_key_changed(str)` signal.
- **`ui/main_window.py`** — Wires API key: loads from settings/env → pushes to coordinator + AI panel. Connects `api_key_changed` signal.
- **`main.py`** — Removed `OLLAMA_HOST` env var.
- **`requirements.txt`** — Removed `ollama>=0.2.0`, added `openai>=1.30.0`.
- **`setup/install.py`** — Removed Ollama preflight, `step_model()`, and connectivity check. Validation now checks `openai` import. Reduced from 7-step to 6-step wizard.
- **Tests rewritten/added**: `test_code_llm.py` TestChat mocks OpenAI instead of Ollama. `test_coordinator.py` updated for API key flow + 3 new tests. `test_audio_settings.py` + 4 API key tests. `test_ai_panel.py` + 7 LLM settings tests. `test_main_window.py` updated _FakeAudioSettings.
- Full suite after the change: **338 passed, 1 skipped**.

### Phase 5 QA: Review Corrections — DONE (2026-04-11)

Four-agent review identified 2 critical and 8 high/medium issues. All fixed:

1. **CRITICAL — Edit detection pipeline restored** — `_process_message()` was calling
   `chat_stream()` which already filtered SEARCH/REPLACE blocks via `split_sentences_streaming()`.
   The accumulated `full_response_parts` contained only prose, so `parse_search_replace()` always
   returned `[]`. Fix: added `chat_stream_raw()` to `code_llm.py` that yields raw text deltas;
   coordinator now uses `chat_stream_raw()` → `_capturing_stream()` (accumulates raw text) →
   `split_sentences_streaming()` (one-pass filter for TTS). Edit detection is fully operational.
2. **CRITICAL — Streaming TTS connected** — `MainWindow` never connected `tts_chunk_ready` signal
   to `TtsNavigator.append_chunk()`. Added `_on_tts_chunk_incremental()` handler: appends each
   chunk, enables TTS controls, and auto-plays on the first chunk.
3. **HIGH — Double sentence-splitting eliminated** — Fixed by #1: raw deltas go through
   `split_sentences_streaming()` exactly once.
4. **HIGH — Import ordering** — Moved `import git` from local-import group to third-party group
   in `coordinator.py`.
5. **HIGH — Test mocks corrected** — All coordinator test helpers updated: `chat_stream` →
   `chat_stream_raw`. `test_process_message_skips_tts_when_no_prose` signal spy connected before
   processing instead of after. Added 7 `chat_stream_raw` tests (incl. 3 error path tests for
   `AuthenticationError`, `APIConnectionError`, `APITimeoutError`). Added 4 incremental TTS
   connection tests in `test_main_window.py`.
6. **MEDIUM — Unused imports removed** — `import struct` from `voice_input.py`, `import wave`
   from `tts.py`.
7. **MEDIUM — Silent exception handlers logged** — `_on_voice_recording_state`,
   `_on_voice_status` in `coordinator.py` and `_start_word_highlight` in `tts_navigator.py` now
   log debug messages instead of silently passing.
8. **MEDIUM — Model name in AGENTS.md** — Updated from "Gemini 2.5 Pro" to "Gemini 2.5 Flash Lite"
   to match `MODEL = "gemini-2.5-flash"` in code.
9. **LOW — Duplicate gitpython** — Removed second `gitpython>=3.1.40` entry from
   `requirements.txt`.
10. **LOW — Phase 5 date** — Fixed from 2026-04-12 to 2026-04-11.

## Current Blockers / Risks

- **Real audio validation pending** — the full Python 3.11 audio environment must be used for
  end-to-end STT/TTS testing; `.venv-poc` is only suitable for Monaco/PyQt proof-of-concept work.
- **Audio UX still rough** — speaking/listening/TTS timing needs a dedicated stabilization pass
  before the app feels like a seamless voice-first coding tool.
- **Installer validation may be stale** — `setup/install.py` should be checked against the current
  dependency set after the RealtimeSTT/OpenWakeWord removal.
