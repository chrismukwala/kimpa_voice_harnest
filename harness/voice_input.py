"""Voice input — thin adapter around RealtimeSTT."""

import logging
import threading
import time
from typing import Callable, Optional

log = logging.getLogger(__name__)


class VoiceInput:
    """Thin wrapper: start()/stop()/on_text(cb).

    Nothing else in the project imports RealtimeSTT directly.
    If RealtimeSTT needs replacing, only this file changes.
    """

    def __init__(self, input_device_index: Optional[int] = None, wake_word_enabled: bool = False):
        self._callback: Optional[Callable[[str], None]] = None
        self._error_callback: Optional[Callable[[str], None]] = None
        self._recording_state_callback: Optional[Callable[[bool], None]] = None
        self._status_callback: Optional[Callable[[str], None]] = None
        self._recorder = None
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._input_device_index = input_device_index
        self._wake_word_enabled = wake_word_enabled
        self._reconfigure_requested = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def input_device_index(self) -> Optional[int]:
        return self._input_device_index

    @property
    def wake_word_enabled(self) -> bool:
        return self._wake_word_enabled

    def on_text(self, callback: Callable[[str], None]) -> None:
        """Register callback invoked with each final transcription."""
        self._callback = callback

    def on_error(self, callback: Callable[[str], None]) -> None:
        """Register callback invoked when the recorder reports an error."""
        self._error_callback = callback

    def on_recording_state(self, callback: Callable[[bool], None]) -> None:
        """Register callback invoked when the recording state changes."""
        self._recording_state_callback = callback

    def on_status(self, callback: Callable[[str], None]) -> None:
        """Register callback invoked with status updates (e.g. 'loading')."""
        self._status_callback = callback

    def start(self) -> None:
        """Begin listening.  Spawns RealtimeSTT in its own thread."""
        if self._running:
            return
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening and shut down the recorder."""
        self._running = False
        self._paused = False
        self._stop_recorder("stopping")
        self._emit_recording_state(False)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def pause(self) -> None:
        """Temporarily mute mic input (for video calls)."""
        self._paused = True
        self._stop_recorder("pausing")
        self._emit_recording_state(False)

    def resume(self) -> None:
        """Resume after pause."""
        self._paused = False
        if self._running and self._recorder is not None:
            try:
                self._recorder.start()
                self._emit_recording_state(True)
            except (RuntimeError, OSError, TypeError, ValueError):
                log.warning("Error resuming recorder", exc_info=True)
        elif self._running:
            self._reconfigure_requested = True

    def set_input_device(self, device_index: Optional[int]) -> None:
        """Update the microphone device and recreate the recorder if needed."""
        self._input_device_index = None if device_index is None else int(device_index)
        self._request_reconfigure()

    def set_wake_word_enabled(self, enabled: bool) -> None:
        """Enable or disable wake-word gating and recreate the recorder if needed."""
        self._wake_word_enabled = bool(enabled)
        self._request_reconfigure()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _listen_loop(self) -> None:
        try:
            from RealtimeSTT import AudioToTextRecorder
        except ImportError as exc:
            self._emit_error(f"Voice input import failed: {exc}")
            self._emit_recording_state(False)
            self._running = False
            return

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            if self._recorder is None or self._reconfigure_requested:
                self._stop_recorder("reconfiguring")
                self._reconfigure_requested = False
                self._emit_status("loading")
                try:
                    log.info(
                        "Creating recorder (input_device=%s, wake_word=%s)",
                        self._input_device_index,
                        self._wake_word_enabled,
                    )
                    self._recorder = self._create_recorder(AudioToTextRecorder)
                    self._recorder.start()
                    log.info("Recorder started")
                    self._emit_recording_state(True)
                    self._emit_status("listening")
                except (RuntimeError, OSError, TypeError, ValueError) as exc:
                    self._emit_error(f"Voice input start failed: {exc}")
                    self._emit_recording_state(False)
                    self._running = False
                    break

            try:
                log.debug("Waiting for recorder text")
                text = self._recorder.text() if self._recorder is not None else None
                if text:
                    log.info("Recorder produced transcription")
            except (RuntimeError, OSError, TypeError, ValueError) as exc:
                if self._paused or self._reconfigure_requested or not self._running:
                    continue
                self._emit_error(f"Voice input error: {exc}")
                self._emit_recording_state(False)
                self._reconfigure_requested = True
                continue

            if self._reconfigure_requested or self._paused:
                continue
            if text and self._callback:
                self._callback(text.strip())

        self._stop_recorder("stopping")
        self._emit_recording_state(False)

    def _create_recorder(self, recorder_cls):
        kwargs = {
            "model": "large-v3",
            "compute_type": "int8_float16",
            "language": "en",
            "min_gap_between_recordings": 0,
            "spinner": False,
            "use_microphone": True,
            "silero_sensitivity": 0.4,
            "post_speech_silence_duration": 1.2,
        }
        if self._wake_word_enabled:
            kwargs["wake_words"] = "hey_jarvis"
        if self._input_device_index is not None:
            kwargs["input_device_index"] = self._input_device_index
        return recorder_cls(**kwargs)

    def _request_reconfigure(self) -> None:
        self._reconfigure_requested = True
        if self._running:
            self._stop_recorder("reconfiguring")

    def _stop_recorder(self, action: str) -> None:
        if self._recorder is None:
            return
        try:
            self._recorder.stop()
        except (RuntimeError, OSError, TypeError, ValueError):
            log.warning("Error %s recorder", action, exc_info=True)
        finally:
            self._recorder = None

    def _emit_error(self, message: str) -> None:
        log.warning(message)
        if self._error_callback is not None:
            self._error_callback(message)

    def _emit_recording_state(self, active: bool) -> None:
        if self._recording_state_callback is not None:
            self._recording_state_callback(active)

    def _emit_status(self, status: str) -> None:
        if self._status_callback is not None:
            self._status_callback(status)
