"""Tests for harness/voice_input.py — VoiceInput with direct faster-whisper + WebRTC VAD."""

from unittest.mock import patch, MagicMock

import numpy as np

from harness.voice_input import VoiceInput


# ---------------------------------------------------------------------------
# Public API surface tests (preserved from Phase 4)
# ---------------------------------------------------------------------------


class TestVoiceInputAPI:
    """Verify the public interface is preserved after the rewrite."""

    def test_on_text_registers_callback(self):
        vi = VoiceInput(preload_model=False)
        cb = lambda text: None
        vi.on_text(cb)
        assert vi._callback is cb

    def test_initial_state(self):
        vi = VoiceInput(preload_model=False)
        assert vi._running is False
        assert vi._callback is None

    def test_default_audio_config(self):
        vi = VoiceInput(preload_model=False)
        assert vi.input_device_index is None

    def test_on_error_registers_callback(self):
        vi = VoiceInput(preload_model=False)
        cb = lambda message: None
        vi.on_error(cb)
        assert vi._error_callback is cb

    def test_on_recording_state_registers_callback(self):
        vi = VoiceInput(preload_model=False)
        cb = lambda active: None
        vi.on_recording_state(cb)
        assert vi._recording_state_callback is cb

    def test_on_status_registers_callback(self):
        vi = VoiceInput(preload_model=False)
        cb = lambda status: None
        vi.on_status(cb)
        assert vi._status_callback is cb

    def test_emit_status_calls_callback(self):
        vi = VoiceInput(preload_model=False)
        received = []
        vi.on_status(lambda s: received.append(s))
        vi._emit_status("loading")
        assert received == ["loading"]

    def test_emit_status_safe_without_callback(self):
        vi = VoiceInput(preload_model=False)
        vi._emit_status("loading")  # should not raise

    def test_stop_when_not_started(self):
        """stop() should be safe to call even if never started."""
        vi = VoiceInput(preload_model=False)
        vi.stop()
        assert vi._running is False

    def test_pause_when_not_started(self):
        """pause() should be safe when not running."""
        vi = VoiceInput(preload_model=False)
        vi.pause()

    def test_resume_when_not_started(self):
        """resume() should be safe when not running."""
        vi = VoiceInput(preload_model=False)
        vi.resume()

    def test_set_input_device_updates_config(self):
        vi = VoiceInput(preload_model=False)
        vi.set_input_device(4)
        assert vi.input_device_index == 4

    def test_set_input_device_none(self):
        vi = VoiceInput(preload_model=False)
        vi.set_input_device(4)
        vi.set_input_device(None)
        assert vi.input_device_index is None

    def test_start_sets_running_flag(self):
        vi = VoiceInput(preload_model=False)
        with patch.object(vi, "_listen_loop"):
            vi.start()
            assert vi._running is True
            vi.stop()

    def test_start_idempotent(self):
        vi = VoiceInput(preload_model=False)
        with patch.object(vi, "_listen_loop"):
            vi.start()
            thread1 = vi._thread
            vi.start()
            thread2 = vi._thread
            assert thread1 is thread2
            vi.stop()

    def test_pause_sets_flag(self):
        vi = VoiceInput(preload_model=False)
        vi._running = True
        vi.pause()
        assert vi._paused is True

    def test_resume_clears_pause(self):
        vi = VoiceInput(preload_model=False)
        vi._running = True
        vi._paused = True
        vi.resume()
        assert vi._paused is False


# ---------------------------------------------------------------------------
# Whisper model loading
# ---------------------------------------------------------------------------


