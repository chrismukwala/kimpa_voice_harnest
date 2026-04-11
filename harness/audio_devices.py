"""Audio device enumeration helpers."""

from typing import Optional

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - depends on local audio stack
    sd = None  # type: ignore[assignment]


def _query_devices() -> list[dict]:
    if sd is None:
        return []
    try:
        return list(sd.query_devices())
    except (RuntimeError, ValueError):
        return []


def _default_device_index(slot: int) -> Optional[int]:
    if sd is None:
        return None
    default_device = getattr(sd.default, "device", None)
    if hasattr(default_device, "__getitem__"):
        try:
            value = default_device[slot]
        except (IndexError, KeyError):
            value = default_device
    else:
        value = default_device
    if value in (None, -1):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_input_devices() -> list[dict]:
    """Return input-capable audio devices."""
    devices = []
    for index, device in enumerate(_query_devices()):
        channels = int(device.get("max_input_channels", 0))
        if channels > 0:
            devices.append({
                "index": index,
                "name": str(device.get("name", f"Input {index}")),
                "channels": channels,
            })
    return devices


def list_output_devices() -> list[dict]:
    """Return output-capable audio devices."""
    devices = []
    for index, device in enumerate(_query_devices()):
        channels = int(device.get("max_output_channels", 0))
        if channels > 0:
            devices.append({
                "index": index,
                "name": str(device.get("name", f"Output {index}")),
                "channels": channels,
            })
    return devices


def get_default_input() -> Optional[int]:
    """Return the default input device index, if any."""
    return _default_device_index(0)


def get_default_output() -> Optional[int]:
    """Return the default output device index, if any."""
    return _default_device_index(1)