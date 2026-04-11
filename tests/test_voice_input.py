"""Tests for harness/voice_input.py — VoiceInput adapter API surface."""

import logging
from unittest.mock import patch, MagicMock

from harness.voice_input import VoiceInput


class TestVoiceInputAPI:
    """Verify the thin adapter exposes the correct public interface."""

    def test_on_text_registers_callback(self):
        vi = VoiceInput()
        cb = lambda text: None
        vi.on_text(cb)
        assert vi._callback is cb

    def test_initial_state(self):
        vi = VoiceInput()
        assert vi._running is False
        assert vi._recorder is None
        assert vi._callback is None

    def test_default_audio_config(self):
        vi = VoiceInput()
        assert vi.input_device_index is None
        assert vi.wake_word_enabled is False

    def test_on_error_registers_callback(self):
        vi = VoiceInput()
        cb = lambda message: None
        vi.on_error(cb)
        assert vi._error_callback is cb

    def test_on_recording_state_registers_callback(self):
        vi = VoiceInput()
        cb = lambda active: None
        vi.on_recording_state(cb)
        assert vi._recording_state_callback is cb

    def test_on_status_registers_callback(self):
        vi = VoiceInput()
        cb = lambda status: None
        vi.on_status(cb)
        assert vi._status_callback is cb

    def test_emit_status_calls_callback(self):
        vi = VoiceInput()
        received = []
        vi.on_status(lambda s: received.append(s))
        vi._emit_status("loading")
        assert received == ["loading"]

    def test_emit_status_safe_without_callback(self):
        vi = VoiceInput()
        vi._emit_status("loading")  # should not raise

    def test_stop_when_not_started(self):
        """stop() should be safe to call even if never started."""
        vi = VoiceInput()
        vi.stop()  # should not raise
        assert vi._running is False

    def test_pause_when_no_recorder(self):
        """pause() should be safe when recorder is None."""
        vi = VoiceInput()
        vi.pause()  # should not raise

    def test_resume_when_no_recorder(self):
        """resume() should be safe when recorder is None."""
        vi = VoiceInput()
        vi.resume()  # should not raise

    def test_set_input_device_updates_config(self):
        vi = VoiceInput()
        vi.set_input_device(4)
        assert vi.input_device_index == 4

    def test_set_wake_word_enabled_updates_config(self):
        vi = VoiceInput()
        vi.set_wake_word_enabled(True)
        assert vi.wake_word_enabled is True

    def test_set_input_device_requests_reconfigure(self):
        vi = VoiceInput()
        vi._running = True
        recorder = MagicMock()
        vi._recorder = recorder

        vi.set_input_device(8)

        recorder.stop.assert_called_once()
        assert vi._reconfigure_requested is True

    def test_create_recorder_uses_input_device_and_wake_word(self):
        captured = {}

        class FakeRecorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        vi = VoiceInput()
        vi.set_input_device(6)
        vi.set_wake_word_enabled(True)
        vi._create_recorder(FakeRecorder)

        assert captured["input_device_index"] == 6
        assert captured["wake_words"] == "hey_jarvis"

    def test_create_recorder_omits_wake_words_when_disabled(self):
        captured = {}

        class FakeRecorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        vi = VoiceInput()
        vi._create_recorder(FakeRecorder)

        assert "wake_words" not in captured

    def test_start_sets_running_flag(self):
        """start() should set _running=True and spawn a thread."""
        vi = VoiceInput()

        # Patch _listen_loop so it doesn't actually import RealtimeSTT.
        with patch.object(vi, "_listen_loop"):
            vi.start()
            assert vi._running is True
            vi.stop()

    def test_start_idempotent(self):
        """Calling start() twice should not spawn a second thread."""
        vi = VoiceInput()
        with patch.object(vi, "_listen_loop"):
            vi.start()
            thread1 = vi._thread
            vi.start()
            thread2 = vi._thread
            assert thread1 is thread2
            vi.stop()

    def test_stop_logs_recorder_error(self, caplog):
        """stop() should log warnings when recorder.stop() throws."""
        vi = VoiceInput()
        vi._running = True
        vi._recorder = MagicMock()
        vi._recorder.stop.side_effect = RuntimeError("device lost")

        with caplog.at_level(logging.WARNING, logger="harness.voice_input"):
            vi.stop()

        assert any("Error stopping recorder" in r.message for r in caplog.records)
        assert vi._recorder is None

    def test_pause_logs_recorder_error(self, caplog):
        """pause() should log warnings when recorder.stop() throws."""
        vi = VoiceInput()
        vi._recorder = MagicMock()
        vi._recorder.stop.side_effect = RuntimeError("device lost")

        with caplog.at_level(logging.WARNING, logger="harness.voice_input"):
            vi.pause()

        assert any("Error pausing recorder" in r.message for r in caplog.records)

    def test_resume_logs_recorder_error(self, caplog):
        """resume() should log warnings when recorder.start() throws."""
        vi = VoiceInput()
        vi._running = True
        vi._recorder = MagicMock()
        vi._recorder.start.side_effect = RuntimeError("device lost")

        with caplog.at_level(logging.WARNING, logger="harness.voice_input"):
            vi.resume()

        assert any("Error resuming recorder" in r.message for r in caplog.records)
