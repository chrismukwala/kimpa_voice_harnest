"""TTS — Kokoro text-to-speech adapter."""

import re
import io
import threading
import wave
from typing import List, Tuple

import numpy as np
import soundfile as sf


# Lazy singleton for Kokoro pipeline — avoids reloading the 82M model every call.
_pipeline_lock = threading.Lock()
_pipeline = None


def _get_pipeline():
    """Return the shared KPipeline instance, creating it on first call."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                from kokoro import KPipeline
                _pipeline = KPipeline(lang_code="a")
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
        generator = pipeline(sentence, voice="af_heart")
        audio_chunks = []
        sample_rate = 24000
        for _, _, audio in generator:
            audio_chunks.append(audio)
            # sample rate comes from the pipeline, usually 24000
        if not audio_chunks:
            continue
        combined = np.concatenate(audio_chunks)
        buf = io.BytesIO()
        sf.write(buf, combined, sample_rate, format="WAV")
        results.append((sentence, buf.getvalue()))

    return results


def play_wav_bytes(wav_bytes: bytes):
    """Play a WAV buffer through the default audio device."""
    import sounddevice as sd

    data, sr = sf.read(io.BytesIO(wav_bytes))
    sd.play(data, sr)
    sd.wait()
