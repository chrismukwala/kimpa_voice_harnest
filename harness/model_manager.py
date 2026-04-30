"""Model manager — STT/TTS model presence detection and lazy download.

Wraps huggingface_hub for cache lookups and snapshot downloads so the UI can
show status indicators and trigger first-run downloads with progress updates.

All public functions accept dependency-injection hooks (`_lookup`, `_downloader`)
so the test suite never hits the network.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)

# faster-whisper turbo lives at this HF repo. voice_input.py loads "base.en"
# via the WhisperModel constructor which resolves to Systran/faster-whisper-base.en.
WHISPER_REPO = "Systran/faster-whisper-base.en"

# Kokoro 82M public weights repo.
KOKORO_REPO = "hexgrad/Kokoro-82M"

# Marker file checked for cache presence — present in both repos.
_CACHE_MARKER = "config.json"


ProgressCb = Callable[[str, int, int], None]


# ----------------------------------------------------------------------
# Default loader / downloader implementations
# ----------------------------------------------------------------------
def _default_lookup(repo_id: str, filename: str):
    """Look up *filename* in the local HF cache for *repo_id*.

    Returns the local path string on hit, the cached-no-exist sentinel if
    HF previously fetched a 404, or None if not cached at all.
    """
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    try:
        return try_to_load_from_cache(repo_id=repo_id, filename=filename)
    except (OSError, ValueError) as exc:
        log.debug("HF cache lookup failed for %s/%s: %s", repo_id, filename, exc)
        return None


def _default_no_exist_sentinel():
    """Return huggingface_hub's _CACHED_NO_EXIST sentinel, or a unique object."""
    try:
        from huggingface_hub.constants import _CACHED_NO_EXIST  # type: ignore
        return _CACHED_NO_EXIST
    except ImportError:
        return object()


def _default_downloader(repo_id: str, **kwargs):
    """Wrap huggingface_hub.snapshot_download with progress translation."""
    progress_cb: Optional[ProgressCb] = kwargs.pop("progress_cb", None)
    from huggingface_hub import snapshot_download

    if progress_cb is not None:
        try:
            progress_cb("starting", 0, 0)
        except (RuntimeError, OSError) as exc:
            log.debug("progress_cb raised: %s", exc)

    path = snapshot_download(repo_id=repo_id, **kwargs)

    if progress_cb is not None:
        try:
            progress_cb("done", 1, 1)
        except (RuntimeError, OSError) as exc:
            log.debug("progress_cb raised: %s", exc)
    return path


# ----------------------------------------------------------------------
# Presence checks
# ----------------------------------------------------------------------
def _is_present(
    repo_id: str,
    _lookup: Optional[Callable[[str, str], object]],
    _no_exist_sentinel: Optional[object],
) -> bool:
    lookup = _lookup or _default_lookup
    sentinel = _no_exist_sentinel if _no_exist_sentinel is not None else _default_no_exist_sentinel()
    result = lookup(repo_id, _CACHE_MARKER)
    if result is None:
        return False
    if result is sentinel:
        return False
    return bool(result)


def whisper_present(_lookup=None, _no_exist_sentinel=None) -> bool:
    """Return True if the whisper model is already cached locally."""
    return _is_present(WHISPER_REPO, _lookup, _no_exist_sentinel)


def kokoro_present(_lookup=None, _no_exist_sentinel=None) -> bool:
    """Return True if the Kokoro TTS model is already cached locally."""
    return _is_present(KOKORO_REPO, _lookup, _no_exist_sentinel)


# ----------------------------------------------------------------------
# Downloads
# ----------------------------------------------------------------------
def _download(repo_id: str, progress_cb, _downloader) -> str:
    downloader = _downloader or _default_downloader
    try:
        return downloader(repo_id, progress_cb=progress_cb)
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        raise RuntimeError(f"Failed to download {repo_id}: {exc}") from exc


def download_whisper(progress_cb: Optional[ProgressCb] = None, _downloader=None) -> str:
    """Download the whisper model to the local HF cache. Returns cache path."""
    return _download(WHISPER_REPO, progress_cb, _downloader)


def download_kokoro(progress_cb: Optional[ProgressCb] = None, _downloader=None) -> str:
    """Download the Kokoro model to the local HF cache. Returns cache path."""
    return _download(KOKORO_REPO, progress_cb, _downloader)


# ----------------------------------------------------------------------
# Composite status (used by the UI status panel)
# ----------------------------------------------------------------------
def status(api_key: Optional[str], _lookup=None, _no_exist_sentinel=None) -> dict:
    """Return a {whisper, kokoro, api_key} dict of bool flags."""
    return {
        "whisper": whisper_present(_lookup=_lookup, _no_exist_sentinel=_no_exist_sentinel),
        "kokoro": kokoro_present(_lookup=_lookup, _no_exist_sentinel=_no_exist_sentinel),
        "api_key": bool(api_key),
    }
