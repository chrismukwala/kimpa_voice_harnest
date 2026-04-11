"""Tests for harness/tts_navigator.py — TTS sentence navigation + playback."""

import pytest
import numpy as np
import io
import wave
from unittest.mock import patch, MagicMock, call

from PyQt6.QtTest import QSignalSpy

from harness.tts_navigator import TtsNavigator


def _make_wav_bytes(duration_ms=100, sample_rate=24000):
    """Create a minimal valid WAV buffer for testing."""
    n_samples = int(sample_rate * duration_ms / 1000)
    samples = np.zeros(n_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def _make_chunks(n=3):
    """Create n (sentence, wav_bytes) test chunks."""
    return [(f"Sentence {i}.", _make_wav_bytes()) for i in range(n)]


# =====================================================================
# Initial state
# =====================================================================

@pytest.mark.ui
class TestTtsNavigatorInit:

    def test_empty_navigator(self, qapp):
        nav = TtsNavigator()
        assert nav.current_index == -1
        assert nav.chunk_count == 0
        assert nav.is_playing is False

    def test_default_output_device_is_none(self, qapp):
        nav = TtsNavigator()
        assert nav.output_device is None

    def test_load_chunks_resets_index(self, qapp):
        nav = TtsNavigator()
        chunks = _make_chunks(3)
        nav.load(chunks)
        assert nav.chunk_count == 3
        assert nav.current_index == 0

    def test_load_empty_list(self, qapp):
        nav = TtsNavigator()
        nav.load([])
        assert nav.chunk_count == 0
        assert nav.current_index == -1


# =====================================================================
# Navigation
# =====================================================================

@pytest.mark.ui
class TestNavigation:

    def test_next_advances_index(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(3))
        nav.next()
        assert nav.current_index == 1

    def test_next_clamps_at_end(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(2))
        nav.next()
        nav.next()
        nav.next()  # should clamp
        assert nav.current_index == 1

    def test_prev_goes_back(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(3))
        nav.next()
        nav.next()
        nav.prev()
        assert nav.current_index == 1

    def test_prev_clamps_at_start(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(3))
        nav.prev()
        assert nav.current_index == 0

    def test_next_on_empty_is_noop(self, qapp):
        nav = TtsNavigator()
        nav.next()
        assert nav.current_index == -1

    def test_prev_on_empty_is_noop(self, qapp):
        nav = TtsNavigator()
        nav.prev()
        assert nav.current_index == -1

    def test_current_text_returns_sentence(self, qapp):
        nav = TtsNavigator()
        chunks = _make_chunks(2)
        nav.load(chunks)
        assert nav.current_text == "Sentence 0."

    def test_current_text_empty_when_no_chunks(self, qapp):
        nav = TtsNavigator()
        assert nav.current_text == ""


# =====================================================================
# Signals
# =====================================================================

@pytest.mark.ui
class TestNavigatorSignals:

    def test_chunk_changed_on_load(self, qapp):
        nav = TtsNavigator()
        spy = QSignalSpy(nav.chunk_changed)
        nav.load(_make_chunks(2))
        assert len(spy) == 1
        assert spy[0] == [0, "Sentence 0."]

    def test_chunk_changed_on_next(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(3))
        spy = QSignalSpy(nav.chunk_changed)
        nav.next()
        assert len(spy) == 1
        assert spy[0] == [1, "Sentence 1."]

    def test_chunk_changed_on_prev(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(3))
        nav.next()
        nav.next()
        spy = QSignalSpy(nav.chunk_changed)
        nav.prev()
        assert len(spy) == 1
        assert spy[0] == [1, "Sentence 1."]

    def test_no_signal_when_clamped(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(2))
        nav.next()  # index = 1 (last)
        spy = QSignalSpy(nav.chunk_changed)
        nav.next()  # clamped — no change
        assert len(spy) == 0

    def test_playback_finished_signal(self, qapp):
        nav = TtsNavigator()
        spy = QSignalSpy(nav.playback_finished)
        nav.load(_make_chunks(1))
        # Simulate play finishing by calling the internal callback.
        nav._on_play_complete()
        assert len(spy) == 1

    @patch("harness.tts_navigator.sd")
    @patch("harness.tts_navigator.sf")
    def test_playback_error_signal(self, mock_sf, mock_sd, qapp):
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)
        mock_sd.play.side_effect = RuntimeError("device failure")

        nav = TtsNavigator()
        nav.load(_make_chunks(1))
        nav._is_playing = True
        nav._playback_token = 1
        spy = QSignalSpy(nav.playback_error)

        nav._play_worker(_make_wav_bytes(), 1.0, 1)

        assert len(spy) == 1
        assert "device failure" in spy[0][0]


# =====================================================================
# Playback (mocked sounddevice)
# =====================================================================

