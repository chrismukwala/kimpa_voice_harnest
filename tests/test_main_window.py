"""Tests for ui/main_window.py — startup wiring + editor-coordinator sync."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from ui.main_window import MainWindow, _is_binary_file, _MAX_FILE_SIZE


class _FakeAudioSettings:
    def __init__(self, input_device=None, output_device=None, wake_word=False, api_key="test-key"):
        self._input_device = input_device
        self._output_device = output_device
        self._wake_word_enabled = wake_word
        self._api_key = api_key

    def input_device(self):
        return self._input_device

    def set_input_device(self, device):
        self._input_device = device

    def output_device(self):
        return self._output_device

    def set_output_device(self, device):
        self._output_device = device

    def wake_word_enabled(self):
        return self._wake_word_enabled

    def set_wake_word_enabled(self, enabled):
        self._wake_word_enabled = enabled

    def api_key(self):
        return self._api_key

    def set_api_key(self, key):
        self._api_key = key


@pytest.fixture
def coordinator():
    """Mocked Coordinator with full signal surface."""
    with patch("harness.coordinator.VoiceInput"):
        from harness.coordinator import Coordinator
        coord = Coordinator()
        yield coord
        coord._stop_event.set()


@pytest.mark.ui
class TestMainWindowStartup:
    """Verify MainWindow wiring at construction time."""

    def test_window_creates_all_panels(self, qapp, coordinator):
        win = MainWindow(coordinator)
        assert win._file_tree is not None
        assert win._editor is not None
        assert win._ai_panel is not None

    def test_set_root_path_sets_tree_root(self, qapp, coordinator):
        win = MainWindow(coordinator)
        with tempfile.TemporaryDirectory() as tmpdir:
            win.set_root_path(tmpdir)
            model_root = win._fs_model.rootPath()
            assert os.path.normpath(model_root) == os.path.normpath(tmpdir)

    def test_coordinator_signals_connected(self, qapp, coordinator):
        """state_changed signal should reach ai_panel.set_state."""
        win = MainWindow(coordinator)
        coordinator.state_changed.emit("processing")
        assert win._ai_panel._status.text() == "Processing"

    @patch("ui.main_window.audio_devices.get_default_output", return_value=None)
    @patch("ui.main_window.audio_devices.get_default_input", return_value=None)
    @patch("ui.main_window.audio_devices.list_output_devices", return_value=[])
    @patch("ui.main_window.audio_devices.list_input_devices", return_value=[])
    def test_audio_settings_applied_on_startup(
        self,
        _mock_inputs,
        _mock_outputs,
        _mock_default_input,
        _mock_default_output,
        qapp,
        coordinator,
    ):
        settings = _FakeAudioSettings(input_device=2, output_device=3, wake_word=True)

        with patch.object(coordinator, "set_input_device") as mock_input, patch.object(
            coordinator, "set_wake_word_enabled"
        ) as mock_wake:
            win = MainWindow(coordinator, audio_settings=settings)

        mock_input.assert_called_once_with(2)
        mock_wake.assert_called_once_with(True)
        assert win._tts_nav.output_device == 3


@pytest.mark.ui
class TestEditorCoordinatorSync:
    """Verify editor changes propagate to coordinator file context."""

    def test_file_open_sets_coordinator_context(self, qapp, coordinator):
        win = MainWindow(coordinator)
        win._editor.set_file("/test.py", "x = 1")
        win._sync_editor_context()

        assert coordinator._current_file_path == "/test.py"
        assert coordinator._current_file_content == "x = 1"

    def test_no_file_does_not_set_context(self, qapp, coordinator):
        """With no file open, context should not be set."""
        win = MainWindow(coordinator)
        win._sync_editor_context()
        # path is "No file open" so context should not be set.
        assert coordinator._current_file_content is None

    def test_manual_query_syncs_then_submits(self, qapp, coordinator):
        win = MainWindow(coordinator)
        win._editor.set_file("/a.py", "hello")
        win._on_manual_query("fix it")

        msg = coordinator._queue.get_nowait()
        assert msg["query"] == "fix it"
        assert msg["context"] == "hello"


@pytest.mark.ui
class TestFileTreeEdgeCases:
    """Verify binary file rejection and size guard."""

    def test_is_binary_file_detects_null_bytes(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02binary data")
            path = f.name
        try:
            assert _is_binary_file(path) is True
        finally:
            os.unlink(path)

    def test_is_binary_file_allows_text(self):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("print('hello')\n")
            path = f.name
        try:
            assert _is_binary_file(path) is False
        finally:
            os.unlink(path)

    def test_load_file_rejects_binary(self, qapp, coordinator):
        win = MainWindow(coordinator)
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02binary data")
            path = f.name
        try:
            win._load_file_by_path(path)
            assert win._editor.path == "No file open"
        finally:
            os.unlink(path)

    def test_load_file_rejects_oversized(self, qapp, coordinator):
        win = MainWindow(coordinator)
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"x" * (_MAX_FILE_SIZE + 1))
            path = f.name
        try:
            win._load_file_by_path(path)
            assert win._editor.path == "No file open"
        finally:
            os.unlink(path)

    def test_load_file_accepts_normal_text(self, qapp, coordinator):
        win = MainWindow(coordinator)
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 42\n")
            path = f.name
        try:
            win._load_file_by_path(path)
            assert win._editor.get_content() == "x = 42\n"
        finally:
            os.unlink(path)

    def test_load_binary_shows_statusbar(self, qapp, coordinator):
        """Binary file rejection should show a status bar message."""
        win = MainWindow(coordinator)
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02binary data")
            path = f.name
        try:
            win._load_file_by_path(path)
            msg = win.statusBar().currentMessage()
            assert "Binary file skipped" in msg
        finally:
            os.unlink(path)

    def test_load_oversized_shows_statusbar(self, qapp, coordinator):
        """Oversized file rejection should show a status bar message."""
        win = MainWindow(coordinator)
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"x" * (_MAX_FILE_SIZE + 1))
            path = f.name
        try:
            win._load_file_by_path(path)
            msg = win.statusBar().currentMessage()
            assert "File too large" in msg
        finally:
            os.unlink(path)

    def test_load_missing_file_shows_statusbar(self, qapp, coordinator):
        """Missing file should show a status bar message."""
        win = MainWindow(coordinator)
        win._load_file_by_path("/nonexistent/path/file.py")
        msg = win.statusBar().currentMessage()
        assert "Cannot read" in msg


@pytest.mark.ui
class TestMainWindowCloseEvent:
    """Verify MainWindow cleanup on close."""

    def test_close_shuts_down_editor(self, qapp, coordinator):
        """closeEvent should call editor.shutdown()."""
        win = MainWindow(coordinator)
        assert win._editor._server is not None
        win.close()
        assert win._editor._server is None


@pytest.mark.ui
class TestDiffFlow:
    """Verify diff accept/reject UI flow (Phase 3a)."""

    def test_edits_proposed_shows_diff_panel(self, qapp, coordinator):
        """When edits_proposed fires, the diff panel should become visible."""
        win = MainWindow(coordinator)
        proposal = {
            "file_path": "/test.py",
            "edits": [{"search": "old", "replace": "new"}],
            "original": "old\n",
            "modified": "new\n",
        }
        coordinator.edits_proposed.emit(proposal)

        assert win._diff_panel is not None
        assert win._diff_panel.isVisible()

    def test_accept_button_calls_coordinator_accept(self, qapp, coordinator):
        """Clicking accept should write the modified content."""
        win = MainWindow(coordinator)
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("old\n")
            path = f.name

        try:
            proposal = {
                "file_path": path,
                "edits": [{"search": "old", "replace": "new"}],
                "original": "old\n",
                "modified": "new\n",
            }
            coordinator.edits_proposed.emit(proposal)

            with patch.object(coordinator, "accept_edits") as mock_accept:
                win._on_accept_edits()
                mock_accept.assert_called_once_with(path, "new\n")
        finally:
            os.unlink(path)

    def test_reject_button_hides_diff_panel(self, qapp, coordinator):
        """Clicking reject should hide the diff panel."""
        win = MainWindow(coordinator)
        proposal = {
            "file_path": "/test.py",
            "edits": [{"search": "old", "replace": "new"}],
            "original": "old\n",
            "modified": "new\n",
        }
        coordinator.edits_proposed.emit(proposal)
        assert win._diff_panel.isVisible()

        win._on_reject_edits()
        assert not win._diff_panel.isVisible()

    def test_accept_reloads_editor(self, qapp, coordinator):
        """After accepting, the editor should show the new content."""
        win = MainWindow(coordinator)
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("old\n")
            path = f.name

        try:
            win._editor.set_file(path, "old\n")
            proposal = {
                "file_path": path,
                "edits": [{"search": "old", "replace": "new"}],
                "original": "old\n",
                "modified": "new\n",
            }
            coordinator.edits_proposed.emit(proposal)

            with patch.object(coordinator, "accept_edits"):
                win._on_accept_edits()

            assert win._editor.get_content() == "new\n"
        finally:
            os.unlink(path)

    def test_edits_applied_updates_statusbar(self, qapp, coordinator):
        """edits_applied signal should show a status bar confirmation."""
        win = MainWindow(coordinator)
        coordinator.edits_applied.emit("/test.py")
        msg = win.statusBar().currentMessage()
        assert "test.py" in msg

    def test_multiple_proposals_do_not_accumulate_handlers(self, qapp, coordinator):
        """Rapid proposals should not stack button handlers."""
        win = MainWindow(coordinator)
        proposal1 = {
            "file_path": "/test.py",
            "edits": [{"search": "old", "replace": "new"}],
            "original": "old\n",
            "modified": "new\n",
        }
        proposal2 = {
            "file_path": "/test.py",
            "edits": [{"search": "new", "replace": "newest"}],
            "original": "new\n",
            "modified": "newest\n",
        }
        coordinator.edits_proposed.emit(proposal1)
        coordinator.edits_proposed.emit(proposal2)

        # After two proposals, accept should only fire once.
        with patch.object(coordinator, "accept_edits", return_value=True) as mock:
            win._on_accept_edits()
            assert mock.call_count == 1
            # Should accept the latest proposal.
            mock.assert_called_once_with("/test.py", "newest\n")

    def test_accept_rejects_stale_proposal_on_file_switch(self, qapp, coordinator):
        """If user switches files, accepting should reject the stale proposal."""
        win = MainWindow(coordinator)
        proposal = {
            "file_path": "/original.py",
            "edits": [{"search": "old", "replace": "new"}],
            "original": "old\n",
            "modified": "new\n",
        }
        coordinator.edits_proposed.emit(proposal)
        # User switches to a different file.
        win._editor.set_file("/different.py", "other content")

        with patch.object(coordinator, "accept_edits") as mock:
            win._on_accept_edits()
            mock.assert_not_called()

        assert win._pending_proposal is None
        assert not win._diff_panel.isVisible()

    def test_accept_does_not_reload_editor_on_failure(self, qapp, coordinator):
        """When accept_edits returns False, editor should not reload."""
        win = MainWindow(coordinator)
        win._editor.set_file("/test.py", "old\n")
        proposal = {
            "file_path": "/test.py",
            "edits": [{"search": "old", "replace": "new"}],
            "original": "old\n",
            "modified": "new\n",
        }
        coordinator.edits_proposed.emit(proposal)

        with patch.object(coordinator, "accept_edits", return_value=False):
            win._on_accept_edits()

        # Editor should still show old content.
        assert win._editor.get_content() == "old\n"


@pytest.mark.ui
class TestTtsNavWiring:
    """Verify MainWindow wires TtsNavigator ↔ AiPanel ↔ Coordinator."""

    def test_main_window_has_tts_navigator(self, qapp, coordinator):
        win = MainWindow(coordinator)
        assert hasattr(win, "_tts_nav")

    def test_tts_chunks_ready_loads_navigator(self, qapp, coordinator):
        """tts_chunks_ready signal should load chunks into the navigator."""
        win = MainWindow(coordinator)
        chunks = [("Hello.", b"wav1"), ("World.", b"wav2")]
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)
        assert win._tts_nav.chunk_count == 2
        assert win._tts_nav.current_index == 0

    def test_tts_chunks_ready_autoplays_and_sets_speaking(self, qapp, coordinator):
        """Incoming chunks should autoplay and move the UI to speaking state."""
        win = MainWindow(coordinator)
        chunks = [("Hello.", b"wav1")]

        with patch.object(win._tts_nav, "play_current") as mock_play:
            coordinator.tts_chunks_ready.emit(chunks)

        mock_play.assert_called_once()
        assert win._ai_panel._status.text() == "Speaking"

    def test_playback_error_surfaces_in_ai_panel_log(self, qapp, coordinator):
        win = MainWindow(coordinator)

        win._tts_nav.playback_error.emit("device failure")

        log_text = win._ai_panel._log.toPlainText()
        assert "TTS playback error" in log_text
        assert "device failure" in log_text

    @patch("ui.main_window.audio_devices.get_default_output", return_value=None)
    @patch("ui.main_window.audio_devices.get_default_input", return_value=None)
    @patch("ui.main_window.audio_devices.list_output_devices", return_value=[])
    @patch("ui.main_window.audio_devices.list_input_devices", return_value=[])
    def test_input_device_change_updates_coordinator_and_settings(
        self,
        _mock_inputs,
        _mock_outputs,
        _mock_default_input,
        _mock_default_output,
        qapp,
        coordinator,
    ):
        settings = _FakeAudioSettings()
        win = MainWindow(coordinator, audio_settings=settings)
        win._ai_panel.set_audio_devices(
            [{"index": 7, "name": "Mic", "channels": 1}],
            [],
            selected_input=None,
            selected_output=None,
        )

        with patch.object(coordinator, "set_input_device") as mock_input:
            win._ai_panel._input_device_combo.setCurrentIndex(1)

        mock_input.assert_called_once_with(7)
        assert settings.input_device() == 7

    @patch("ui.main_window.audio_devices.get_default_output", return_value=None)
    @patch("ui.main_window.audio_devices.get_default_input", return_value=None)
    @patch("ui.main_window.audio_devices.list_output_devices", return_value=[])
    @patch("ui.main_window.audio_devices.list_input_devices", return_value=[])
    def test_output_device_change_updates_navigator_and_settings(
        self,
        _mock_inputs,
        _mock_outputs,
        _mock_default_input,
        _mock_default_output,
        qapp,
        coordinator,
    ):
        settings = _FakeAudioSettings()
        win = MainWindow(coordinator, audio_settings=settings)
        win._ai_panel.set_audio_devices(
            [],
            [{"index": 9, "name": "Speaker", "channels": 2}],
            selected_input=None,
            selected_output=None,
        )

        win._ai_panel._output_device_combo.setCurrentIndex(1)

        assert win._tts_nav.output_device == 9
        assert settings.output_device() == 9

    @patch("ui.main_window.audio_devices.get_default_output", return_value=None)
    @patch("ui.main_window.audio_devices.get_default_input", return_value=None)
    @patch("ui.main_window.audio_devices.list_output_devices", return_value=[])
    @patch("ui.main_window.audio_devices.list_input_devices", return_value=[])
    def test_wake_word_toggle_updates_coordinator_and_settings(
        self,
        _mock_inputs,
        _mock_outputs,
        _mock_default_input,
        _mock_default_output,
        qapp,
        coordinator,
    ):
        settings = _FakeAudioSettings()
        win = MainWindow(coordinator, audio_settings=settings)

        with patch.object(coordinator, "set_wake_word_enabled") as mock_wake:
            win._ai_panel._wake_word_check.setChecked(True)

        mock_wake.assert_called_once_with(True)
        assert settings.wake_word_enabled() is True

    def test_recording_active_signal_updates_panel(self, qapp, coordinator):
        win = MainWindow(coordinator)
        coordinator.state_changed.emit("listening")

        coordinator.recording_active_changed.emit(True)

        assert win._ai_panel._flash_timer.isActive()

    def test_word_highlight_signal_updates_panel_html(self, qapp, coordinator):
        win = MainWindow(coordinator)
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit([("hello brave world", b"wav")])

        win._tts_nav.word_highlight.emit(1, 3)

        assert "background:#ce9178" in win._ai_panel._tts_sentence.text()

    def test_tts_chunks_ready_enables_controls(self, qapp, coordinator):
        """AI panel TTS controls should enable when chunks arrive."""
        win = MainWindow(coordinator)
        assert not win._ai_panel._play_btn.isEnabled()
        chunks = [("Hi.", b"wav1")]
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)
        assert win._ai_panel._play_btn.isEnabled()
        assert win._ai_panel._stop_btn.isEnabled()

    def test_chunk_changed_updates_ai_panel(self, qapp, coordinator):
        """chunk_changed from navigator should update AI panel info."""
        win = MainWindow(coordinator)
        chunks = [("First.", b"wav1"), ("Second.", b"wav2")]
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)
        # After load, chunk 0 should be displayed.
        assert "1 / 2" in win._ai_panel._chunk_label.text()
        assert "First." in win._ai_panel._tts_sentence.text()

    def test_keyboard_right_arrow_navigates_next(self, qapp, coordinator):
        """Right arrow handler should advance TTS navigator."""
        win = MainWindow(coordinator)
        win.show()
        chunks = [("A.", b"w1"), ("B.", b"w2"), ("C.", b"w3")]
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)

        # Call handler directly — QTest.keyPress doesn't trigger
        # QShortcut(ApplicationShortcut) reliably in headless tests.
        win._on_tts_right()
        assert win._tts_nav.current_index == 1

    def test_keyboard_left_arrow_navigates_prev(self, qapp, coordinator):
        """Left arrow key should go back in TTS navigator."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        win = MainWindow(coordinator)
        win.show()
        chunks = [("A.", b"w1"), ("B.", b"w2")]
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)

        QTest.keyPress(win, Qt.Key.Key_Right)
        QTest.keyPress(win, Qt.Key.Key_Left)
        assert win._tts_nav.current_index == 0

    @patch("harness.tts_navigator.sd")
    @patch("harness.tts_navigator.sf")
    def test_space_toggles_play(self, mock_sf, mock_sd, qapp, coordinator):
        """Space handler should play/stop TTS."""
        import threading

        gate = threading.Event()
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)
        mock_sd.wait.side_effect = lambda: gate.wait()

        win = MainWindow(coordinator)
        win.show()
        chunks = [("A.", b"w1")]
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)

        # Call handler directly — QTest.keyPress doesn't trigger
        # QShortcut(ApplicationShortcut) reliably in headless tests.
        win._on_tts_space()
        assert win._tts_nav.is_playing is True
        gate.set()

    def test_escape_stops_playback(self, qapp, coordinator):
        """Escape handler should stop TTS playback."""
        win = MainWindow(coordinator)
        win.show()
        chunks = [("A.", b"w1")]
        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)
        # Simulate playing state without actual audio.
        win._tts_nav._is_playing = True

        # Call handler directly — QTest.keyPress doesn't trigger
        # QShortcut(ApplicationShortcut) reliably in headless tests.
        win._on_tts_escape()
        assert win._tts_nav.is_playing is False

    def test_playback_finished_returns_to_listening_without_disabling_controls(
        self, qapp, coordinator
    ):
        """Completion should restore listening state but keep replay controls enabled."""
        win = MainWindow(coordinator)
        chunks = [("A.", b"w1")]

        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)

        win._on_tts_playback_finished()

        assert win._ai_panel._status.text() == "Listening"
        assert win._ai_panel._play_btn.isEnabled()

    def test_stop_request_returns_to_listening(self, qapp, coordinator):
        """Explicit stop should stop playback and restore listening state."""
        win = MainWindow(coordinator)
        chunks = [("A.", b"w1")]

        with patch.object(win._tts_nav, "play_current"):
            coordinator.tts_chunks_ready.emit(chunks)

        win._tts_nav._is_playing = True
        with patch.object(win._tts_nav, "stop") as mock_stop:
            win._on_tts_stop_requested()

        mock_stop.assert_called_once()
        assert win._ai_panel._status.text() == "Listening"
