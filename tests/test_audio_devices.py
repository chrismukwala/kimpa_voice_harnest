"""Tests for harness/audio_devices.py."""

from unittest.mock import patch

from harness import audio_devices


class TestAudioDevices:
    @patch("harness.audio_devices.sd")
    def test_list_input_devices_filters_input_capable(self, mock_sd):
        mock_sd.query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2},
        ]

        devices = audio_devices.list_input_devices()

        assert devices == [{"index": 0, "name": "Mic", "channels": 2}]

    @patch("harness.audio_devices.sd")
    def test_list_output_devices_filters_output_capable(self, mock_sd):
        mock_sd.query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2},
        ]

        devices = audio_devices.list_output_devices()

        assert devices == [{"index": 1, "name": "Speaker", "channels": 2}]

    @patch("harness.audio_devices.sd")
    def test_get_default_input_from_tuple(self, mock_sd):
        mock_sd.default.device = (4, 7)

        assert audio_devices.get_default_input() == 4

    @patch("harness.audio_devices.sd")
    def test_get_default_output_from_tuple(self, mock_sd):
        mock_sd.default.device = (4, 7)

        assert audio_devices.get_default_output() == 7

    def test_returns_empty_when_sounddevice_missing(self):
        with patch("harness.audio_devices.sd", None):
            assert audio_devices.list_input_devices() == []
            assert audio_devices.list_output_devices() == []
            assert audio_devices.get_default_input() is None
            assert audio_devices.get_default_output() is None

    @patch("harness.audio_devices.sd")
    def test_query_error_returns_empty_devices(self, mock_sd):
        mock_sd.query_devices.side_effect = RuntimeError("boom")

        assert audio_devices.list_input_devices() == []
        assert audio_devices.list_output_devices() == []