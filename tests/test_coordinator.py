"""Tests for harness/coordinator.py — message format, enqueue, lifecycle."""

import os
import queue
import threading
from unittest.mock import patch, MagicMock

import pytest

from harness.coordinator import Coordinator


class _SyncThread:
    """Thread stand-in that runs its target synchronously — for TTS signal tests."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


@pytest.fixture
def coordinator():
    """Create a Coordinator with mocked VoiceInput (no mic required)."""
    with patch("harness.coordinator.VoiceInput") as MockVI:
        mock_vi = MagicMock()
        MockVI.return_value = mock_vi
        coord = Coordinator()
        yield coord
        # Ensure cleanup.
        coord._stop_event.set()


class TestMessageFormat:
    """The coordinator message format is a critical contract (ADR-006)."""

    def test_enqueue_creates_correct_message_shape(self, coordinator):
        coordinator._enqueue("hello")
        msg = coordinator._queue.get_nowait()

        assert "query" in msg
        assert "context" in msg
        assert "repo_map" in msg
        assert msg["query"] == "hello"

    def test_enqueue_includes_file_context(self, coordinator):
        coordinator.set_file_context("/path/to/file.py", "print('hi')")
        coordinator._enqueue("fix it")
        msg = coordinator._queue.get_nowait()

        assert msg["context"] == "print('hi')"

    def test_enqueue_without_context_has_none(self, coordinator):
        coordinator._enqueue("do something")
        msg = coordinator._queue.get_nowait()

        assert msg["context"] is None
        assert msg["repo_map"] is None

    def test_message_keys_are_exactly_three(self, coordinator):
        coordinator._enqueue("test")
        msg = coordinator._queue.get_nowait()
        assert set(msg.keys()) == {"query", "context", "repo_map"}


class TestFileContext:
    """Verify file context management."""

    def test_set_file_context(self, coordinator):
        coordinator.set_file_context("/a/b.py", "content")
        assert coordinator._current_file_path == "/a/b.py"
        assert coordinator._current_file_content == "content"

    def test_clear_file_context(self, coordinator):
        coordinator.set_file_context("/a/b.py", "content")
        coordinator.clear_file_context()
        assert coordinator._current_file_path is None
        assert coordinator._current_file_content is None


class TestSubmitText:
    """Manual text input should enqueue like voice input."""

    def test_submit_text_enqueues_message(self, coordinator):
        coordinator.submit_text("manual query")
        msg = coordinator._queue.get_nowait()
        assert msg["query"] == "manual query"

    def test_stt_text_does_not_enqueue(self, coordinator):
        """STT text goes to the preview box — the user confirms with Send."""
        coordinator._on_stt_text("hello world test")
        import queue as _q
        with pytest.raises(_q.Empty):
            coordinator._queue.get_nowait()

    def test_stt_text_emits_transcription_ready(self, coordinator):
        received = []
        coordinator.transcription_ready.connect(lambda t: received.append(t))
        coordinator._on_stt_text("hello world test")
        assert received == ["hello world test"]


class TestPTT:
    """Push-to-talk proxy methods forward to VoiceInput."""

    def test_ptt_press_calls_voice(self, coordinator):
        coordinator.ptt_press()
        coordinator._voice.ptt_press.assert_called_once()

    def test_ptt_release_calls_voice(self, coordinator):
        coordinator.ptt_release()
        coordinator._voice.ptt_release.assert_called_once()

    def test_set_ptt_mode_calls_voice(self, coordinator):
        coordinator.set_ptt_mode(True)
        coordinator._voice.set_ptt_mode.assert_called_once_with(True)


class TestLifecycle:
    """Verify start/stop/pause/resume state transitions."""

    def test_stop_sets_event(self, coordinator):
        coordinator.stop()
        assert coordinator._stop_event.is_set()
        # Sentinel value should be in queue.
        sentinel = coordinator._queue.get_nowait()
        assert sentinel is None

    def test_initial_state(self, coordinator):
        assert not coordinator._stop_event.is_set()
        assert coordinator._worker_thread is None

    def test_pause_listening_calls_voice_pause(self, coordinator):
        coordinator.pause_listening()
        coordinator._voice.pause.assert_called_once()

    def test_pause_listening_emits_idle(self, coordinator):
        received = []
        coordinator.state_changed.connect(lambda s: received.append(s))
        coordinator.pause_listening()
        assert "idle" in received

    def test_resume_listening_calls_voice_resume(self, coordinator):
        coordinator.resume_listening()
        coordinator._voice.resume.assert_called_once()

    def test_resume_listening_emits_listening(self, coordinator):
        received = []
        coordinator.state_changed.connect(lambda s: received.append(s))
        coordinator.resume_listening()
        assert "listening" in received

    def test_set_input_device_calls_voice_input(self, coordinator):
        coordinator.set_input_device(5)
        coordinator._voice.set_input_device.assert_called_once_with(5)

    def test_set_wake_word_enabled_is_noop(self, coordinator):
        """Phase 5 — wake word removed, method is a no-op."""
        coordinator.set_wake_word_enabled(True)
        # Should not forward to voice input — it's a pass-through no-op.

    def test_set_api_key_stores_key(self, coordinator):
        coordinator.set_api_key("my-secret-key")
        assert coordinator._api_key == "my-secret-key"

    def test_voice_error_emits_error_signal(self, coordinator):
        received = []
        coordinator.error_occurred.connect(lambda msg: received.append(msg))

        coordinator._on_voice_error("mic failed")

        assert received == ["mic failed"]

    def test_recording_active_changed_signal(self, coordinator):
        received = []
        coordinator.recording_active_changed.connect(lambda active: received.append(active))

        coordinator._on_voice_recording_state(True)
        coordinator._on_voice_recording_state(False)

        assert received == [True, False]


class TestProcessMessage:
    """Verify _process_message calls streaming LLM and TTS in order."""

    @staticmethod
    def _setup_streaming_mocks(mock_llm, mock_tts, response_text, prose=""):
        """Wire up chat_stream_raw → split_sentences_streaming → speak_stream mocks."""
        mock_llm.chat_stream_raw.return_value = iter([response_text])
        mock_llm.extract_prose.return_value = prose
        mock_llm.parse_search_replace.return_value = []

        def fake_splitter(chunks):
            for chunk in chunks:
                pass  # consume so _capturing_stream populates full_response_parts
            if prose:
                yield prose

        mock_llm.split_sentences_streaming.side_effect = fake_splitter

        def fake_speak(sentences):
            for s in sentences:
                yield (s, b"wav")

        mock_tts.speak_stream.side_effect = fake_speak

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_calls_llm(self, mock_llm, mock_tts, coordinator):
        self._setup_streaming_mocks(mock_llm, mock_tts, "response text")

        coordinator._api_key = "test-key"
        msg = {"query": "hello", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_llm.chat_stream_raw.assert_called_once_with(
            "hello", context=None, repo_map=None, api_key="test-key"
        )

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_skips_tts_when_no_prose(self, mock_llm, mock_tts, coordinator):
        self._setup_streaming_mocks(
            mock_llm, mock_tts,
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
        )

        # Connect signal spy BEFORE processing so it captures any emissions.
        received = []
        coordinator.tts_chunk_ready.connect(lambda s, w: received.append((s, w)))

        coordinator._api_key = "test-key"
        msg = {"query": "fix it", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 0

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_calls_tts_when_prose_exists(self, mock_llm, mock_tts, coordinator):
        self._setup_streaming_mocks(
            mock_llm, mock_tts, "I fixed the bug.", prose="I fixed the bug."
        )

        received = []
        coordinator.tts_chunks_ready.connect(lambda chunks: received.append(chunks))

        coordinator._api_key = "test-key"
        msg = {"query": "fix it", "context": None, "repo_map": None}
        with patch("harness.coordinator.threading.Thread", new=_SyncThread):
            coordinator._process_message(msg)

        assert len(received) == 1
        assert received[0] == [("I fixed the bug.", b"wav")]

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_skips_llm_when_no_api_key(self, mock_llm, mock_tts, coordinator):
        """Without an API key, LLM should not be called and error emitted."""
        coordinator._api_key = None

        errors = []
        coordinator.error_occurred.connect(lambda msg: errors.append(msg))

        msg = {"query": "hello", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_llm.chat_stream.assert_not_called()
        assert len(errors) == 1
        assert "API key" in errors[0]

    @patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"})
    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_uses_env_var_fallback(self, mock_llm, mock_tts, coordinator):
        """When _api_key is None, fall back to GEMINI_API_KEY env var."""
        self._setup_streaming_mocks(mock_llm, mock_tts, "ok")

        coordinator._api_key = None
        msg = {"query": "hello", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_llm.chat_stream_raw.assert_called_once_with(
            "hello", context=None, repo_map=None, api_key="env-key"
        )


class TestThreadSafety:
    """Verify context lock protects shared state."""

    def test_context_lock_exists(self, coordinator):
        assert hasattr(coordinator, "_context_lock")
        assert isinstance(coordinator._context_lock, type(threading.Lock()))

    def test_enqueue_snapshots_context(self, coordinator):
        """Context should be captured at enqueue time, not read later."""
        coordinator.set_file_context("/a.py", "version1")
        coordinator._enqueue("query")
        # Change context after enqueue.
        coordinator.set_file_context("/b.py", "version2")

        msg = coordinator._queue.get_nowait()
        assert msg["context"] == "version1"

    def test_stop_joins_worker(self, coordinator):
        """stop() should set event AND join the worker thread."""
        with patch("harness.coordinator.code_llm"), \
             patch("harness.coordinator.tts_mod"):
            coordinator.start()
            assert coordinator._worker_thread is not None
            coordinator.stop()
            assert coordinator._stop_event.is_set()
            assert coordinator._worker_thread is None


class TestResponseSplitter:
    """Verify _process_message splits edits from prose (Phase 3a)."""

    @staticmethod
    def _wire(mock_llm, mock_tts, response, prose="", edits=None):
        """Helper to set up streaming mocks for response splitter tests."""
        mock_llm.chat_stream_raw.return_value = iter([response])
        mock_llm.extract_prose.return_value = prose
        mock_llm.parse_search_replace.return_value = edits or []

        def fake_splitter(chunks):
            for chunk in chunks:
                pass  # consume so _capturing_stream populates full_response_parts
            if prose:
                yield prose

        mock_llm.split_sentences_streaming.side_effect = fake_splitter

        def fake_speak(sentences):
            for s in sentences:
                yield (s, b"wav")

        mock_tts.speak_stream.side_effect = fake_speak

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_emits_edits_proposed_when_blocks_present(self, mock_llm, mock_tts, coordinator):
        llm_response = (
            "I fixed the bug.\n"
            "<<<<<<< SEARCH\n"
            "old line\n"
            "=======\n"
            "new line\n"
            ">>>>>>> REPLACE"
        )
        self._wire(
            mock_llm, mock_tts, llm_response,
            prose="I fixed the bug.",
            edits=[{"search": "old line", "replace": "new line"}],
        )

        received = []
        coordinator.edits_proposed.connect(lambda data: received.append(data))

        coordinator._api_key = "test-key"
        coordinator.set_file_context("/test.py", "old line\n")
        msg = {"query": "fix it", "context": "old line\n", "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 1
        assert received[0]["file_path"] == "/test.py"
        assert len(received[0]["edits"]) == 1

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_no_edits_proposed_for_prose_only(self, mock_llm, mock_tts, coordinator):
        self._wire(
            mock_llm, mock_tts, "Just an explanation.",
            prose="Just an explanation.",
        )

        received = []
        coordinator.edits_proposed.connect(lambda data: received.append(data))

        coordinator._api_key = "test-key"
        msg = {"query": "what is this?", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 0

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_edits_proposed_includes_preview(self, mock_llm, mock_tts, coordinator):
        """edits_proposed should include both original and modified content."""
        self._wire(
            mock_llm, mock_tts,
            "<<<<<<< SEARCH\nalpha\n=======\nbeta\n>>>>>>> REPLACE",
            edits=[{"search": "alpha", "replace": "beta"}],
        )

        received = []
        coordinator.edits_proposed.connect(lambda data: received.append(data))

        coordinator._api_key = "test-key"
        coordinator.set_file_context("/f.py", "alpha\ngamma\n")
        msg = {"query": "fix", "context": "alpha\ngamma\n", "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 1
        assert received[0]["original"] == "alpha\ngamma\n"
        assert "beta" in received[0]["modified"]

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_still_calls_tts_when_edits_and_prose(self, mock_llm, mock_tts, coordinator):
        """Even when edits exist, prose should still go to TTS."""
        response = (
            "Here's the fix.\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
        )
        self._wire(
            mock_llm, mock_tts, response,
            prose="Here's the fix.",
            edits=[{"search": "old", "replace": "new"}],
        )

        chunks_received = []
        coordinator.tts_chunk_ready.connect(lambda s, w: chunks_received.append((s, w)))

        coordinator._api_key = "test-key"
        coordinator.set_file_context("/f.py", "old\n")
        msg = {"query": "fix", "context": "old\n", "repo_map": None}
        with patch("harness.coordinator.threading.Thread", new=_SyncThread):
            coordinator._process_message(msg)

        assert len(chunks_received) == 1
        assert chunks_received[0][0] == "Here's the fix."

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_edit_apply_failure_emits_error(self, mock_llm, mock_tts, coordinator):
        """If edits can't be applied, emit an error instead of edits_proposed."""
        self._wire(
            mock_llm, mock_tts,
            "<<<<<<< SEARCH\nnonexistent\n=======\nnew\n>>>>>>> REPLACE",
            edits=[{"search": "nonexistent", "replace": "new"}],
        )

        edits_received = []
        errors_received = []
        coordinator.edits_proposed.connect(lambda data: edits_received.append(data))
        coordinator.error_occurred.connect(lambda msg: errors_received.append(msg))

        coordinator._api_key = "test-key"
        coordinator.set_file_context("/f.py", "totally different content\n")
        msg = {"query": "fix", "context": "totally different content\n", "repo_map": None}
        coordinator._process_message(msg)

        assert len(edits_received) == 0
        assert len(errors_received) == 1


