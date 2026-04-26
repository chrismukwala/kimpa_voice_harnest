"""Tests for harness/tts.py — sentence splitting + speak/play contracts."""

from unittest.mock import patch, MagicMock
import numpy as np
import io

from harness.tts import _split_sentences


# =====================================================================
# _split_sentences
# =====================================================================

class TestSplitSentences:
    """Verify the crude sentence splitter used before TTS synthesis."""

    def test_single_sentence(self):
        result = _split_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_multiple_sentences(self):
        result = _split_sentences("First sentence. Second sentence. Third one!")
        assert len(result) == 3
        assert result[0] == "First sentence."
        assert result[2] == "Third one!"

    def test_question_mark(self):
        result = _split_sentences("What is this? It is a test.")
        assert len(result) == 2

    def test_exclamation(self):
        result = _split_sentences("Wow! That works!")
        assert len(result) == 2

    def test_empty_string(self):
        result = _split_sentences("")
        assert result == []

    def test_whitespace_only(self):
        result = _split_sentences("   ")
        assert result == []

    def test_no_terminal_punctuation(self):
        result = _split_sentences("No punctuation here")
        assert result == ["No punctuation here"]

    def test_strips_leading_trailing_whitespace(self):
        result = _split_sentences("  Hello world.  ")
        assert result == ["Hello world."]

    def test_preserves_sentence_content(self):
        result = _split_sentences("I added a docstring. The function now has type hints.")
        assert "I added a docstring." in result
        assert "The function now has type hints." in result


# =====================================================================
# speak (mocked Kokoro)
# =====================================================================

class TestSpeak:
    """Verify speak() returns List[Tuple[str, bytes]] contract."""

    @patch("harness.tts.KPipeline", create=True)
    def test_speak_returns_list_of_tuples(self, _mock_kpipeline_cls):
        """The return type contract: List[Tuple[str, bytes]]."""
        # Mock the KPipeline to yield a fake audio array.
        mock_pipeline_instance = MagicMock()
        _mock_kpipeline_cls.return_value = mock_pipeline_instance

        fake_audio = np.zeros(2400, dtype=np.float32)
        mock_pipeline_instance.return_value = iter([(0, 0, fake_audio)])

        # Patch the lazy import inside speak().
        with patch.dict("sys.modules", {"kokoro": MagicMock(KPipeline=_mock_kpipeline_cls)}):
            from harness.tts import speak
            result = speak("Hello.")

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            sentence, wav_data = item
            assert isinstance(sentence, str)
            assert isinstance(wav_data, bytes)

    @patch("harness.tts.KPipeline", create=True)
    def test_speak_empty_text_returns_empty_list(self, _mock_kpipeline_cls):
        with patch.dict("sys.modules", {"kokoro": MagicMock(KPipeline=_mock_kpipeline_cls)}):
            from harness.tts import speak
            result = speak("")
        assert result == []


# =====================================================================
# play_wav_bytes (mocked sounddevice)
# =====================================================================

class TestPlayWavBytes:
    """Verify play_wav_bytes calls sounddevice correctly."""

    @patch("harness.tts.sd", create=True)
    @patch("harness.tts.sf")
    def test_play_wav_bytes_calls_sounddevice(self, mock_sf, mock_sd):
        fake_data = np.zeros(100, dtype=np.float32)
        mock_sf.read.return_value = (fake_data, 24000)

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            from harness.tts import play_wav_bytes
            play_wav_bytes(b"fake wav data")

        mock_sd.play.assert_called_once()
        mock_sd.wait.assert_called_once()


# =====================================================================
# speak_stream (Phase 5 streaming TTS)
# =====================================================================