class TestVoiceInputModel:
    """Verify whisper model loading and configuration."""

    def test_model_loads_base_en_with_int8_float16(self):
        """Model should be loaded as 'base.en' with validated CUDA compute type."""
        mock_cls = MagicMock()
        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        vi._load_model()
        mock_cls.assert_called_once()
        _, kwargs = mock_cls.call_args
        assert kwargs.get("compute_type") == "int8_float16"
        assert kwargs.get("device") == "cuda"

    def test_model_is_loaded_once_per_instance(self):
        """Model should only be created once per VoiceInput instance."""
        mock_cls = MagicMock()
        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        vi._load_model()
        vi._load_model()
        assert mock_cls.call_count == 1

    def test_model_load_failure_emits_error(self):
        mock_cls = MagicMock(side_effect=RuntimeError("CUDA OOM"))
        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        errors = []
        vi.on_error(lambda m: errors.append(m))
        vi._load_model()
        assert len(errors) == 1
        assert "CUDA OOM" in errors[0]

    def test_listen_loop_reemits_preload_failure_after_callbacks_registered(self):
        mock_cls = MagicMock(side_effect=RuntimeError("CUDA OOM"))
        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        vi._model_ready.set()
        vi._model_error_message = "Whisper model load failed: CUDA OOM"
        errors = []
        vi.on_error(lambda message: errors.append(message))

        with patch.dict("sys.modules", {"sounddevice": MagicMock()}):
            vi._running = True
            vi._listen_loop()

        assert errors == ["Whisper model load failed: CUDA OOM"]

    def test_mic_open_retries_before_stopping(self):
        class PortAudioError(RuntimeError):
            pass

        mock_sd = MagicMock()
        mock_sd.PortAudioError = PortAudioError
        mock_sd.InputStream.side_effect = PortAudioError("device locked")

        vi = VoiceInput(model_class=MagicMock(), preload_model=False)
        vi._model = object()
        vi._model_ready.set()
        vi._create_vad = MagicMock()
        vi._mic_open_max_retries = 2
        vi._mic_open_retry_delay = 0.0
        errors = []
        vi.on_error(lambda message: errors.append(message))

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            vi._running = True
            vi._listen_loop()

        assert mock_sd.InputStream.call_count == 2
        assert any("Mic open failed" in error for error in errors)
        assert vi._running is False


# ---------------------------------------------------------------------------
# VAD state machine
# ---------------------------------------------------------------------------


class TestVADStateMachine:
    """Verify the WebRTC VAD-based speech detection logic."""

    def test_vad_created_with_aggressiveness(self):
        """VAD should be created with aggressiveness=3."""
        mock_vad_mod = MagicMock()
        vi = VoiceInput(vad_module=mock_vad_mod, preload_model=False)
        vi._create_vad()
        mock_vad_mod.Vad.assert_called_once_with(3)

    def test_silence_duration_default(self):
        """Default post-speech silence should be 1.2s (increased for fewer false triggers)."""
        vi = VoiceInput(preload_model=False)
        assert vi._post_speech_silence == 1.2

    def test_min_speech_seconds_default(self):
        """Utterances shorter than 1.0s should be discarded."""
        vi = VoiceInput(preload_model=False)
        assert vi._min_speech_seconds == 1.0

    def test_min_words_default(self):
        """Transcriptions with fewer than 3 words should be discarded."""
        vi = VoiceInput(preload_model=False)
        assert vi._min_words == 3

    def test_pre_buffer_duration_default(self):
        """Default pre-recording buffer should be 0.3s."""
        vi = VoiceInput(preload_model=False)
        assert vi._pre_buffer_seconds == 0.3

    def test_ptt_mode_default_off(self):
        vi = VoiceInput(preload_model=False)
        assert vi._ptt_mode is False

    def test_set_ptt_mode_true(self):
        vi = VoiceInput(preload_model=False)
        vi.set_ptt_mode(True)
        assert vi._ptt_mode is True

    def test_set_ptt_mode_false_clears_active(self):
        vi = VoiceInput(preload_model=False)
        vi._ptt_active.set()
        vi.set_ptt_mode(False)
        assert not vi._ptt_active.is_set()

    def test_ptt_press_sets_event_when_ptt_on(self):
        vi = VoiceInput(preload_model=False)
        vi.set_ptt_mode(True)
        vi.ptt_press()
        assert vi._ptt_active.is_set()

    def test_ptt_press_no_op_when_ptt_off(self):
        vi = VoiceInput(preload_model=False)
        vi.ptt_press()  # PTT mode is off — should not set event
        assert not vi._ptt_active.is_set()

    def test_ptt_release_clears_event(self):
        vi = VoiceInput(preload_model=False)
        vi.set_ptt_mode(True)
        vi.ptt_press()
        vi.ptt_release()
        assert not vi._ptt_active.is_set()


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------


