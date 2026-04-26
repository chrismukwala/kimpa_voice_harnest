"""TTS — Kokoro text-to-speech adapter."""

import re
import io
import logging
import threading
from typing import Generator, Iterator, List, Tuple

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)


# Run Kokoro on GPU if available, otherwise fall back to CPU.
try:
    import torch as _torch
    TTS_DEVICE = "cuda" if _torch.cuda.is_available() else "cpu"
except ImportError:
    TTS_DEVICE = "cpu"

# Lazy singleton for Kokoro pipeline — avoids reloading the 82M model every call.
_pipeline_lock = threading.Lock()
_synthesis_lock = threading.Lock()
_pipeline = None


def _get_pipeline():
    """Return the shared KPipeline instance, creating it on first call."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                from kokoro import KPipeline
                _pipeline = KPipeline(lang_code="a", device=TTS_DEVICE)
    return _pipeline


def _split_sentences(text: str) -> list[str]:
    """Crude sentence splitter for spoken prose."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def speak(text: str) -> List[Tuple[str, bytes]]:
    """Convert *text* to a list of (sentence, wav_bytes) pairs.

    Each wav_bytes is a complete WAV file in memory.
    Phase 4 adds arrow-key navigation over this list.
    """
    pipeline = _get_pipeline()
    sentences = _split_sentences(text)
    if not sentences:
        return []

    results: List[Tuple[str, bytes]] = []
    for sentence in sentences:
        wav_bytes = _synthesize_sentence(pipeline, sentence)
        if wav_bytes is not None:
            results.append((sentence, wav_bytes))

    return results


def speak_stream(sentences: Iterator[str]) -> Generator[Tuple[str, bytes], None, None]:
    """Yield (sentence, wav_bytes) one at a time from an iterator of sentences.

    Unlike speak(), this processes each sentence as it arrives, enabling
    playback to start while the LLM is still generating.
    """
    pipeline = _get_pipeline()
    for sentence in sentences:
        if not sentence or not sentence.strip():
            continue
        wav_bytes = _synthesize_sentence(pipeline, sentence)
        if wav_bytes is not None:
            yield (sentence, wav_bytes)


def _synthesize_sentence(pipeline, sentence: str) -> bytes | None:
    """Return WAV bytes for one sentence, or None if synthesis fails."""
    try:
        with _synthesis_lock:
            generator = pipeline(sentence, voice="af_heart")
            audio_chunks = []
            sample_rate = 24000
            for _, _, audio in generator:
                audio_chunks.append(audio)
        if not audio_chunks:
            return None
        combined = np.concatenate(audio_chunks)
        if combined.ndim != 1:
            raise ValueError("Expected mono audio from Kokoro")
        buf = io.BytesIO()
        sf.write(buf, combined, sample_rate, format="WAV")
        return buf.getvalue()
    except (RuntimeError, OSError, ValueError) as exc:
        log.warning("Skipping TTS sentence after synthesis failure: %s", exc)
        return None


def play_wav_bytes(wav_bytes: bytes):
    """Play a WAV buffer through the default audio device."""
    import sounddevice as sd

    data, sr = sf.read(io.BytesIO(wav_bytes))
    sd.play(data, sr)
    sd.wait()