class TestSpeakStream:
    """Verify speak_stream() yields (sentence, wav_bytes) from an iterator."""

    @patch("harness.tts._pipeline", None)
    @patch("harness.tts.KPipeline", create=True)
    def test_speak_stream_yields_incrementally(self, _mock_kpipeline_cls):
        """speak_stream should yield one chunk per sentence from the iterator."""
        mock_pipeline = MagicMock()
        _mock_kpipeline_cls.return_value = mock_pipeline

        fake_audio = np.zeros(2400, dtype=np.float32)
        mock_pipeline.side_effect = lambda text, voice: iter([(0, 0, fake_audio)])

        with patch.dict("sys.modules", {"kokoro": MagicMock(KPipeline=_mock_kpipeline_cls)}):
            from harness.tts import speak_stream
            sentences = iter(["Hello.", "World."])
            results = list(speak_stream(sentences))

        assert len(results) == 2
        for sentence, wav_data in results:
            assert isinstance(sentence, str)
            assert isinstance(wav_data, bytes)

    @patch("harness.tts._pipeline", None)
    @patch("harness.tts.KPipeline", create=True)
    def test_speak_stream_empty_iterator(self, _mock_kpipeline_cls):
        with patch.dict("sys.modules", {"kokoro": MagicMock(KPipeline=_mock_kpipeline_cls)}):
            from harness.tts import speak_stream
            results = list(speak_stream(iter([])))
        assert results == []

    @patch("harness.tts._pipeline", None)
    @patch("harness.tts.KPipeline", create=True)
    def test_speak_stream_skips_empty_sentences(self, _mock_kpipeline_cls):
        mock_pipeline = MagicMock()
        _mock_kpipeline_cls.return_value = mock_pipeline

        fake_audio = np.zeros(2400, dtype=np.float32)
        mock_pipeline.side_effect = lambda text, voice: iter([(0, 0, fake_audio)])

        with patch.dict("sys.modules", {"kokoro": MagicMock(KPipeline=_mock_kpipeline_cls)}):
            from harness.tts import speak_stream
            sentences = iter(["Hello.", "", "  "])
            results = list(speak_stream(sentences))

        assert len(results) == 1
        assert results[0][0] == "Hello."

    @patch("harness.tts._pipeline", None)
    @patch("harness.tts.KPipeline", create=True)
    def test_speak_stream_continues_after_bad_sentence(self, _mock_kpipeline_cls):
        mock_pipeline = MagicMock()
        _mock_kpipeline_cls.return_value = mock_pipeline

        good_audio = np.zeros(2400, dtype=np.float32)
        bad_audio = np.zeros((2, 2), dtype=np.float32)
        mock_pipeline.side_effect = [
            iter([(0, 0, bad_audio)]),
            iter([(0, 0, good_audio)]),
        ]

        with patch.dict("sys.modules", {"kokoro": MagicMock(KPipeline=_mock_kpipeline_cls)}):
            from harness.tts import speak_stream
            results = list(speak_stream(iter(["Bad.", "Good."])))

        assert len(results) == 1
        assert results[0][0] == "Good."

    @patch("harness.tts._pipeline", None)
    @patch("harness.tts.KPipeline", create=True)
    def test_speak_stream_serializes_pipeline_calls(self, _mock_kpipeline_cls):
        mock_pipeline = MagicMock()
        _mock_kpipeline_cls.return_value = mock_pipeline
        fake_audio = np.zeros(2400, dtype=np.float32)
        mock_pipeline.side_effect = lambda text, voice: iter([(0, 0, fake_audio)])

        with patch.dict("sys.modules", {"kokoro": MagicMock(KPipeline=_mock_kpipeline_cls)}):
            from harness import tts
            with patch.object(tts, "_synthesis_lock") as mock_lock:
                mock_lock.__enter__.return_value = None
                mock_lock.__exit__.return_value = None
                list(tts.speak_stream(iter(["One.", "Two."])))

        assert mock_lock.__enter__.call_count == 2


# =====================================================================
# GPU device configuration (Phase 5)
# =====================================================================

class TestTTSDevice:
    """Verify Kokoro can be configured for GPU execution."""

    def test_default_device_is_gpu_or_cpu(self):
        """Device is cuda when torch CUDA is available, otherwise cpu — never a bad value."""
        from harness.tts import TTS_DEVICE
        assert TTS_DEVICE in ("cuda", "cpu")
