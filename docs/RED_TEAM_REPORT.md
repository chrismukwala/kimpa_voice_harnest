# Voice Harness — Red Team Report
_Generated: April 26, 2026_
_Red Team Agents: Security · Performance · Resilience · Dependencies · UX_

---

## Executive Summary

The most dangerous structural weakness in this codebase is a **trifecta of silent failures**: a Whisper model load error produces no user-visible signal, a microphone open failure permanently kills the listen loop with no recovery path, and a missing API key emits an error only to the scrollable response log. Any one of these leaves the user staring at a status label that says "listening" while nothing works. On top of this, the `ApplicationShortcut` binding for Left/Right arrow keys fires even inside text input widgets, making it impossible to move the text cursor — a ship-blocking regression for the keyboard fallback path. These issues combine with a subtle `_project_root=None` path-check bypass that could allow an LLM-crafted response to write files outside the project boundary under specific invocation conditions.

---

## Severity Matrix

| Dimension         | Severity | Flagging Agent(s)                       |
|-------------------|----------|-----------------------------------------|
| Security          | HIGH     | redteam-security                        |
| Performance       | CRITICAL | redteam-performance                     |
| Resilience        | CRITICAL | redteam-resilience                      |
| Dependencies      | MEDIUM   | redteam-dependencies                    |
| UX / Workflow     | CRITICAL | redteam-ux                              |

---

## Cross-Cutting Findings

Issues flagged by two or more agents — structurally the most dangerous.

| Finding | Flagged By | Combined Severity |
|---------|-----------|------------------|
| Concurrent TTS threads race on shared Kokoro singleton | Performance + Resilience | CRITICAL |
| `_project_root=None` bypasses all path validation in `accept_edits` | Security + Resilience | HIGH |
| Full LLM stream collected before TTS starts — streaming architecture defeated | Performance + UX | HIGH |
| Silent failure chain: model load / mic fail / API key missing produce no prominent UI feedback | Resilience + UX | CRITICAL |
| `validate_path()` in `edit_applier.py` is dead code — authoritative path guard is unclear | Security + Dependencies | MEDIUM |

---

## Priority Action List

### P0 — SHOWSTOPPER (ship-blocker or data-loss risk)

- [ ] **[UX/REGRESSION]** `ui/main_window.py:203–206` — `ApplicationShortcut` binds `Qt.Key.Key_Left` and `Qt.Key.Key_Right` at application scope. These fire even when the user is typing in the manual query `QLineEdit`, the API key field, or any other text widget, hijacking the cursor keys for TTS navigation instead. Every keyboard-based interaction is broken. **Fix**: Change shortcut context to `WindowShortcut` and/or use `Shift+Left/Right`, or gate the handler so it only fires when no text widget has focus.

- [ ] **[SECURITY]** `harness/coordinator.py:236–250` — `accept_edits()` skips the entire path-containment check when `self._project_root is None`. `Coordinator(project_root=None)` is a valid call (e.g., future refactors, test harnesses) and leaves arbitrary file write unguarded. An LLM returning a malicious `SEARCH/REPLACE` targeting `C:\Windows\System32\drivers\etc\hosts` would pass unchecked. **Fix**: If `_project_root` is `None`, validate that `file_path` matches `_current_file_path` (i.e., only the open file is writable). Raise/emit error and return `False` if neither check passes.

- [ ] **[SECURITY]** `harness/code_llm.py:50–55` — File content is passed verbatim into the LLM user message with no sanitisation. A maliciously crafted source file (prompt injection) can override the system prompt and direct the LLM to emit `SEARCH/REPLACE` blocks targeting arbitrary paths. Combined with the P0 path-check bypass above, this is exploitable. **Fix**: Wrap file content in a clearly delimited "data" block with explicit instructions that content inside cannot override system rules; add a pre-send check for `<<<<<<< SEARCH` patterns within the file context (indicating a nested injection attempt).

### P1 — CRITICAL (breaks under normal use or exposes sensitive data)

