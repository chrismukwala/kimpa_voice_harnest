"""TTS Navigator — arrow-key sentence navigation + speed-adjusted playback."""

import io
import logging
import threading
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

import soundfile as sf

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover — test env may lack sounddevice
    sd = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Speed limits.
_MIN_SPEED = 0.25
_MAX_SPEED = 3.0


class TtsNavigator(QObject):
    """Manages a list of (sentence, wav_bytes) chunks with navigation and playback.

    Supports arrow-key prev/next, play-all with auto-advance, and speed control.
    """

    chunk_changed = pyqtSignal(int, str)      # (index, sentence_text)
    playback_finished = pyqtSignal()
    playback_error = pyqtSignal(str)
    speed_changed = pyqtSignal(float)
    word_highlight = pyqtSignal(int, int)
    _playback_complete = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chunks: List[Tuple[str, bytes]] = []
        self._index: int = -1
        self._is_playing: bool = False
        self._speed: float = 1.0
        self._output_device: Optional[int] = None
        self._auto_advance: bool = False
        self._play_thread: Optional[threading.Thread] = None
        self._playback_token: int = 0
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setSingleShot(True)
        self._highlight_timer.timeout.connect(self._advance_word_highlight)
        self._highlight_intervals_ms: List[int] = []
        self._highlight_word_index = -1
        self._highlight_word_count = 0
        self._playback_complete.connect(self._on_play_complete_for_token)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def current_index(self) -> int:
        return self._index

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def output_device(self) -> Optional[int]:
        return self._output_device

    @property
    def current_text(self) -> str:
        if 0 <= self._index < len(self._chunks):
            return self._chunks[self._index][0]
        return ""

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def load(self, chunks: List[Tuple[str, bytes]]) -> None:
        """Load new chunks and reset to the first one."""
        self.stop()
        self._chunks = list(chunks)
        if self._chunks:
            self._index = 0
            self.chunk_changed.emit(0, self._chunks[0][0])
        else:
            self._index = -1

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def next(self) -> None:
        """Move to the next chunk (clamps at end)."""
        if not self._chunks or self._index < 0:
            return
        self._stop_word_highlight()
        new_idx = self._index + 1
        if new_idx >= len(self._chunks):
            return  # clamped
        self._index = new_idx
        self.chunk_changed.emit(self._index, self._chunks[self._index][0])

    def prev(self) -> None:
        """Move to the previous chunk (clamps at start)."""
        if not self._chunks or self._index < 0:
            return
        self._stop_word_highlight()
        new_idx = self._index - 1
        if new_idx < 0:
            return  # clamped
        self._index = new_idx
        self.chunk_changed.emit(self._index, self._chunks[self._index][0])

    # ------------------------------------------------------------------
    # Speed
    # ------------------------------------------------------------------
    def set_speed(self, speed: float) -> None:
        """Set playback speed (clamped to 0.25–3.0)."""
        clamped = max(_MIN_SPEED, min(_MAX_SPEED, speed))
        self._speed = clamped
        self.speed_changed.emit(clamped)
        if self._is_playing and 0 <= self._index < len(self._chunks):
            sentence, wav_bytes = self._chunks[self._index]
            self._start_word_highlight(sentence, wav_bytes, clamped)

    def set_output_device(self, device_index: Optional[int]) -> None:
        """Override the output device used for playback, or reset to default."""
        self._output_device = None if device_index is None else int(device_index)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def play_current(self) -> None:
        """Play the current chunk through the selected or default audio device."""
        if not self._chunks or self._index < 0:
            return
        sentence, wav_bytes = self._chunks[self._index]
        self._playback_token += 1
        playback_token = self._playback_token
        self._is_playing = True
        speed_snapshot = self._speed
        output_device_snapshot = self._output_device
        self._start_word_highlight(sentence, wav_bytes, speed_snapshot)
        self._play_thread = threading.Thread(
            target=self._play_worker,
            args=(wav_bytes, speed_snapshot, playback_token, output_device_snapshot),
            daemon=True,
        )
        self._play_thread.start()

    def play_all(self) -> None:
        """Play from current chunk to end, auto-advancing."""
        self._auto_advance = True
        self.play_current()

    def stop(self) -> None:
        """Stop any current playback."""
        self._auto_advance = False
        self._stop_word_highlight()
        if self._is_playing:
            self._playback_token += 1
            if sd is not None:
                sd.stop()
            self._is_playing = False

    def _play_worker(
        self,
        wav_bytes: bytes,
        speed: float,
        playback_token: int,
        output_device: Optional[int] = None,
    ) -> None:
        """Background thread: decode WAV and play via sounddevice."""
        try:
            audio_backend = sd
            if audio_backend is None:
                raise RuntimeError("sounddevice is unavailable")
            data, sr = sf.read(io.BytesIO(wav_bytes))
            effective_sr = int(sr * speed)
            audio_backend.play(data, samplerate=effective_sr, device=output_device)
            audio_backend.wait()
        except (RuntimeError, TypeError, ValueError) as exc:
            log.warning("TTS playback error: %s", exc)
            self.playback_error.emit(str(exc))
        finally:
            self._playback_complete.emit(playback_token)

    @pyqtSlot(int)
    def _on_play_complete_for_token(self, playback_token: int) -> None:
        """Ignore stale playback completions from superseded sessions."""
        if playback_token != self._playback_token:
            return
        self._on_play_complete()

    @pyqtSlot()
    def _on_play_complete(self) -> None:
        """Called on the main thread when a chunk finishes playing."""
        self._is_playing = False
        self._stop_word_highlight()

        if self._auto_advance and self._index < len(self._chunks) - 1:
            self.next()
            self.play_current()
        else:
            self._auto_advance = False
            self.playback_finished.emit()

    def _start_word_highlight(self, sentence: str, wav_bytes: bytes, speed: float) -> None:
        self._stop_word_highlight()
        words = sentence.split()
        self._highlight_word_count = len(words)
        if self._highlight_word_count == 0:
            return
        try:
            info = sf.info(io.BytesIO(wav_bytes))
        except (RuntimeError, TypeError, ValueError):
            return
        samplerate = getattr(info, "samplerate", 0)
        frames = getattr(info, "frames", 0)
        if not isinstance(samplerate, (int, float)) or samplerate <= 0:
            return
        if not isinstance(frames, (int, float)) or frames <= 0:
            return
        total_duration_ms = int((frames / samplerate) * 1000 / max(speed, _MIN_SPEED))
        self._highlight_intervals_ms = self._build_word_intervals(words, total_duration_ms)
        self._highlight_word_index = 0
        self.word_highlight.emit(0, self._highlight_word_count)
        if self._highlight_intervals_ms:
            self._highlight_timer.start(self._highlight_intervals_ms[0])

    def _stop_word_highlight(self) -> None:
        self._highlight_timer.stop()
        self._highlight_intervals_ms = []
        self._highlight_word_index = -1
        self._highlight_word_count = 0

    def _build_word_intervals(self, words: List[str], total_duration_ms: int) -> List[int]:
        if len(words) <= 1:
            return []
        clamped_total_ms = max(total_duration_ms, len(words))
        weights = [max(len(word.strip(".,!?;:")), 1) for word in words]
        total_weight = sum(weights)
        raw = [max(1, int(clamped_total_ms * weight / total_weight)) for weight in weights]
        return raw[:-1]

    @pyqtSlot()
    def _advance_word_highlight(self) -> None:
        if self._highlight_word_count <= 1:
            return
        next_index = self._highlight_word_index + 1
        if next_index >= self._highlight_word_count:
            self._stop_word_highlight()
            return
        self._highlight_word_index = next_index
        self.word_highlight.emit(next_index, self._highlight_word_count)
        interval_index = next_index
        if interval_index < len(self._highlight_intervals_ms):
            self._highlight_timer.start(self._highlight_intervals_ms[interval_index])
