"""Persistent audio configuration storage."""

from typing import Optional

from PyQt6.QtCore import QSettings


_INPUT_DEVICE_KEY = "audio/input_device"
_OUTPUT_DEVICE_KEY = "audio/output_device"
_WAKE_WORD_KEY = "audio/wake_word_enabled"
_API_KEY_KEY = "llm/api_key"


class AudioSettingsStore:
    """Thin persistence seam for audio settings."""

    def __init__(self, settings: Optional[QSettings] = None) -> None:
        self._settings = settings or QSettings()

    def input_device(self) -> Optional[int]:
        return self._read_optional_int(_INPUT_DEVICE_KEY)

    def set_input_device(self, device_index: Optional[int]) -> None:
        self._write_optional_int(_INPUT_DEVICE_KEY, device_index)

    def output_device(self) -> Optional[int]:
        return self._read_optional_int(_OUTPUT_DEVICE_KEY)

    def set_output_device(self, device_index: Optional[int]) -> None:
        self._write_optional_int(_OUTPUT_DEVICE_KEY, device_index)

    def wake_word_enabled(self) -> bool:
        value = self._settings.value(_WAKE_WORD_KEY, False)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def set_wake_word_enabled(self, enabled: bool) -> None:
        self._settings.setValue(_WAKE_WORD_KEY, bool(enabled))

    def api_key(self) -> Optional[str]:
        value = self._settings.value(_API_KEY_KEY, None)
        if value in (None, "", "None"):
            return None
        return str(value)

    def set_api_key(self, key: Optional[str]) -> None:
        if key is None or key == "":
            self._settings.remove(_API_KEY_KEY)
            return
        self._settings.setValue(_API_KEY_KEY, key)

    def _read_optional_int(self, key: str) -> Optional[int]:
        value = self._settings.value(key, None)
        if value in (None, "", "None"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _write_optional_int(self, key: str, value: Optional[int]) -> None:
        if value is None:
            self._settings.remove(key)
            return
        self._settings.setValue(key, int(value))