- [ ] **[PERFORMANCE]** `harness/voice_input.py:145` — `compute_type="int8"` is used for the Whisper CUDA model. `AGENTS.md` explicitly requires `"int8_float16"` for the RTX 4080. `int8` on CUDA is slower and less accurate than the validated configuration. **Fix**: Change to `compute_type="int8_float16"`.

- [ ] **[PERFORMANCE]** `harness/coordinator.py:301–309` — The streaming LLM pipeline is fully defeated: `full_response = "".join(code_llm.chat_stream_raw(...))` collects the entire response before any TTS starts. The `speak_stream` / `split_sentences_streaming` infrastructure exists but is only used _after_ the full response arrives. For long LLM responses, TTS latency equals full generation time. **Fix**: In `_process_message`, process `chat_stream_raw` lazily: feed chunks into `split_sentences_streaming` as a live iterator and pass that into `speak_stream` in the TTS thread, so the first TTS chunk begins as soon as the first sentence completes.

- [ ] **[RESILIENCE]** `harness/voice_input.py:127–130` — If Whisper model load fails in `_preload_model`, `log.error(...)` is called but `_error_callback` has not been registered yet at that point. The listen loop later detects `self._model is None` and sets `self._running = False; return` — silently. No error signal reaches the UI. **Fix**: Store the error message and re-emit via `_emit_error` after the listen loop detects the failure, which is after callbacks have been registered via `start()`.

- [ ] **[RESILIENCE]** `harness/voice_input.py:228–233` — Mic open failure (`sd.InputStream` raises) sets `self._running = False; break`, permanently killing the listen loop. There is no retry, no recovery button, no way to restart listening short of restarting the app. **Fix**: Replace the permanent kill with a retry loop: sleep 2s and retry mic open up to N times, emitting a status update on each attempt; after N failures, emit error and set running=False.

- [ ] **[RESILIENCE/PERFORMANCE]** `harness/tts.py:32–40` and `harness/coordinator.py:362` — Multiple TTS threads can run concurrently (rapid queries), both calling `pipeline(sentence, voice="af_heart")` on the shared `_pipeline` Kokoro singleton. Kokoro's thread safety is not documented. On a 12GB VRAM budget already loaded with Whisper, two concurrent Kokoro synthesis passes risk OOM or corrupt synthesis state. **Fix**: Add a `threading.Lock` around the `pipeline(...)` call in `speak_stream`, or use a single-threaded TTS dispatch queue so only one sentence synthesises at a time.

- [ ] **[SECURITY]** `harness/audio_settings.py:42–47` — The Gemini API key is stored via `QSettings.setValue(_API_KEY_KEY, key)`. On Windows, QSettings defaults to the registry (`HKEY_CURRENT_USER\Software\...`) in plain text. Any process running as the same user can read it. **Fix**: Use `win32crypt.CryptProtectData` (Windows Data Protection API) to encrypt before storing, and `CryptUnprotectData` on load. Provide a fallback to env var only with a clear warning if the DPAPI is unavailable.

### P2 — HIGH (significant friction, latency, or reliability risk)

- [ ] **[UX]** `ui/main_window.py:168–169` — `DiffPanel` is instantiated without a parent widget (`self._diff_panel = DiffPanel()`). In PyQt6, a parentless QWidget becomes a top-level window. `show_diff()` calls `self.show()`, which pops it up as a free-floating, possibly off-screen window rather than inline in the IDE layout. **Fix**: Either give `DiffPanel` the main window as parent (so it appears inside the window), or integrate it into the main splitter between the editor and AI panel.