@pytest.mark.ui
class TestPlayback:

    def test_set_output_device(self, qapp):
        nav = TtsNavigator()
        nav.set_output_device(7)
        assert nav.output_device == 7

    @patch("harness.tts_navigator.sd")
    @patch("harness.tts_navigator.sf")
    def test_play_current_calls_sounddevice(self, mock_sf, mock_sd, qapp):
        import threading
        gate = threading.Event()
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)
        # Block sd.wait so thread stays alive long enough to check is_playing.
        mock_sd.wait.side_effect = lambda: gate.wait()

        nav = TtsNavigator()
        nav.load(_make_chunks(2))
        nav.play_current()

        assert nav.is_playing is True
        mock_sf.read.assert_called_once()
        mock_sd.play.assert_called_once()
        gate.set()  # release the thread

    @patch("harness.tts_navigator.sd")
    @patch("harness.tts_navigator.sf")
    def test_play_current_passes_selected_output_device(self, mock_sf, mock_sd, qapp):
        import threading

        gate = threading.Event()
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)
        mock_sd.wait.side_effect = lambda: gate.wait()

        nav = TtsNavigator()
        nav.set_output_device(5)
        nav.load(_make_chunks(1))
        nav.play_current()

        _, kwargs = mock_sd.play.call_args
        assert kwargs.get("device") == 5
        gate.set()

    @patch("harness.tts_navigator.sf")
    def test_start_word_highlight_emits_first_signal(self, mock_sf, qapp):
        mock_sf.info.return_value = MagicMock(frames=48000, samplerate=24000)
        nav = TtsNavigator()
        spy = QSignalSpy(nav.word_highlight)

        nav._start_word_highlight("hello brave world", _make_wav_bytes(), 1.0)

        assert len(spy) == 1
        assert spy[0] == [0, 3]
        assert nav._highlight_timer.isActive()

    @patch("harness.tts_navigator.sf")
    def test_stop_cancels_word_highlight_timer(self, mock_sf, qapp):
        mock_sf.info.return_value = MagicMock(frames=48000, samplerate=24000)
        nav = TtsNavigator()
        nav._is_playing = True
        nav._start_word_highlight("hello brave world", _make_wav_bytes(), 1.0)

        nav.stop()

        assert not nav._highlight_timer.isActive()

    @patch("harness.tts_navigator.sd")
    @patch("harness.tts_navigator.sf")
    def test_stop_stops_playback(self, mock_sf, mock_sd, qapp):
        import threading
        gate = threading.Event()
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)
        mock_sd.wait.side_effect = lambda: gate.wait()

        nav = TtsNavigator()
        nav.load(_make_chunks(1))
        nav.play_current()
        assert nav.is_playing is True
        nav.stop()

        mock_sd.stop.assert_called_once()
        assert nav.is_playing is False
        gate.set()  # release the thread

    def test_play_on_empty_is_noop(self, qapp):
        nav = TtsNavigator()
        nav.play_current()  # should not raise
        assert nav.is_playing is False

    def test_play_worker_emits_error_when_sounddevice_missing(self, qapp):
        nav = TtsNavigator()
        nav.load(_make_chunks(1))
        nav._is_playing = True
        nav._playback_token = 1
        spy = QSignalSpy(nav.playback_error)

        with patch("harness.tts_navigator.sd", None):
            nav._play_worker(_make_wav_bytes(), 1.0, 1)

        assert len(spy) == 1
        assert "sounddevice is unavailable" in spy[0][0]

    @patch("harness.tts_navigator.sd")
    @patch("harness.tts_navigator.sf")
    def test_play_all_auto_advances(self, mock_sf, mock_sd, qapp):
        """play_all() starts from current and auto-advances on completion."""
        import threading
        import time
        gate = threading.Event()
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)
        mock_sd.wait.side_effect = lambda: gate.wait()

        nav = TtsNavigator()
        nav.load(_make_chunks(3))
        nav.play_all()

        assert nav._auto_advance is True
        assert nav.is_playing is True
        # Release the first chunk so _on_play_complete fires (via QueuedConnection).
        gate.set()
        # Wait briefly for the background thread to finish and queue the slot.
        time.sleep(0.05)
        # Process pending Qt events so the queued slot executes.
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        assert nav.current_index == 1


# =====================================================================
# Speed control
# =====================================================================

@pytest.mark.ui
class TestSpeedControl:

    def test_default_speed(self, qapp):
        nav = TtsNavigator()
        assert nav.speed == 1.0

    def test_set_speed(self, qapp):
        nav = TtsNavigator()
        nav.set_speed(1.5)
        assert nav.speed == 1.5

    def test_speed_clamps_minimum(self, qapp):
        nav = TtsNavigator()
        nav.set_speed(0.1)
        assert nav.speed == 0.25

    def test_speed_clamps_maximum(self, qapp):
        nav = TtsNavigator()
        nav.set_speed(5.0)
        assert nav.speed == 3.0

    def test_speed_changed_signal(self, qapp):
        nav = TtsNavigator()
        spy = QSignalSpy(nav.speed_changed)
        nav.set_speed(2.0)
        assert len(spy) == 1

    @patch("harness.tts_navigator.sd")
    @patch("harness.tts_navigator.sf")
    def test_speed_affects_sample_rate(self, mock_sf, mock_sd, qapp):
        """When speed > 1.0, playback sample rate should be scaled up."""
        import threading
        gate = threading.Event()
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)
        mock_sd.wait.side_effect = lambda: gate.wait()

        nav = TtsNavigator()
        nav.set_speed(2.0)
        nav.load(_make_chunks(1))
        nav.play_current()

        # The play call should use sample_rate * speed
        args, kwargs = mock_sd.play.call_args
        assert kwargs.get("samplerate") == 48000 or args[1] == 48000
        gate.set()  # release the thread
