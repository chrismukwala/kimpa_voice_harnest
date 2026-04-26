"""Voice input — direct faster-whisper + WebRTC VAD.

Uses faster-whisper (CTranslate2) with the turbo model for low-latency
transcription.  WebRTC VAD detects speech boundaries.  No RealtimeSTT
dependency — this module owns the full mic → text pipeline.
"""

import collections
import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

log = logging.getLogger(__name__)

# Audio constants
SAMPLE_RATE = 16000
FRAME_MS = 30  # WebRTC VAD requires 10, 20, or 30 ms frames
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2  # 16-bit PCM


class VoiceInput:
    """Mic → text pipeline: sounddevice stream → WebRTC VAD → faster-whisper.

    Public API (unchanged from Phase 4):
        start(), stop(), pause(), resume()
        on_text(cb), on_error(cb), on_recording_state(cb), on_status(cb)
        set_input_device(index)
    """

    def __init__(
        self,
        input_device_index: Optional[int] = None,
        model_class=None,
        vad_module=None,
        preload_model: bool = True,
    ):
        self._callback: Optional[Callable[[str], None]] = None
        self._error_callback: Optional[Callable[[str], None]] = None
        self._recording_state_callback: Optional[Callable[[bool], None]] = None
        self._status_callback: Optional[Callable[[str], None]] = None

        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._input_device_index = input_device_index

        # Whisper model — preloaded in background thread for fast startup.
        self._model = None
        self._model_class = model_class
        self._model_error_message: Optional[str] = None
        self._model_ready = threading.Event()
        self._preload_thread: Optional[threading.Thread] = None
        if preload_model:
            self._preload_thread = threading.Thread(target=self._preload_model, daemon=True)
            self._preload_thread.start()

        # Audio stream (sounddevice.InputStream)
        self._stream = None

        # VAD config
        self._post_speech_silence = 1.2   # seconds of silence to end utterance (D: increased from 0.5)
        self._pre_buffer_seconds = 0.3    # audio kept before speech onset
        self._min_speech_seconds = 1.0    # (C) utterances shorter than this are discarded
        self._min_words = 3               # (A) utterances with fewer words are discarded

        # Push-to-talk
        self._ptt_mode = False
        self._ptt_active = threading.Event()
        self._vad = None
        self._vad_module = vad_module

        # Mic recovery policy.
        self._mic_open_retry_delay = 2.0
        self._mic_open_max_retries = 3

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def input_device_index(self) -> Optional[int]:
        return self._input_device_index

    def on_text(self, callback: Callable[[str], None]) -> None:
        """Register callback invoked with each final transcription."""
        self._callback = callback

    def on_error(self, callback: Callable[[str], None]) -> None:
        """Register callback invoked when an error occurs."""
        self._error_callback = callback

    def on_recording_state(self, callback: Callable[[bool], None]) -> None:
        """Register callback invoked when recording state changes."""
        self._recording_state_callback = callback

    def on_status(self, callback: Callable[[str], None]) -> None:
        """Register callback invoked with status updates."""
        self._status_callback = callback

    def start(self) -> None:
        """Begin listening.  Spawns the listen loop in its own thread."""
        if self._running:
            return
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening and clean up resources."""
        self._running = False
        self._paused = False
        self._stop_stream()
        self._emit_recording_state(False)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def pause(self) -> None:
        """Temporarily mute mic input."""
        self._paused = True
        self._stop_stream()
        self._emit_recording_state(False)

    def resume(self) -> None:
        """Resume after pause."""
        self._paused = False

    def set_input_device(self, device_index: Optional[int]) -> None:
        """Update the microphone device.  Takes effect on next stream restart."""
        self._input_device_index = None if device_index is None else int(device_index)
        # If currently running, restart the stream on next loop iteration
        self._stop_stream()

    def set_ptt_mode(self, enabled: bool) -> None:
        """Switch between push-to-talk mode and VAD mode."""
        self._ptt_mode = enabled
        if not enabled:
            self._ptt_active.clear()

    def ptt_press(self) -> None:
        """Signal that the push-to-talk button is being held."""
        if self._ptt_mode:
            self._ptt_active.set()

    def ptt_release(self) -> None:
        """Signal that the push-to-talk button was released."""
        self._ptt_active.clear()

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------
    def _preload_model(self) -> None:
        """Background thread: load the whisper model so it's ready before first speech."""
        try:
            self._load_model()
        except Exception as exc:
            self._model_error_message = f"Whisper model load failed: {exc}"
            log.error("Background model preload failed: %s", exc)

    def _load_model(self) -> bool:
        """Load the whisper base.en model.  Returns True on success."""
        if self._model is not None:
            self._model_ready.set()
            return True
        try:
            if self._model_class is None:
                from faster_whisper import WhisperModel
                self._model_class = WhisperModel
            log.info("Loading whisper base.en model (int8_float16)...")
            self._model = self._model_class(
                "base.en",
                device="cuda",
                compute_type="int8_float16",
            )
            self._model_ready.set()
            self._model_error_message = None
            log.info("Whisper base.en model loaded")
            return True
        except (RuntimeError, OSError, ImportError, ValueError) as exc:
            self._model_error_message = f"Whisper model load failed: {exc}"
            self._model_ready.set()  # unblock waiters even on failure
            self._emit_error(self._model_error_message)
            return False

    def _create_vad(self):
        """Create a WebRTC VAD instance with aggressiveness=3 (most aggressive)."""
        if self._vad_module is None:
            import webrtcvad
            self._vad_module = webrtcvad
        self._vad = self._vad_module.Vad(3)

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------
    def _transcribe(self, audio: np.ndarray) -> str:
        """Run whisper on an audio array (float32, 16kHz). Returns text."""
        if self._model is None:
            return ""
        segments, _ = self._model.transcribe(
            audio,
            beam_size=1,
            language="en",
            condition_on_previous_text=False,
            vad_filter=True,  # (B) Whisper Silero VAD strips non-speech before decoding
        )
        parts = []
        for seg in segments:
            parts.append(seg.text)
        return "".join(parts).strip()

    # ------------------------------------------------------------------
    # Listen loop
    # ------------------------------------------------------------------
    def _listen_loop(self) -> None:
        """Main loop: capture mic audio, detect speech via VAD, transcribe."""
        import sounddevice as sd

        self._emit_status("loading")
        self._model_ready.wait()  # wait for background preload
        if self._model is None:
            if self._model_error_message:
                self._emit_error(self._model_error_message)
            else:
                self._emit_error("Whisper model is not available")
            self._running = False
            return
        self._create_vad()
        mic_open_failures = 0

        # Pre-speech ring buffer (captures audio before VAD triggers)
        pre_buf_frames = max(1, int(self._pre_buffer_seconds / (FRAME_MS / 1000)))
        pre_buffer = collections.deque(maxlen=pre_buf_frames)

        # Frames of silence needed to end an utterance
        silence_frames_needed = int(self._post_speech_silence / (FRAME_MS / 1000))

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            # (Re)open the mic stream if needed
            if self._stream is None:
                try:
                    self._stream = sd.InputStream(
                        samplerate=SAMPLE_RATE,
                        channels=1,
                        dtype="int16",
                        blocksize=SAMPLES_PER_FRAME,
                        device=self._input_device_index,
                    )
                    self._stream.start()
                    mic_open_failures = 0
                    self._emit_recording_state(True)
                    self._emit_status("listening")
                except (RuntimeError, OSError, sd.PortAudioError) as exc:
                    mic_open_failures += 1
                    self._emit_error(
                        "Mic open failed "
                        f"(attempt {mic_open_failures}/{self._mic_open_max_retries}): {exc}"
                    )
                    self._emit_recording_state(False)
                    if mic_open_failures >= self._mic_open_max_retries:
                        self._running = False
                        break
                    self._emit_status("loading")
                    time.sleep(self._mic_open_retry_delay)
                    continue

            # --- Collect speech ---
            if self._ptt_mode:
                # PTT: wait for button press, then record while held
                while self._running and not self._paused and not self._ptt_active.is_set():
                    time.sleep(0.02)
                if not self._running or self._paused:
                    continue
                speech_frames = []
                self._emit_recording_state(True)
                try:
                    while self._running and self._ptt_active.is_set() and self._stream is not None:
                        data, overflowed = self._stream.read(SAMPLES_PER_FRAME)
                        if overflowed:
                            log.debug("Input overflow — dropped samples")
                        speech_frames.append(data.tobytes())
                except (RuntimeError, OSError) as exc:
                    log.warning("Stream read error: %s", exc)
                    self._stop_stream()
                    speech_frames = []
                finally:
                    self._emit_recording_state(False)
                if not speech_frames or not self._running:
                    continue
            else:
                # VAD: detect speech onset, collect until silence
                speech_frames = []
                silence_count = 0
                speaking = False
                pre_buffer.clear()
                try:
                    while self._running and not self._paused and self._stream is not None:
                        data, overflowed = self._stream.read(SAMPLES_PER_FRAME)
                        if overflowed:
                            log.debug("Input overflow — dropped samples")
                        frame_bytes = data.tobytes()
                        is_speech = self._vad.is_speech(frame_bytes, SAMPLE_RATE)
                        if not speaking:
                            pre_buffer.append(frame_bytes)
                            if is_speech:
                                speaking = True
                                silence_count = 0
                                speech_frames.extend(pre_buffer)
                                pre_buffer.clear()
                        else:
                            speech_frames.append(frame_bytes)
                            if is_speech:
                                silence_count = 0
                            else:
                                silence_count += 1
                                if silence_count >= silence_frames_needed:
                                    break  # End of utterance
                except (RuntimeError, OSError) as exc:
                    log.warning("Stream read error: %s", exc)
                    self._stop_stream()
                    continue
                if not speech_frames or not self._running:
                    continue

            # --- Convert to float32 for whisper ---
            raw = b"".join(speech_frames)
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            # (C) Discard clips too short — VAD mode only; PTT user decides duration
            if not self._ptt_mode:
                duration = len(pcm) / SAMPLE_RATE
                if duration < self._min_speech_seconds:
                    log.debug("Utterance too short (%.2fs) — discarded", duration)
                    continue
            # --- Transcribe ---
            self._emit_status("processing")
            text = self._transcribe(pcm)
            self._emit_status("listening")
            self._emit_text(text)

        self._stop_stream()
        self._emit_recording_state(False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _stop_stream(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except (RuntimeError, OSError):
            log.warning("Error closing audio stream", exc_info=True)
        finally:
            self._stream = None

    def _emit_text(self, text: str) -> None:
        if not text or not text.strip():
            return
        # (A) Discard likely hallucinations / noise transcriptions
        if len(text.strip().split()) < self._min_words:
            log.debug("Utterance too short (%r) — discarded", text)
            return
        if self._callback is not None:
            self._callback(text.strip())

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
