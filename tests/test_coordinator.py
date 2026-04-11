"""Tests for harness/coordinator.py — message format, enqueue, lifecycle."""

import os
import queue
import threading
from unittest.mock import patch, MagicMock

import pytest

from harness.coordinator import Coordinator


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

    def test_set_wake_word_enabled_calls_voice_input(self, coordinator):
        coordinator.set_wake_word_enabled(True)
        coordinator._voice.set_wake_word_enabled.assert_called_once_with(True)

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
    """Verify _process_message calls LLM and TTS in order."""

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_calls_llm(self, mock_llm, mock_tts, coordinator):
        mock_llm.chat.return_value = "response text"
        mock_llm.extract_prose.return_value = ""

        coordinator._api_key = "test-key"
        msg = {"query": "hello", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_llm.chat.assert_called_once_with(
            "hello", context=None, repo_map=None, api_key="test-key"
        )

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_skips_tts_when_no_prose(self, mock_llm, mock_tts, coordinator):
        mock_llm.chat.return_value = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
        mock_llm.extract_prose.return_value = ""

        coordinator._api_key = "test-key"
        msg = {"query": "fix it", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_tts.speak.assert_not_called()

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_calls_tts_when_prose_exists(self, mock_llm, mock_tts, coordinator):
        mock_llm.chat.return_value = "I fixed the bug."
        mock_llm.extract_prose.return_value = "I fixed the bug."
        mock_tts.speak.return_value = [("I fixed the bug.", b"wav")]

        received = []
        coordinator.tts_chunks_ready.connect(lambda chunks: received.append(chunks))

        coordinator._api_key = "test-key"
        msg = {"query": "fix it", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_tts.speak.assert_called_once_with("I fixed the bug.")
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

        mock_llm.chat.assert_not_called()
        assert len(errors) == 1
        assert "API key" in errors[0]

    @patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"})
    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_process_message_uses_env_var_fallback(self, mock_llm, mock_tts, coordinator):
        """When _api_key is None, fall back to GEMINI_API_KEY env var."""
        mock_llm.chat.return_value = "ok"
        mock_llm.extract_prose.return_value = ""

        coordinator._api_key = None
        msg = {"query": "hello", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        mock_llm.chat.assert_called_once_with(
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
        mock_llm.chat.return_value = llm_response
        mock_llm.extract_prose.return_value = "I fixed the bug."
        mock_llm.parse_search_replace.return_value = [
            {"search": "old line", "replace": "new line"}
        ]
        mock_tts.speak.return_value = [("I fixed the bug.", b"wav")]

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
        mock_llm.chat.return_value = "Just an explanation."
        mock_llm.extract_prose.return_value = "Just an explanation."
        mock_llm.parse_search_replace.return_value = []
        mock_tts.speak.return_value = [("Just an explanation.", b"wav")]

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
        mock_llm.chat.return_value = "<<<<<<< SEARCH\nalpha\n=======\nbeta\n>>>>>>> REPLACE"
        mock_llm.extract_prose.return_value = ""
        mock_llm.parse_search_replace.return_value = [
            {"search": "alpha", "replace": "beta"}
        ]

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
        mock_llm.chat.return_value = (
            "Here's the fix.\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
        )
        mock_llm.extract_prose.return_value = "Here's the fix."
        mock_llm.parse_search_replace.return_value = [
            {"search": "old", "replace": "new"}
        ]
        mock_tts.speak.return_value = [("Here's the fix.", b"wav")]

        coordinator._api_key = "test-key"
        coordinator.set_file_context("/f.py", "old\n")
        msg = {"query": "fix", "context": "old\n", "repo_map": None}
        coordinator._process_message(msg)

        mock_tts.speak.assert_called_once_with("Here's the fix.")

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_edit_apply_failure_emits_error(self, mock_llm, mock_tts, coordinator):
        """If edits can't be applied, emit an error instead of edits_proposed."""
        mock_llm.chat.return_value = "<<<<<<< SEARCH\nnonexistent\n=======\nnew\n>>>>>>> REPLACE"
        mock_llm.extract_prose.return_value = ""
        mock_llm.parse_search_replace.return_value = [
            {"search": "nonexistent", "replace": "new"}
        ]

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
    """Verify Phase 4 — TTS chunks are emitted via signal, not played inline."""

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_tts_chunks_ready_emitted(self, mock_llm, mock_tts, coordinator):
        """When prose exists, tts_chunks_ready should be emitted with chunks."""
        mock_llm.chat.return_value = "I fixed it."
        mock_llm.extract_prose.return_value = "I fixed it."
        mock_llm.parse_search_replace.return_value = []
        mock_tts.speak.return_value = [("I fixed it.", b"wav")]

        received = []
        coordinator.tts_chunks_ready.connect(lambda chunks: received.append(chunks))

        coordinator._api_key = "test-key"

        msg = {"query": "fix", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 1
        assert received[0] == [("I fixed it.", b"wav")]

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_no_tts_chunks_when_no_prose(self, mock_llm, mock_tts, coordinator):
        """No tts_chunks_ready signal when prose is empty."""
        mock_llm.chat.return_value = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
        mock_llm.extract_prose.return_value = ""
        mock_llm.parse_search_replace.return_value = [
            {"search": "old", "replace": "new"}
        ]

        received = []
        coordinator.tts_chunks_ready.connect(lambda chunks: received.append(chunks))

        coordinator._api_key = "test-key"
        msg = {"query": "fix", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert len(received) == 0

    @patch("harness.coordinator.tts_mod")
    @patch("harness.coordinator.code_llm")
    def test_tts_does_not_play_inline(self, mock_llm, mock_tts, coordinator):
        """Phase 4 — coordinator should NOT call play_wav_bytes directly."""
        mock_llm.chat.return_value = "Done."
        mock_llm.extract_prose.return_value = "Done."
        mock_llm.parse_search_replace.return_value = []
        mock_tts.speak.return_value = [("Done.", b"wav")]

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
        mock_llm.chat.return_value = "Done."
        mock_llm.extract_prose.return_value = "Done."
        mock_llm.parse_search_replace.return_value = []
        mock_tts.speak.return_value = [("Done.", b"wav")]

        states = []
        started = []
        finished = []
        coordinator.state_changed.connect(lambda state: states.append(state))
        coordinator.tts_started.connect(lambda: started.append(True))
        coordinator.tts_finished.connect(lambda: finished.append(True))

        coordinator._api_key = "test-key"

        msg = {"query": "fix", "context": None, "repo_map": None}
        coordinator._process_message(msg)

        assert states == ["processing"]
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