class TestAcceptEdits:
    """Verify accept_edits writes file + git commits."""

    @patch("harness.coordinator.git_ops")
    def test_accept_edits_writes_file(self, mock_git, coordinator, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("old content\n", encoding="utf-8")
        mock_git.auto_commit.return_value = True

        result = coordinator.accept_edits(str(test_file), "new content\n")

        assert result is True
        assert test_file.read_text(encoding="utf-8") == "new content\n"

    @patch("harness.coordinator.git_ops")
    def test_accept_edits_calls_git_auto_commit(self, mock_git, coordinator, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("old\n", encoding="utf-8")
        mock_git.auto_commit.return_value = True

        coordinator.accept_edits(str(test_file), "new\n")

        mock_git.auto_commit.assert_called_once()

    @patch("harness.coordinator.git_ops")
    def test_accept_edits_emits_edits_applied(self, mock_git, coordinator, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("old\n", encoding="utf-8")
        mock_git.auto_commit.return_value = True

        received = []
        coordinator.edits_applied.connect(lambda path: received.append(path))

        coordinator.accept_edits(str(test_file), "new\n")

        assert len(received) == 1
        assert received[0] == str(test_file)

    @patch("harness.coordinator.git_ops")
    def test_reject_edits_does_not_write(self, mock_git, coordinator, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("original\n", encoding="utf-8")

        coordinator.reject_edits()

        assert test_file.read_text(encoding="utf-8") == "original\n"
        mock_git.auto_commit.assert_not_called()

    @patch("harness.coordinator.git_ops")
    def test_accept_returns_false_on_write_error(self, mock_git, coordinator):
        """Accept should return False and emit error for unwritable paths."""
        errors = []
        coordinator.error_occurred.connect(lambda msg: errors.append(msg))

        result = coordinator.accept_edits("/nonexistent/dir/file.py", "content")

        assert result is False
        assert len(errors) == 1
        assert "Failed to write" in errors[0]

    @patch("harness.coordinator.git_ops")
    def test_accept_emits_error_on_git_failure(self, mock_git, coordinator, tmp_path):
        """If git commit fails, file is still written but error emitted."""
        test_file = tmp_path / "test.py"
        test_file.write_text("old\n", encoding="utf-8")
        mock_git.auto_commit.return_value = False

        errors = []
        coordinator.error_occurred.connect(lambda msg: errors.append(msg))

        result = coordinator.accept_edits(str(test_file), "new\n")

        assert result is True  # file was written
        assert test_file.read_text(encoding="utf-8") == "new\n"
        assert len(errors) == 1
        assert "git commit failed" in errors[0]

    @patch("harness.coordinator.git_ops")
    def test_accept_rejects_path_outside_project(self, mock_git, coordinator, tmp_path):
        """Path outside project_root should be refused."""
        coordinator._project_root = str(tmp_path / "project")
        (tmp_path / "project").mkdir()
        outside_file = tmp_path / "outside.py"
        outside_file.write_text("hack\n", encoding="utf-8")

        errors = []
        coordinator.error_occurred.connect(lambda msg: errors.append(msg))

        result = coordinator.accept_edits(str(outside_file), "evil\n")

        assert result is False
        assert outside_file.read_text(encoding="utf-8") == "hack\n"  # unchanged
        assert len(errors) == 1
        assert "outside project root" in errors[0]

    @patch("harness.coordinator.git_ops")
    @patch("harness.coordinator._git")
    def test_accept_uses_repo_relative_path_for_git(self, mock_git_mod, mock_git, coordinator, tmp_path):
        """Git should receive a repo-relative path, not just basename."""
        project = tmp_path / "project"
        project.mkdir()
        sub = project / "harness"
        sub.mkdir()
        test_file = sub / "code_llm.py"
        test_file.write_text("old\n", encoding="utf-8")
        mock_git.auto_commit.return_value = True

        # Simulate _git.Repo finding the project root.
        mock_repo = MagicMock()
        mock_repo.working_tree_dir = str(project)
        mock_git_mod.Repo.return_value = mock_repo

        coordinator.accept_edits(str(test_file), "new\n")

        call_kwargs = mock_git.auto_commit.call_args
        staged_path = call_kwargs.kwargs.get("file_path") or call_kwargs[1].get("file_path")
        # Should NOT be just "code_llm.py" — must include subdirectory.
        assert staged_path == os.path.join("harness", "code_llm.py")


class TestPipelineLoopShutdown:
    """Verify pipeline loop exits cleanly on stop."""

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_pipeline_exits_on_sentinel(self, mock_llm, mock_tts, coordinator):
        coordinator._stop_event.clear()
        coordinator._queue.put(None)  # sentinel
        coordinator._pipeline_loop()  # should return quickly

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_pipeline_exits_on_stop_event(self, mock_llm, mock_tts, coordinator):
        coordinator._stop_event.set()
        coordinator._pipeline_loop()  # should return immediately


class TestTtsChunksSignal:
    """Verify Phase 4/5 — TTS chunks are emitted via signal, not played inline."""

    @staticmethod
    def _wire(mock_llm, mock_tts, response, prose=""):
        mock_llm.chat_stream_raw.return_value = iter([response])
        mock_llm.extract_prose.return_value = prose
        mock_llm.parse_search_replace.return_value = []

        def fake_splitter(chunks):
            for chunk in chunks:
                pass  # consume so _capturing_stream populates full_response_parts
            if prose:
                yield prose

        mock_llm.split_sentences_streaming.side_effect = fake_splitter

        def fake_speak(sentences):
            for s in sentences:
                yield (s, b"wav")

        mock_tts.speak_stream.side_effect = fake_speak

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_tts_chunks_ready_emitted(self, mock_llm, mock_tts, coordinator):
        """When prose exists, tts_chunks_ready should be emitted with chunks."""
        self._wire(mock_llm, mock_tts, "I fixed it.", prose="I fixed it.")

        received = []
        coordinator.tts_chunks_ready.connect(lambda chunks: received.append(chunks))

        coordinator._api_key = "test-key"

        msg = {"query": "fix", "context": None, "repo_map": None}
        with patch("harness.coordinator.threading.Thread", new=_SyncThread):
            coordinator._process_message(msg)

        assert len(received) == 1
        assert received[0] == [("I fixed it.", b"wav")]

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_no_tts_chunks_when_no_prose(self, mock_llm, mock_tts, coordinator):
        """No tts_chunks_ready signal when prose is empty."""
        self._wire(
            mock_llm, mock_tts,
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
        )

        received = []
        coordinator.tts_chunks_ready.connect(lambda chunks: received.append(chunks))

        coordinator._api_key = "test-key"
        msg = {"query": "fix", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 0

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_tts_does_not_play_inline(self, mock_llm, mock_tts, coordinator):
        """Coordinator should NOT call play_wav_bytes directly."""
        self._wire(mock_llm, mock_tts, "Done.", prose="Done.")

        coordinator._api_key = "test-key"

        msg = {"query": "fix", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_tts.play_wav_bytes.assert_not_called()

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_defers_tts_state_to_playback_owner(
        self, mock_llm, mock_tts, coordinator
    ):
        """Coordinator should hand off chunks without marking playback complete."""
        self._wire(mock_llm, mock_tts, "Done.", prose="Done.")

        states = []
        started = []
        finished = []
        coordinator.state_changed.connect(lambda state: states.append(state))
        coordinator.tts_started.connect(lambda: started.append(True))
        coordinator.tts_finished.connect(lambda: finished.append(True))

        coordinator._api_key = "test-key"

        msg = {"query": "fix", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert states == ["processing", "listening"]
        assert started == []
        assert finished == []


class TestTtsPlaybackLifecycle:
    """Verify explicit playback lifecycle methods drive speaking/listening state."""

    def test_begin_tts_playback_emits_started_and_speaking(self, coordinator):
        states = []
        started = []
        coordinator.state_changed.connect(lambda state: states.append(state))
        coordinator.tts_started.connect(lambda: started.append(True))

        coordinator.begin_tts_playback()

        assert states == ["speaking"]
        assert started == [True]

    def test_finish_tts_playback_emits_finished_and_listening(self, coordinator):
        states = []
        finished = []
        coordinator.state_changed.connect(lambda state: states.append(state))
        coordinator.tts_finished.connect(lambda: finished.append(True))

        coordinator.begin_tts_playback()
        coordinator.finish_tts_playback()

        assert states[-1] == "listening"
        assert finished == [True]

    def test_finish_tts_playback_is_noop_when_inactive(self, coordinator):
        states = []
        finished = []
        coordinator.state_changed.connect(lambda state: states.append(state))
        coordinator.tts_finished.connect(lambda: finished.append(True))

        coordinator.finish_tts_playback()

        assert states == []
        assert finished == []


class TestStreamingPipeline:
    """Phase 5 — verify _process_message uses streaming LLM → TTS pipeline."""

    @staticmethod
    def _wire(mock_llm, mock_tts, chunks, sentences=None, prose="", edits=None):
        """Wire streaming mocks so generators consume their inputs properly."""
        mock_llm.chat_stream_raw.return_value = iter(chunks)
        mock_llm.extract_prose.return_value = prose
        mock_llm.parse_search_replace.return_value = edits or []

        sentence_list = sentences if sentences is not None else ([prose] if prose else [])

        def fake_splitter(input_chunks):
            for chunk in input_chunks:
                pass  # consume so _capturing_stream populates full_response_parts
            yield from sentence_list

        mock_llm.split_sentences_streaming.side_effect = fake_splitter

        def fake_speak(input_sentences):
            for s in input_sentences:
                yield (s, b"wav")

        mock_tts.speak_stream.side_effect = fake_speak

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_uses_chat_stream_raw_instead_of_chat(self, mock_llm, mock_tts, coordinator):
        """_process_message should call chat_stream_raw(), not chat()."""
        self._wire(mock_llm, mock_tts, ["Hello."], sentences=["Hello."])

        coordinator._api_key = "test-key"
        msg = {"query": "hi", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_llm.chat_stream_raw.assert_called_once()
        mock_llm.chat.assert_not_called()

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_emits_tts_chunk_ready_per_sentence(self, mock_llm, mock_tts, coordinator):
        """Each sentence should trigger a separate tts_chunk_ready signal."""
        self._wire(
            mock_llm, mock_tts,
            ["First. ", "Second."],
            sentences=["First.", "Second."],
            prose="First. Second.",
        )

        received = []
        coordinator.tts_chunk_ready.connect(lambda s, w: received.append((s, w)))

        coordinator._api_key = "test-key"
        msg = {"query": "hello", "context": None, "repo_map": None}
        with patch("harness.coordinator.threading.Thread", new=_SyncThread):
            coordinator._process_message(msg)

        assert len(received) == 2
        assert received[0] == ("First.", b"wav")
        assert received[1] == ("Second.", b"wav")

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_accumulates_full_response(self, mock_llm, mock_tts, coordinator):
        """llm_response_ready should contain the full accumulated response."""
        self._wire(
            mock_llm, mock_tts,
            ["Hello ", "world."],
            sentences=["Hello world."],
            prose="Hello world.",
        )

        responses = []
        coordinator.llm_response_ready.connect(lambda r: responses.append(r))

        coordinator._api_key = "test-key"
        msg = {"query": "hi", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert len(responses) == 1
        assert responses[0] == "Hello world."

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_parses_edits_from_full_response(self, mock_llm, mock_tts, coordinator):
        """Edits should be parsed from the full accumulated response."""
        full = "Fix.\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
        self._wire(
            mock_llm, mock_tts,
            [full],
            sentences=["Fix."],
            prose="Fix.",
            edits=[{"search": "old", "replace": "new"}],
        )

        edits_received = []
        coordinator.edits_proposed.connect(lambda d: edits_received.append(d))

        coordinator._api_key = "test-key"
        coordinator.set_file_context("/f.py", "old\n")
        msg = {"query": "fix", "context": "old\n", "repo_map": None}
        coordinator._process_message(msg)

        mock_llm.parse_search_replace.assert_called_once_with(full)
        assert len(edits_received) == 1

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_no_tts_when_stream_yields_nothing(self, mock_llm, mock_tts, coordinator):
        """When speak_stream yields nothing, no tts_chunk_ready emitted."""
        self._wire(
            mock_llm, mock_tts,
            ["<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"],
            sentences=[],
        )

        received = []
        coordinator.tts_chunk_ready.connect(lambda s, w: received.append((s, w)))

        coordinator._api_key = "test-key"
        msg = {"query": "fix", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 0
