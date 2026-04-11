"""Manual audio smoke test for TTS playback diagnostics.

Lists output devices, plays a short sine wave, then tries a Kokoro sample through the
same output path used by the app. The `--device` index matches the override used by
`TtsNavigator.set_output_device()`.
"""

__test__ = False

import argparse
import io
import sys
from typing import Iterable, Optional

import numpy as np
import soundfile as sf

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover - manual diagnostic script
    raise SystemExit(f"sounddevice is required for this tool: {exc}")

from harness import tts as tts_mod


_DEFAULT_TEXT = "Voice Harness audio smoke test. If you can hear this, playback works."


def _default_output_index() -> Optional[int]:
    default_device = sd.default.device
    if hasattr(default_device, "__getitem__"):
        try:
            output_index = default_device[1]
        except (IndexError, KeyError):
            output_index = default_device
    else:
        output_index = default_device
    if output_index in (None, -1):
        return None
    return int(output_index)


def _iter_output_devices() -> Iterable[tuple[int, str, int]]:
    for index, device in enumerate(sd.query_devices()):
        max_output_channels = int(device.get("max_output_channels", 0))
        if max_output_channels > 0:
            yield index, str(device.get("name", f"Device {index}")), max_output_channels


def _print_output_devices() -> None:
    default_index = _default_output_index()
    print("Output devices:")
    for index, name, channels in _iter_output_devices():
        marker = " (default)" if index == default_index else ""
        print(f"  [{index}] {name} - {channels} ch{marker}")
    if default_index is None:
        print("No default output device is configured.")


def _make_sine_wave(duration_s: float = 0.75, sample_rate: int = 48000) -> np.ndarray:
    timeline = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return (0.15 * np.sin(2 * np.pi * 440.0 * timeline)).astype(np.float32)


def _play_array(data: np.ndarray, sample_rate: int, device: Optional[int]) -> None:
    sd.play(data, samplerate=sample_rate, device=device)
    sd.wait()


def _play_sine(device: Optional[int]) -> None:
    print("Playing sine-wave probe...")
    _play_array(_make_sine_wave(), 48000, device)
    print("Sine-wave probe completed.")


def _play_kokoro_sample(text: str, device: Optional[int]) -> None:
    print("Generating Kokoro sample...")
    chunks = tts_mod.speak(text)
    if not chunks:
        raise RuntimeError("Kokoro returned no audio chunks")

    sentence, wav_bytes = chunks[0]
    data, sample_rate = sf.read(io.BytesIO(wav_bytes))
    print(f"Playing Kokoro sample: {sentence}")
    _play_array(data, int(sample_rate), device)
    print("Kokoro sample completed.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        type=int,
        help="Output device index to use (same index accepted by TtsNavigator.set_output_device)",
    )
    parser.add_argument("--list-only", action="store_true", help="Only list output devices")
    parser.add_argument("--skip-sine", action="store_true", help="Skip the sine-wave probe")
    parser.add_argument("--skip-kokoro", action="store_true", help="Skip the Kokoro probe")
    parser.add_argument("--text", default=_DEFAULT_TEXT, help="Text for the Kokoro sample")
    args = parser.parse_args(argv)

    if sys.version_info[:2] != (3, 11):
        print(
            "Warning: Voice Harness audio dependencies are supported on Python 3.11.x; "
            f"current version is {sys.version.split()[0]}."
        )

    _print_output_devices()
    if args.list_only:
        return 0

    device = args.device if args.device is not None else _default_output_index()
    if device is None:
        print("No usable output device found.")
        return 1

    print(f"Using output device index: {device}")

    success = True

    if not args.skip_sine:
        try:
            _play_sine(device)
        except (RuntimeError, ValueError) as exc:
            print(f"Sine-wave probe failed: {exc}")
            success = False

    if not args.skip_kokoro:
        try:
            _play_kokoro_sample(args.text, device)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            print(f"Kokoro probe failed: {exc}")
            success = False

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())