- [ ] **[UX]** `ui/ai_panel.py` — Wake word checkbox (`_wake_word_check`) is visible and interactive but `Coordinator.set_wake_word_enabled()` is a documented no-op (`pass`). Clicking the checkbox has zero effect. **Fix**: Either remove the checkbox (it's dead UI), or show it as disabled with a tooltip: "Wake word support removed in Phase 5."

- [ ] **[UX]** `harness/coordinator.py:194–200` — `_on_stt_text` routes STT transcription to the UI preview box only, requiring a manual Send click. The project goal is voice-first — a spoken command should not require a mouse click to submit. **Fix**: After populating the query box, auto-submit after a short confirmation delay (e.g., 1.5s with a visible countdown) that the user can cancel. Or add a voice confirmation mode ("submit on next silence after transcription").

- [ ] **[RESILIENCE]** `harness/coordinator.py:224` — The pipeline queue `queue.Queue()` has no maximum size. Rapid speech-to-Send actions queue arbitrarily many LLM requests, each backed by a 120-second timeout. Under rapid input, the queue grows unboundedly and the system could be processing queries for minutes after the user stops talking. **Fix**: Set `maxsize=3`; when full, emit a "busy" message and discard new submissions.

- [ ] **[PERFORMANCE]** `harness/coordinator.py:220–222` — `refresh_repo_map()` runs synchronously at the start of `_pipeline_loop`, blocking the worker thread from processing any query until tree-sitter has walked the entire project tree. For large repos, this can take 5–15 seconds. **Fix**: Run repo map generation in a separate thread, or use `threading.Thread(target=self.refresh_repo_map, daemon=True).start()` before entering the loop.

- [ ] **[SECURITY/DEPS]** `harness/edit_applier.py:18–31` — `validate_path()` is a well-tested public function that checks for path traversal and absolute paths, but it is **never called** in `coordinator.accept_edits()`. The coordinator has its own `realpath` check, but `validate_path` remains dead code creating false confidence in test coverage. **Fix**: Either call `validate_path` as a first-pass check in `accept_edits`, or delete the function and its tests and consolidate the validation logic.

### P3 — MEDIUM (tech debt, polish, and hardening)

- [ ] **[DEPS]** `requirements.txt:15` — `ctranslate2==4.4.0` is a hard pin on an old release. Any upstream CVE cannot be patched. Similarly `onnxruntime>=1.18.0,<1.19.0` allows only one patch version. **Fix**: Document the exact CUDA/cuDNN constraint in `requirements.txt` comments; test with ctranslate2==4.4.x range; periodically re-evaluate upper bounds.

- [ ] **[DEPS]** `requirements.txt:21,23` — `kokoro>=0.9.0` and `openai>=1.30.0` have no upper bounds. Kokoro is in active development; a 1.0 release could silently change the `KPipeline` API or the `pipeline(sentence, voice="af_heart")` call signature. **Fix**: Add `<1.0.0` and `<2.0.0` upper bounds respectively until compatibility is validated.

- [ ] **[RESILIENCE]** `ui/main_window.py:298–302` — `_on_accept_edits` guards against stale proposals using `os.path.normpath()` comparison, but `normpath` is case-sensitive on Windows while the filesystem is not. A proposal for `C:\Project\Main.py` vs editor path `c:\project\main.py` (different case) would incorrectly reject a valid accept. **Fix**: Use `os.path.normcase(os.path.normpath(...))` for both sides of the comparison.

- [ ] **[PERFORMANCE]** `harness/edit_applier.py:47–68` — `_fuzzy_find_and_replace` is O(N) SequenceMatcher comparisons for every edit, where N is the number of possible starting positions. For a 5000-line file with a 5-line search block, this is ~5000 SequenceMatcher calls. **Fix**: Pre-filter candidates using a hash of the first/last line before running SequenceMatcher; or limit fuzzy matching to a sliding window of ±10 lines around an initial exact search for the first line.

- [ ] **[RESILIENCE]** `harness/voice_input.py` module-level globals `WhisperModel` and `webrtcvad` — These are set lazily and shared across all `VoiceInput` instances via global mutation. Multiple instances (e.g., parallel test runs) race on assignment. **Fix**: Move to instance-level imports inside `_load_model` and `_create_vad`; the globals are only needed to avoid re-importing, which Python's import cache handles anyway.

- [ ] **[UX]** `main.py:58` — `coordinator.set_ptt_mode(True)` is the default, but there is no global keyboard hotkey for PTT (only the on-screen button). A voice-first assistant requires a hardware-accessible PTT shortcut. The "Hold to Talk" button is mouse-only. **Fix**: Register a global hotkey (e.g., `F2` or configurable) via `pynput` or Qt global event filter for PTT press/release.

- [ ] **[UX]** All error conditions — `coordinator.error_occurred` → `lambda msg: self._ai_panel.append_response(f"⚠ Error: {msg}")`. Critical errors (no API key, mic dead, model not loaded) are appended to the scrolling response log where they can be missed entirely. **Fix**: Add a dedicated error banner widget at the top of the AI panel that appears on critical errors and requires explicit dismissal; reserve the response log for LLM output only.

- [ ] **[RESILIENCE]** `harness/tts.py:speak_stream` — If `np.concatenate(audio_chunks)` raises (e.g., mismatched dtypes from a Kokoro version change), it propagates unhandled out of the generator, killing the entire `_run_tts` thread mid-stream. **Fix**: Wrap the concatenate + sf.write block in a per-sentence try/except and `continue` on failure, so one bad sentence doesn't abort the rest of the response.

### P4 — LOW (minor issues worth tracking)

- [ ] **[SECURITY]** `main.py:7` — `os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"` silences Intel MKL duplicate-library warnings. These warnings can indicate a misconfigured environment or a dependency that loaded conflicting native libraries. Silencing them hides diagnostic signal.

- [ ] **[SECURITY]** `ui/editor_panel.py:252` — `QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls` is set to `True`. This allows Monaco JS to make outbound HTTP requests. While Monaco itself is well-audited, any future script injection in the editor view could exfiltrate data to remote servers. Evaluate whether this setting is still required.

- [ ] **[UX]** `ui/main_window.py` — TTS navigation keyboard shortcuts (Left/Right/Space/Escape) are not documented anywhere in the UI — no tooltips, no Help menu, no on-screen hint. Discoverability is zero.

- [ ] **[UX]** `ui/ai_panel.py:_api_key_input` — The API key field retains its value as password-masked dots after saving. A future "Clear API Key" action or timeout would improve key hygiene. Low risk because the field uses `EchoMode.Password`.

- [ ] **[DEPS]** `harness/git_ops.py` — `gitpython>=3.1.40` excludes CVE-2022-24439 (cmd injection, affects <3.1.30). The current floor is safe but should be noted for periodic re-evaluation.

- [ ] **[RESILIENCE]** `ui/main_window.py:_on_tts_stop_requested` — Checks `if not self._tts_nav.is_playing: return`. However, `is_playing` is set/cleared across threads without a lock. In a race between the playback thread completing and the user clicking Stop, `is_playing` may be stale. The consequence is benign (double-stop is a no-op) but the pattern should be audited.

---

## Individual Agent Reports

### Security Report

**redteam-security** — Attack surface: OWASP Top 10, secret exposure, injection risks, unsafe file operations.

#### SEC-1: Prompt Injection via File Content (HIGH)
`harness/code_llm.py:50–55` — File content is inserted directly into the LLM user message:
```python
user_parts.append(f"## Currently open file\n```\n{truncated}\n```\n")
```
A source file containing `<<<<<<< SEARCH ... >>>>>>> REPLACE` patterns, or explicit instruction-override text, passes directly to the LLM with no sanitisation. The attacker scenario: a developer opens a dependency file from an untrusted package that contains injected instructions; the LLM follows them and generates `SEARCH/REPLACE` blocks targeting sensitive files. Combined with SEC-2, this could result in arbitrary file write.

#### SEC-2: Path Validation Bypass When `_project_root` is None (HIGH)
`harness/coordinator.py:236–250`:
```python
if self._project_root:
    try:
        real_file = os.path.realpath(file_path)
        real_root = os.path.realpath(self._project_root)
        if not real_file.startswith(real_root + os.sep) ...
```
The entire guard is conditional on `self._project_root` being truthy. `Coordinator(project_root=None)` is a valid constructor call. `main.py` always passes a root, but this is not enforced by the type system or assertions. The result: an LLM-directed write to any absolute path on the filesystem passes unchecked when `_project_root` is None.

#### SEC-3: API Key Stored Plaintext in QSettings / Registry (HIGH)
`harness/audio_settings.py:42–47` — `QSettings.setValue(_API_KEY_KEY, key)` stores the Gemini API key in the Windows registry under `HKEY_CURRENT_USER` in plain text. Any malware or process running as the same user can read it via `reg query`. The key provides paid LLM access and should be protected at rest using DPAPI.

#### SEC-4: Dead Code Creates False Security Confidence (MEDIUM)
`harness/edit_applier.py:18–31` — `validate_path()` performs path traversal detection and is covered by tests, but is **never called** in the production file-write path. The actual guard (`os.path.realpath` comparison in coordinator) is different and less tested. A developer reading `edit_applier.py` would believe path validation is active; it is not.

#### SEC-5: `KMP_DUPLICATE_LIB_OK=TRUE` Silences Diagnostic Warnings (LOW)
`main.py:7` — This suppresses Intel MKL multi-load warnings that could indicate a corrupted or conflicting native library setup. Harmless in normal operation, but hides important diagnostic signal.

#### SEC-6: `LocalContentCanAccessRemoteUrls=True` in WebEngine (LOW)
`ui/editor_panel.py:252` — Grants the Monaco QWebEngine view permission to make outbound HTTP requests. Acceptable for Monaco's AMD module loader, but should be re-evaluated if any user-controlled content could be executed in the view.

---

### Performance Report

**redteam-performance** — Attack surface: UI thread blocking, VRAM budget violations, memory leaks, audio pipeline latency failures.

#### PERF-1: Wrong Whisper `compute_type` on CUDA (CRITICAL)
`harness/voice_input.py:145`:
```python
self._model = WhisperModel("base.en", device="cuda", compute_type="int8")
```
`AGENTS.md` explicitly requires `"int8_float16"` for the RTX 4080 setup. `int8` uses integer-only compute paths that are slower on NVIDIA tensor cores optimised for mixed-precision operations. This is the validated-and-documented spec deviation. STT latency will be measurably higher than the project target.

#### PERF-2: Streaming LLM Architecture Fully Defeated (CRITICAL)
`harness/coordinator.py:301–309`:
```python
full_response = "".join(
    code_llm.chat_stream_raw(query, context=context, repo_map=repo_map, api_key=api_key)
)
```
`chat_stream_raw` returns a generator but `"".join(...)` consumes it entirely before any processing begins. TTS latency = full LLM generation time. The `split_sentences_streaming` and `speak_stream` infrastructure was built for incremental processing but is only used on the already-complete string. The "first TTS word target: begin playback while the response is still generating" (PROJECT.md) is unachievable in the current pipeline.

#### PERF-3: Repo Map Blocks Pipeline Worker at Startup (HIGH)
`harness/coordinator.py:220–222`:
```python
def _pipeline_loop(self):
    self.refresh_repo_map()  # synchronous, blocks for tree-sitter walk
    while not self._stop_event.is_set():
        ...
```
For a project with hundreds of files, tree-sitter parsing all of them can take 5–15 seconds. The pipeline worker is blocked during this time and cannot process the user's first query. If the user speaks immediately after the app appears ready, their first query is silently queued and delayed.

#### PERF-4: Multiple Concurrent TTS Threads on Rapid Queries (HIGH)
`harness/coordinator.py:357–362` — Each `_process_message` call spawns a new `tts_thread`. Two queries within the TTS synthesis window launch two threads both calling `pipeline(sentence, voice="af_heart")` on the shared `_pipeline` Kokoro singleton. The VRAM budget is 12 GB; two concurrent Kokoro GPU inferences may exceed the budget or produce corrupted audio.

#### PERF-5: `_fuzzy_find_and_replace` O(N·M) Complexity (MEDIUM)
`harness/edit_applier.py:47–68` — The fuzzy matcher iterates every possible starting position and runs `SequenceMatcher` for each. For a 2000-line file with a 5-line search block, this is ~2000 SequenceMatcher invocations. In practice this could add 500ms–2s to edit proposal latency for large files.

#### PERF-6: Word Highlight Timer Resolution on Windows (LOW)
`harness/tts_navigator.py` — Per-word highlight intervals are computed by dividing estimated audio duration by word count. Windows' QTimer has ~15ms resolution. At playback speed 3.0x and a sentence with many short words, computed intervals may be < 15ms, causing several words to highlight simultaneously in a single timer callback. The visual effect is highlight "bunching," not a crash.

---

### Resilience Report

**redteam-resilience** — Attack surface: hardware outages, API failures, silent exception swallowing, and unrecoverable states.

#### RES-1: Mic Open Failure Permanently Kills Listen Loop (CRITICAL)
`harness/voice_input.py:228–233`:
```python
except (RuntimeError, OSError, sd.PortAudioError) as exc:
    self._emit_error(f"Mic open failed: {exc}")
    self._running = False
    break
```
After a single mic failure (device unplugged, driver crash, exclusive-mode lock), the loop exits permanently. The app continues to run but silently ignores all further voice input. There is no retry mechanism, no "Reconnect" button, and no change to the status indicator. The user sees `"Listening"` but nothing works.

#### RES-2: Whisper Model Load Failure Produces No UI Error (CRITICAL)
`harness/voice_input.py:127–130` in `_preload_model`: calls `log.error(...)` and returns. `_error_callback` is `None` at preload time (registered later via `on_error()`). The listen loop detects `self._model is None` → sets `self._running = False; return`. The `_emit_error` path is never taken. The user sees no error message anywhere — the app appears ready but STT is permanently dead.

#### RES-3: Kokoro Singleton Concurrent Access (CRITICAL)
`harness/tts.py:_get_pipeline()` — Double-checked locking correctly protects object _creation_. But `pipeline(sentence, voice="af_heart")` is called without any lock, and two TTS threads can execute this simultaneously. Kokoro 0.9.x makes no thread-safety guarantees. Possible outcomes: corrupted audio output, GPU memory corruption, or Python-level AttributeError mid-synthesis.

#### RES-4: Pipeline Queue Unbounded — No Backpressure (HIGH)
`harness/coordinator.py:68` — `queue.Queue()` with no `maxsize`. Under rapid repeated voice-to-Send (or adversarial keyboard mashing), the queue fills with 120-second-timeout LLM requests. The system continues processing stale queries for minutes. The user has no way to cancel the queue.

#### RES-5: Edit Accept Uses Non-Case-Insensitive Path Comparison (MEDIUM)
`ui/main_window.py:298–302` — `os.path.normpath(current_path) != os.path.normpath(proposal["file_path"])`. On Windows, `normpath` does not lowercase, but NTFS paths are case-insensitive. A proposal for `C:\Project\Main.py` with editor path `c:\project\main.py` (different capitalisation) is incorrectly rejected as a stale proposal.

#### RES-6: TTS Sentence Crash Aborts Entire Response (MEDIUM)
`harness/tts.py:speak_stream` — If `np.concatenate(audio_chunks)` or `sf.write(buf, ...)` raises for a single sentence (dtype mismatch, empty chunks), the exception propagates out of the generator, killing the `_run_tts` thread. The remainder of the response is never synthesised and never emitted.

#### RES-7: Stop/Join Race in `VoiceInput.stop()` (LOW)
`harness/voice_input.py:stop()` — `self._running = False; self._stop_stream()` then joins with `timeout=2.0`. If the model is still loading (`_model_ready.wait()` blocks indefinitely), the join timeout silently expires. The thread remains alive and could call back into a partially-destroyed object.

#### RES-8: `_tts_playback_active` Flag Access Across Threads (LOW)
`harness/coordinator.py:begin_tts_playback / finish_tts_playback` — `_tts_playback_active` is read/written from the pipeline worker thread (via `_run_tts` → signal back to UI) and the Qt main thread without a lock. On CPython the GIL prevents torn reads, but the logic (guard on `if not self._tts_playback_active`) is not atomic.

---

### Dependency & Maintainability Report

**redteam-dependencies** — Attack surface: dependency tree, install process, module coupling, dead code, and long-term rot.

#### DEP-1: `ctranslate2==4.4.0` Hard Pin — Cannot Patch CVEs (HIGH)
`requirements.txt:15` — An exact pin on a library with C++ GPU code. Any vulnerability discovered in ctranslate2 4.4.0 cannot be addressed without a full upgrade that requires cuDNN 9.2. This is a known architectural debt with no current exit path.

#### DEP-2: `onnxruntime>=1.18.0,<1.19.0` — One-Patch-Version Window (HIGH)
`requirements.txt:16` — The narrowest possible SemVer range. Any security patch in 1.18.x releases is fine; but if the DLL conflict was resolved in 1.19+, the constraint must be manually revisited or the project is stuck with a known-vulnerable version.

#### DEP-3: `webrtcvad-wheels` — Abandoned Library (MEDIUM)
`requirements.txt:17` — The upstream `webrtcvad` library has had no commits since ~2019. The `-wheels` variant is a third-party repackage with prebuilt Windows binaries. No CVE tracking, no security reviews, no maintenance. Any WebRTC vulnerability in the native VAD code has no upstream fix path.

#### DEP-4: `kokoro>=0.9.0` — No Upper Bound on Active-Development Package (MEDIUM)
`requirements.txt:21` — Kokoro is actively developed. The 0.9.x API (`KPipeline(lang_code="a", device=...)` and `pipeline(text, voice="af_heart")`) could change in 1.0 without notice, silently breaking TTS synthesis.

#### DEP-5: `openai>=1.30.0` — No Upper Bound (MEDIUM)
`requirements.txt:22` — The OpenAI Python SDK has had a major breaking change (0.x → 1.x). Another major version could silently break the `base_url=BASE_URL` Gemini endpoint pattern.

#### DEP-6: `validate_path()` Dead Production Code (MEDIUM)
`harness/edit_applier.py:18–31` — This function is tested (adds to test count) but never called in the actual write path. It creates a false impression of security coverage. Tests for dead code inflate confidence metrics.

#### DEP-7: Module-Level Globals `WhisperModel` / `webrtcvad` Are Not Thread-Safe (MEDIUM)
`harness/voice_input.py:14–15` — Two `VoiceInput` instances (in parallel tests or future multi-mic scenarios) would race on `global WhisperModel; if WhisperModel is None: WhisperModel = _WM`. CPython's GIL prevents torn assignment but the check-then-set is not atomic and two threads could both enter the `if` branch.

#### DEP-8: `tree-sitter-languages>=1.10.0` — Compiled Grammar Library, No Upper Bound (LOW)
`requirements.txt:26` — Bundles pre-compiled native grammars. A major version could rename language keys in `_EXT_TO_LANG`, silently producing empty repo maps with no error.

#### DEP-9: GitPython CVE History — Version Floor is Safe, But Periodic Audit Needed (LOW)
`requirements.txt:24` — `>=3.1.40` excludes CVE-2022-24439 (cmd injection via URL, patched in 3.1.30) and CVE-2023-40590 (patched in 3.1.41). Floor is currently safe but should be bumped periodically as new CVEs are disclosed.

---

### UX & Workflow Report

**redteam-ux** — Attack surface: voice feedback blindness, missing error states, diff review gaps, TTS navigation discoverability, and keyboard accessibility.

#### UX-1: Arrow Key ApplicationShortcuts Break Text Editing (CRITICAL / SHIP BLOCKER)
`ui/main_window.py:203–206` — `Qt.ShortcutContext.ApplicationShortcut` for `Key_Left` and `Key_Right` intercepts these keys globally, including when the cursor is in a `QLineEdit` or `QPlainTextEdit`. Every time the user attempts to move the text cursor in the query box, the TTS navigator fires instead. Keyboard fallback — the documented alternative to voice — is completely broken.

#### UX-2: DiffPanel Appears as Floating Window (CRITICAL)
`ui/main_window.py:168–169` — `DiffPanel()` is created with no parent. In PyQt6, parentless `QWidget` objects are top-level windows. `show_diff()` calls `self.show()`, which pops up a separate window that:
- May appear behind the main window
- Has no title bar or window decorations (unexpected for a dialog)
- Can appear on a different monitor
- Has no keyboard trap, so Escape does not dismiss it

The core accept/reject workflow is effectively hidden from the user.

#### UX-3: Wake Word Checkbox Is a Dead No-Op (HIGH)
`harness/coordinator.py:set_wake_word_enabled()` returns immediately (`pass`). The checkbox in the audio settings panel is visible, toggleable, and persisted to `QSettings`. It does nothing. A user enabling "Wake Word" will speak a trigger word and wonder why nothing happens — potentially spending significant time debugging.

#### UX-4: STT Requires Manual Send — Voice-First Promise Broken (HIGH)
`harness/coordinator.py:_on_stt_text` — STT transcription goes to `ai_panel.populate_query()` (fills the input box) but never auto-submits. `PROJECT.md` states the primary interaction is speech. A voice command requires: (1) speak, (2) wait for transcription, (3) click Send or press Enter. Step 3 requires mouse or keyboard. In PTT mode the user must press the on-screen button, then click Send. Two physical actions for every voice query.

#### UX-5: No Startup Loading Indicator (HIGH)
`main.py` — The app shows the full UI immediately on launch, but Whisper model loading takes 10–25s in the background. During this time the status label shows `"idle"` or briefly `"loading"` but there is no spinner, progress bar, or ETA. Users with no audio background will click Send, see nothing happen (the model isn't ready), and assume the app is broken. The 25–50s cold startup documented in PROJECT.md needs a visible loading indicator.

#### UX-6: All Errors Go to Scrolling Log (HIGH)
`ui/main_window.py:175–177` — `coordinator.error_occurred.connect(lambda msg: self._ai_panel.append_response(f"⚠ Error: {msg}"))`. Every error, including critical ones like "No API key configured," "Mic open failed," and "Whisper model load failed," are appended as plain text to the scrollable response log. If the log has previous content (multiple LLM exchanges), the error scrolls out of view immediately. There is no toast, no modal, no persistent banner.

#### UX-7: No PTT Global Keyboard Shortcut (MEDIUM)
`main.py:58` — PTT mode is the default (`coordinator.set_ptt_mode(True)`). The only PTT trigger is the on-screen "Hold to Talk" button. There is no keyboard shortcut. For a voice-first assistant, requiring the user to keep a mouse button held while speaking defeats the purpose. The Left/Right shortcuts demonstrate that the app *can* bind application-wide keys — but PTT has no hotkey.

#### UX-8: TTS Navigation Not Discoverable (MEDIUM)
Arrow key TTS navigation exists but is not documented anywhere in the UI — no tooltip on the `◄` / `►` buttons, no help text, no keyboard shortcut hint. The buttons themselves carry no tooltip. A new user has no way to know that Left/Right arrows navigate TTS (especially ironic given that those keys also break text editing — UX-1).

#### UX-9: No "Processing" Visual Feedback for Long LLM Requests (MEDIUM)
The state transitions to "processing" and the status label updates, but there is no animated spinner, progress ring, or animated dots. A 15–30 second LLM request shows a static "Processing" label. On Windows, a static UI during a long operation is commonly interpreted as a frozen application.

#### UX-10: API Key Not Cleared from Widget After Save (LOW)
`ui/ai_panel.py:_api_key_input` — After saving, the API key field retains its value as password-masked dots. The field is never cleared. If the user shares their screen (pair programming, demo), the masked field is visible and its presence confirms an API key is stored. A "Clear" button or auto-clear on focus-loss would improve security hygiene.
