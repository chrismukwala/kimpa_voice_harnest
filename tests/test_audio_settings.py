"""Tests for harness/audio_settings.py."""

from PyQt6.QtCore import QSettings

from harness.audio_settings import AudioSettingsStore, _API_KEY_KEY


def _make_settings(tmp_path):
    return QSettings(str(tmp_path / "audio.ini"), QSettings.Format.IniFormat)


class TestAudioSettingsStore:
    def test_defaults(self, tmp_path):
        store = AudioSettingsStore(_make_settings(tmp_path))

        assert store.input_device() is None
        assert store.output_device() is None
        assert store.wake_word_enabled() is False

    def test_input_device_persists(self, tmp_path):
        settings = _make_settings(tmp_path)
        store = AudioSettingsStore(settings)

        store.set_input_device(3)

        reloaded = AudioSettingsStore(settings)
        assert reloaded.input_device() == 3

    def test_output_device_can_be_cleared(self, tmp_path):
        settings = _make_settings(tmp_path)
        store = AudioSettingsStore(settings)
        store.set_output_device(5)

        store.set_output_device(None)

        assert store.output_device() is None

    def test_wake_word_enabled_persists(self, tmp_path):
        settings = _make_settings(tmp_path)
        store = AudioSettingsStore(settings)

        store.set_wake_word_enabled(True)

        reloaded = AudioSettingsStore(settings)
        assert reloaded.wake_word_enabled() is True

    def test_api_key_defaults_to_none(self, tmp_path):
        store = AudioSettingsStore(_make_settings(tmp_path))
        assert store.api_key() is None

    def test_api_key_persists(self, tmp_path):
        settings = _make_settings(tmp_path)
        store = AudioSettingsStore(settings)

        store.set_api_key("my-secret-key")

        reloaded = AudioSettingsStore(settings)
        assert reloaded.api_key() == "my-secret-key"

    def test_api_key_is_not_stored_plaintext(self, tmp_path):
        settings = _make_settings(tmp_path)
        store = AudioSettingsStore(settings)

        store.set_api_key("my-secret-key")

        raw_value = settings.value(_API_KEY_KEY, None)
        assert raw_value != "my-secret-key"

    def test_api_key_can_be_cleared(self, tmp_path):
        settings = _make_settings(tmp_path)
        store = AudioSettingsStore(settings)
        store.set_api_key("key-to-clear")

        store.set_api_key(None)

        assert store.api_key() is None

    def test_api_key_empty_string_clears(self, tmp_path):
        settings = _make_settings(tmp_path)
        store = AudioSettingsStore(settings)
        store.set_api_key("key-to-clear")

        store.set_api_key("")

        assert store.api_key() is None