"""Manual microphone smoke test for Voice Harness.

Lists input devices, records a short sample, prints amplitude stats, and can optionally
attempt one live RealtimeSTT transcription.
"""

__test__ = False

import argparse
import sys
from typing import Iterable, Optional

import numpy as np

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover - manual diagnostic script
    raise SystemExit(f"sounddevice is required for this tool: {exc}")


def _default_input_index() -> Optional[int]:
    default_device = sd.default.device
    if hasattr(default_device, "__getitem__"):
        try:
            input_index = default_device[0]
        except (IndexError, KeyError):
            input_index = default_device
    else:
        input_index = default_device
    if input_index in (None, -1):
        return None
    return int(input_index)


def _iter_input_devices() -> Iterable[tuple[int, str, int]]:
    for index, device in enumerate(sd.query_devices()):
        max_input_channels = int(device.get("max_input_channels", 0))
        if max_input_channels > 0:
            yield index, str(device.get("name", f"Device {index}")), max_input_channels


def _print_input_devices() -> None:
    default_index = _default_input_index()
    print("Input devices:")
    for index, name, channels in _iter_input_devices():
        marker = " (default)" if index == default_index else ""
        print(f"  [{index}] {name} - {channels} ch{marker}")
    if default_index is None:
        print("No default input device is configured.")


def _record_sample(duration_s: float, device: Optional[int], sample_rate: int) -> np.ndarray:
    frame_count = int(sample_rate * duration_s)
    data = sd.rec(
        frame_count,
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    return np.asarray(data).reshape(-1)


def _print_amplitude_stats(data: np.ndarray) -> None:
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0
    print(f"Peak amplitude: {peak:.5f}")
    print(f"RMS amplitude:  {rms:.5f}")


def _transcribe_once(device: Optional[int]) -> None:
    try:
        from RealtimeSTT import AudioToTextRecorder
    except ImportError as exc:
        print(f"RealtimeSTT import failed: {exc}")
        return

    kwargs = {
        "model": "large-v3",
        "compute_type": "int8_float16",
        "language": "en",
        "min_length": 3,
        "min_gap_between_recordings": 0,
        "spinner": False,
        "use_microphone": True,
        "silero_sensitivity": 0.4,
        "post_speech_silence_duration": 1.2,
    }
    if device is not None:
        kwargs["input_device_index"] = device

    recorder = AudioToTextRecorder(**kwargs)
    print("RealtimeSTT ready. Speak one short sentence...")
    recorder.start()
    try:
        text = recorder.text()
        print(f"Transcription: {text!r}")
    finally:
        recorder.stop()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, help="Input device index to use")
    parser.add_argument("--list-only", action="store_true", help="Only list input devices")
    parser.add_argument("--duration", type=float, default=3.0, help="Record duration in seconds")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate for the probe")
    parser.add_argument("--transcribe", action="store_true", help="Attempt one RealtimeSTT transcription")
    args = parser.parse_args(argv)

    if sys.version_info[:2] != (3, 11):
        print(
            "Warning: Voice Harness audio dependencies are supported on Python 3.11.x; "
            f"current version is {sys.version.split()[0]}."
        )

    _print_input_devices()
    if args.list_only:
        return 0

    device = args.device if args.device is not None else _default_input_index()
    if device is None:
        print("No usable input device found.")
        return 1

    print(f"Using input device index: {device}")
    try:
        print(f"Recording {args.duration:.1f}s sample...")
        data = _record_sample(args.duration, device, args.sample_rate)
        _print_amplitude_stats(data)
    except (RuntimeError, ValueError) as exc:
        print(f"Microphone probe failed: {exc}")
        return 1

    if args.transcribe:
        _transcribe_once(device)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())