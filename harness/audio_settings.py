"""Persistent audio configuration storage."""

import base64
import ctypes
import logging
import os
from typing import Optional

from PyQt6.QtCore import QSettings


_INPUT_DEVICE_KEY = "audio/input_device"
_OUTPUT_DEVICE_KEY = "audio/output_device"
_WAKE_WORD_KEY = "audio/wake_word_enabled"
_API_KEY_KEY = "llm/api_key"
_PROTECTED_PREFIX = "dpapi:"

log = logging.getLogger(__name__)


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
        text = str(value)
        if text.startswith(_PROTECTED_PREFIX):
            decrypted = _unprotect_text(text.removeprefix(_PROTECTED_PREFIX))
            if decrypted is None:
                log.warning("Stored API key could not be decrypted; use GEMINI_API_KEY instead")
            return decrypted
        return text

    def set_api_key(self, key: Optional[str]) -> None:
        if key is None or key == "":
            self._settings.remove(_API_KEY_KEY)
            return
        protected = _protect_text(key)
        if protected is None:
            log.warning("API key was not stored; configure GEMINI_API_KEY instead")
            self._settings.remove(_API_KEY_KEY)
            return
        self._settings.setValue(_API_KEY_KEY, f"{_PROTECTED_PREFIX}{protected}")

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


def _protect_text(text: str) -> Optional[str]:
    data = text.encode("utf-8")
    encrypted = _dpapi_protect(data)
    if encrypted is None:
        if os.name == "nt":
            return None
        encrypted = base64.b64encode(data)
        return "portable:" + encrypted.decode("ascii")
    return base64.b64encode(encrypted).decode("ascii")


def _unprotect_text(payload: str) -> Optional[str]:
    if payload.startswith("portable:"):
        try:
            return base64.b64decode(payload.removeprefix("portable:")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    try:
        encrypted = base64.b64decode(payload)
    except ValueError:
        return None
    decrypted = _dpapi_unprotect(encrypted)
    if decrypted is None:
        return None
    try:
        return decrypted.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _dpapi_protect(data: bytes) -> Optional[bytes]:
    if os.name != "nt":
        return None
    try:
        import win32crypt
        encrypted = win32crypt.CryptProtectData(data, None, None, None, None, 0)
        return encrypted
    except ImportError:
        return _crypt_protect_data(data)
    except (RuntimeError, OSError, ValueError):
        return None


def _dpapi_unprotect(data: bytes) -> Optional[bytes]:
    if os.name != "nt":
        return None
    try:
        import win32crypt
        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
    except ImportError:
        return _crypt_unprotect_data(data)
    except (RuntimeError, OSError, ValueError):
        return None


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _bytes_to_blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _crypt_protect_data(data: bytes) -> Optional[bytes]:
    in_blob, _buffer = _bytes_to_blob(data)
    out_blob = _DataBlob()
    try:
        result = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
        if not result:
            return None
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)



def _crypt_unprotect_data(data: bytes) -> Optional[bytes]:
    in_blob, _buffer = _bytes_to_blob(data)
    out_blob = _DataBlob()
    try:
        result = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
        if not result:
            return None
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)