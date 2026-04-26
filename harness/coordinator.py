"""Coordinator — queue pipeline: STT → context_assembler → LLM → response_splitter → TTS."""

import logging
import os
import queue
import threading
from typing import Iterator, Optional

from PyQt6.QtCore import QObject, pyqtSignal

import git as _git

from harness.voice_input import VoiceInput
from harness import code_llm
from harness import tts as tts_mod
from harness import edit_applier
from harness import git_ops
from harness import repo_map as repo_map_mod

log = logging.getLogger(__name__)

# Timeout (seconds) for blocking queue.get so the worker checks shutdown regularly.
_QUEUE_TIMEOUT = 1.0
_QUEUE_MAXSIZE = 3
_STREAM_SENTINEL = object()


class Coordinator(QObject):
    """Central pipeline connecting voice input → LLM → TTS → UI.

    Signals keep the UI updated from background threads.
    """

    # Signals — UI connects to these.
    state_changed = pyqtSignal(str)         # "idle" | "listening" | "processing" | "speaking"
    transcription_ready = pyqtSignal(str)   # final STT text
    llm_response_ready = pyqtSignal(str)    # full LLM response text
    prose_ready = pyqtSignal(str)           # prose portion (read aloud)
    tts_started = pyqtSignal()
    tts_finished = pyqtSignal()
    tts_chunks_ready = pyqtSignal(list)      # List[Tuple[str, bytes]] for TtsNavigator
    tts_chunk_ready = pyqtSignal(str, object)  # Phase 5: incremental (sentence, wav_bytes)
    error_occurred = pyqtSignal(str)
    recording_active_changed = pyqtSignal(bool)
    edits_proposed = pyqtSignal(dict)       # {file_path, edits, original, modified}
    edits_applied = pyqtSignal(str)         # file_path after accept

    def __init__(self, project_root: Optional[str] = None):
        super().__init__()
        self._project_root = project_root
        self._voice = VoiceInput()
        self._voice.on_text(self._on_stt_text)
        self._voice.on_error(self._on_voice_error)
        self._voice.on_recording_state(self._on_voice_recording_state)
        self._voice.on_status(self._on_voice_status)
        self._tts_playback_active = False

        # Pipeline queue — each item is a message dict.
        self._queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Lock protects _current_file_content, _current_file_path, _repo_map.
        self._context_lock = threading.Lock()

        # Current file context (set by editor panel when user opens a file).
        self._current_file_content: Optional[str] = None
        self._current_file_path: Optional[str] = None

        # Repo map — generated from project tree via tree-sitter (Phase 3b).
        self._repo_map: Optional[str] = None

        # API key for hosted LLM (set via UI or env var fallback).
        self._api_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the voice listener and the pipeline worker."""
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._pipeline_loop, daemon=True)
        self._worker_thread.start()
        self._voice.start()
        self.state_changed.emit("listening")

    def stop(self) -> None:
        """Shut everything down and wait for worker to exit."""
        self._stop_event.set()
        self._tts_playback_active = False
        self._voice.stop()
        try:
            self._queue.put_nowait(None)  # sentinel to unblock worker
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(None)
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=5.0)
            self._worker_thread = None

    def pause_listening(self) -> None:
        self._voice.pause()
        self.state_changed.emit("idle")

    def resume_listening(self) -> None:
        self._voice.resume()
        self.state_changed.emit("listening")

    def set_input_device(self, device_index: Optional[int]) -> None:
        """Apply a new microphone device through the voice adapter."""
        self._voice.set_input_device(device_index)

    def set_ptt_mode(self, enabled: bool) -> None:
        """Switch the voice input between push-to-talk and VAD mode."""
        self._voice.set_ptt_mode(enabled)

    def ptt_press(self) -> None:
        """Forward PTT button press to the voice input."""
        self._voice.ptt_press()

    def ptt_release(self) -> None:
        """Forward PTT button release to the voice input."""
        self._voice.ptt_release()

    def set_wake_word_enabled(self, enabled: bool) -> None:
        """No-op — wake word support removed in Phase 5."""
        pass

    def set_api_key(self, key: Optional[str]) -> None:
        """Set the API key for the hosted LLM."""
        self._api_key = key

    def begin_tts_playback(self) -> None:
        """Mark TTS playback as active and emit the speaking transition once."""
        if self._tts_playback_active:
            return
        self._tts_playback_active = True
        self.state_changed.emit("speaking")
        self.tts_started.emit()

    def finish_tts_playback(self) -> None:
        """Mark TTS playback as complete and return the UI to listening."""
        if not self._tts_playback_active:
            return
        self._tts_playback_active = False
        self.tts_finished.emit()
        self.state_changed.emit("listening")

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------
    def set_file_context(self, path: str, content: str):
        """Called by the editor panel whenever the active file changes."""
        with self._context_lock:
            self._current_file_path = path
            self._current_file_content = content

    def refresh_repo_map(self):
        """Regenerate the repo map from project root."""
        if not self._project_root:
            return
        try:
            map_text = repo_map_mod.generate_repo_map(self._project_root)
            with self._context_lock:
                self._repo_map = map_text if map_text else None
            log.info("Repo map generated: %d chars", len(map_text))
        except (OSError, ValueError, RuntimeError) as exc:
            log.warning("Failed to generate repo map: %s", exc)

    def clear_file_context(self):
        with self._context_lock:
            self._current_file_path = None
            self._current_file_content = None

    # ------------------------------------------------------------------
    # Manual text input (fallback for no mic)
    # ------------------------------------------------------------------
    def submit_text(self, text: str) -> None:
        """Enqueue a query typed in the manual input box."""
        self._enqueue(text)

    # ------------------------------------------------------------------
    # Internal: from STT callback → queue
    # ------------------------------------------------------------------
    def _on_stt_text(self, text: str):
        try:
            self.transcription_ready.emit(text)
        except RuntimeError:
            return
        # Intentionally NOT calling _enqueue here.
        # STT text goes to the UI preview box; the user reviews and clicks Send.

    def _on_voice_error(self, message: str) -> None:
        try:
            self.error_occurred.emit(message)
        except RuntimeError:
            log.warning("Coordinator deleted; swallowing error: %s", message)

    def _on_voice_recording_state(self, active: bool) -> None:
        try:
            self.recording_active_changed.emit(active)
        except RuntimeError:
            log.debug("Coordinator deleted; swallowing recording_state")

    def _on_voice_status(self, status: str) -> None:
        try:
            self.state_changed.emit(status)
        except RuntimeError:
            log.debug("Coordinator deleted; swallowing status: %s", status)

    def _enqueue(self, query: str):
        with self._context_lock:
            msg = {
                "query": query,
                "context": self._current_file_content,
                "repo_map": self._repo_map,
            }
        try:
            self._queue.put_nowait(msg)
        except queue.Full:
            self.error_occurred.emit("Voice Harness is busy; dropped the newest request")

    # ------------------------------------------------------------------
    # Pipeline worker (runs in background thread)
    # ------------------------------------------------------------------
    def _pipeline_loop(self):
        # Generate initial repo map for LLM context (Phase 3b).
        threading.Thread(target=self.refresh_repo_map, daemon=True).start()

        while not self._stop_event.is_set():
            try:
                msg = self._queue.get(timeout=_QUEUE_TIMEOUT)
            except queue.Empty:
                continue
            if msg is None:
                break
            try:
                self._process_message(msg)
            except Exception as exc:  # Last-resort pipeline guardrail
                self.error_occurred.emit(str(exc))
                self.state_changed.emit("listening")

    # ------------------------------------------------------------------
    # Accept / reject proposed edits
    # ------------------------------------------------------------------
    def accept_edits(self, file_path: str, modified_content: str) -> bool:
        """Write *modified_content* to *file_path* and auto-commit.

        Returns True on success, False on failure (emits error_occurred).
        """
        if not self._validate_edit_target(file_path):
            return False

        # --- Write file ---
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)
        except OSError as exc:
            self.error_occurred.emit(f"Failed to write {file_path}: {exc}")
            return False

        # --- Git commit with repo-relative path ---
        try:
            repo = _git.Repo(file_path, search_parent_directories=True)
            repo_root = repo.working_tree_dir
            rel_path = os.path.relpath(file_path, repo_root)
        except (
            ImportError,
            _git.exc.InvalidGitRepositoryError,
            _git.exc.NoSuchPathError,
            OSError,
        ) as exc:
            log.debug("Git repo lookup failed, using dirname: %s", exc)
            repo_root = os.path.dirname(file_path)
            rel_path = os.path.basename(file_path)

        committed = git_ops.auto_commit(
            repo_path=repo_root,
            file_path=rel_path,
            message=f"feat: Voice Harness edit to {os.path.basename(file_path)}",
        )
        if not committed:
            self.error_occurred.emit(
                f"File written but git commit failed for {file_path}"
            )
            # File was written — still emit edits_applied so UI reloads.
        self.edits_applied.emit(file_path)
        return True

    def reject_edits(self) -> None:
        """Discard proposed edits — no-op."""
        log.info("Edits rejected by user")

    def _validate_edit_target(self, file_path: str) -> bool:
        try:
            real_file = os.path.realpath(file_path)
            if self._project_root:
                real_root = os.path.realpath(self._project_root)
                common_path = os.path.commonpath([real_file, real_root])
                if os.path.normcase(common_path) != os.path.normcase(real_root):
                    self.error_occurred.emit(
                        f"Refusing edit outside project root: {file_path}"
                    )
                    return False
                rel_path = os.path.relpath(real_file, real_root)
                edit_applier.validate_path(rel_path, real_root)
                return True

            with self._context_lock:
                current_file = self._current_file_path
            if current_file is None:
                self.error_occurred.emit("Refusing edit without project root or open file")
                return False
            real_current = os.path.realpath(current_file)
            if os.path.normcase(real_file) != os.path.normcase(real_current):
                self.error_occurred.emit(
                    f"Refusing edit outside active file: {file_path}"
                )
                return False
            return True
        except (OSError, ValueError) as exc:
            self.error_occurred.emit(f"Path validation failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Pipeline worker (runs in background thread)
    # ------------------------------------------------------------------
    def _process_message(self, msg: dict):
        self.state_changed.emit("processing")

        query = msg["query"]
        context = msg["context"]
        repo_map = msg["repo_map"]

        # --- API key ---
        api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            self.error_occurred.emit("No API key configured — set one in LLM Settings")
            self.state_changed.emit("listening")
            return

        # --- Stream LLM response into a live TTS consumer ---
        try:
            raw_stream = code_llm.chat_stream_raw(
                query, context=context, repo_map=repo_map, api_key=api_key
            )
        except RuntimeError as exc:
            self.error_occurred.emit(str(exc))
            self.state_changed.emit("listening")
            return

        chunk_queue: queue.Queue = queue.Queue()
        stream_done = threading.Event()
        stream_errors: list[RuntimeError] = []
        full_response_parts: list[str] = []

        def produce_chunks() -> None:
            try:
                for chunk in raw_stream:
                    full_response_parts.append(chunk)
                    chunk_queue.put(chunk)
            except RuntimeError as exc:
                stream_errors.append(exc)
            finally:
                chunk_queue.put(_STREAM_SENTINEL)
                stream_done.set()

        def queued_chunks() -> Iterator[str]:
            while True:
                item = chunk_queue.get()
                if item is _STREAM_SENTINEL:
                    break
                yield item

        sentences = code_llm.split_sentences_streaming(queued_chunks())
        producer_thread = threading.Thread(target=produce_chunks, daemon=True)
        tts_thread = threading.Thread(
            target=self._run_tts, args=(sentences,), daemon=True
        )
        producer_thread.start()
        tts_thread.start()
        stream_done.wait()

        if stream_errors:
            self.error_occurred.emit(str(stream_errors[0]))
            self.state_changed.emit("listening")
            return

        full_response = "".join(full_response_parts)

        # Emit response to UI immediately — pipeline is now free.
        self.llm_response_ready.emit(full_response)

        # --- response_splitter (Phase 3a) ---
        prose = code_llm.extract_prose(full_response)
        edits = code_llm.parse_search_replace(full_response)
        self.prose_ready.emit(prose)

        # --- Propose edits if any SEARCH/REPLACE blocks found ---
        if edits and context is not None:
            with self._context_lock:
                file_path = self._current_file_path

            result = edit_applier.apply_edits(context, edits)
            if result.success and file_path:
                self.edits_proposed.emit({
                    "file_path": file_path,
                    "edits": edits,
                    "original": context,
                    "modified": result.content,
                    "used_fuzzy": result.used_fuzzy,
                })
            elif not result.success:
                for err in result.errors:
                    self.error_occurred.emit(f"Edit failed: {err}")

        # (Option B) Always return to listening before TTS starts.
        self.state_changed.emit("listening")

    def _run_tts(self, sentences: Iterator[str]) -> None:
        """Synthesise streaming sentences via Kokoro and emit chunks."""
        try:
            tts_chunks: list = []
            for sentence, wav_bytes in tts_mod.speak_stream(sentences):
                tts_chunks.append((sentence, wav_bytes))
                self.tts_chunk_ready.emit(sentence, wav_bytes)
            if tts_chunks:
                self.tts_chunks_ready.emit(tts_chunks)
        except Exception as exc:
            log.warning("TTS synthesis failed: %s", exc)
            try:
                self.error_occurred.emit(f"TTS error: {exc}")
            except RuntimeError:
                pass