class TestTranscription:
    """Verify transcription calls and parameter tuning."""

    def test_transcribe_uses_beam_1(self):
        """Transcription should use beam_size=1 for lowest latency."""
        mock_model = MagicMock()
        mock_cls = MagicMock(return_value=mock_model)
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        vi._load_model()
        audio = np.zeros(16000, dtype=np.float32)
        vi._transcribe(audio)

        mock_model.transcribe.assert_called_once()
        _, kwargs = mock_model.transcribe.call_args
        assert kwargs.get("beam_size") == 1
        assert kwargs.get("language") == "en"

    def test_transcribe_returns_text(self):
        """Transcribed segments should be concatenated into final text."""
        mock_model = MagicMock()
        mock_cls = MagicMock(return_value=mock_model)

        seg1 = MagicMock()
        seg1.text = " Hello world"
        seg2 = MagicMock()
        seg2.text = " how are you"
        mock_model.transcribe.return_value = (iter([seg1, seg2]), MagicMock())

        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        vi._load_model()
        audio = np.zeros(16000, dtype=np.float32)
        result = vi._transcribe(audio)

        assert result == "Hello world how are you"

    def test_transcribe_empty_segments(self):
        """Empty segments should return empty string."""
        mock_model = MagicMock()
        mock_cls = MagicMock(return_value=mock_model)
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        vi._load_model()
        audio = np.zeros(16000, dtype=np.float32)
        result = vi._transcribe(audio)

        assert result == ""

    def test_transcribe_condition_on_previous_text_false(self):
        """Should not condition on previous text (avoids hallucination)."""
        mock_model = MagicMock()
        mock_cls = MagicMock(return_value=mock_model)
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        vi = VoiceInput(model_class=mock_cls, preload_model=False)
        vi._load_model()
        vi._transcribe(np.zeros(16000, dtype=np.float32))

        _, kwargs = mock_model.transcribe.call_args
        assert kwargs.get("condition_on_previous_text") is False


# ---------------------------------------------------------------------------
# Callback safety
# ---------------------------------------------------------------------------


class TestCallbackSafety:
    """Verify callbacks are invoked safely and errors are handled."""

    def test_callback_invoked_with_text(self):
        vi = VoiceInput(preload_model=False)
        received = []
        vi.on_text(lambda t: received.append(t))
        vi._emit_text("hello world test")
        assert received == ["hello world test"]

    def test_callback_not_invoked_for_short_utterance(self):
        """Transcriptions with fewer than min_words words are discarded."""
        vi = VoiceInput(preload_model=False)
        received = []
        vi.on_text(lambda t: received.append(t))
        vi._emit_text("hello")
        assert received == []

    def test_callback_not_invoked_for_empty_text(self):
        vi = VoiceInput(preload_model=False)
        received = []
        vi.on_text(lambda t: received.append(t))
        vi._emit_text("")
        assert received == []

    def test_callback_not_invoked_for_whitespace(self):
        vi = VoiceInput(preload_model=False)
        received = []
        vi.on_text(lambda t: received.append(t))
        vi._emit_text("   ")
        assert received == []

    def test_error_callback_invoked(self):
        vi = VoiceInput(preload_model=False)
        errors = []
        vi.on_error(lambda m: errors.append(m))
        vi._emit_error("boom")
        assert errors == ["boom"]

    def test_recording_state_callback(self):
        vi = VoiceInput(preload_model=False)
        states = []
        vi.on_recording_state(lambda a: states.append(a))
        vi._emit_recording_state(True)
        vi._emit_recording_state(False)
        assert states == [True, False]
