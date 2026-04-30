"""Tests for harness.model_manager — STT/TTS model presence + lazy download."""

import pytest

from harness import model_manager


# ----------------------------------------------------------------------
# Presence checks
# ----------------------------------------------------------------------
def test_whisper_present_returns_true_when_cache_lookup_returns_path(tmp_path):
    """If the cache lookup yields a real path, model is present."""
    fake_path = tmp_path / "config.json"
    fake_path.write_text("{}")

    def fake_lookup(repo_id, filename):
        assert repo_id == model_manager.WHISPER_REPO
        return str(fake_path)

    assert model_manager.whisper_present(_lookup=fake_lookup) is True


def test_whisper_present_returns_false_when_lookup_returns_none():
    def fake_lookup(repo_id, filename):
        return None

    assert model_manager.whisper_present(_lookup=fake_lookup) is False


def test_whisper_present_returns_false_for_cached_no_exist_sentinel():
    """huggingface_hub sentinel for cached-not-existent must be treated as absent."""
    sentinel = object()

    def fake_lookup(repo_id, filename):
        return sentinel

    assert (
        model_manager.whisper_present(_lookup=fake_lookup, _no_exist_sentinel=sentinel)
        is False
    )


def test_kokoro_present_returns_true_when_cache_lookup_returns_path(tmp_path):
    fake_path = tmp_path / "config.json"
    fake_path.write_text("{}")

    def fake_lookup(repo_id, filename):
        assert repo_id == model_manager.KOKORO_REPO
        return str(fake_path)

    assert model_manager.kokoro_present(_lookup=fake_lookup) is True


def test_kokoro_present_returns_false_when_lookup_returns_none():
    def fake_lookup(repo_id, filename):
        return None

    assert model_manager.kokoro_present(_lookup=fake_lookup) is False


# ----------------------------------------------------------------------
# Downloads
# ----------------------------------------------------------------------
def test_download_whisper_invokes_snapshot_download_for_correct_repo():
    calls = {}

    def fake_download(repo_id, **kwargs):
        calls["repo_id"] = repo_id
        calls["kwargs"] = kwargs
        return "/fake/path"

    result = model_manager.download_whisper(_downloader=fake_download)

    assert calls["repo_id"] == model_manager.WHISPER_REPO
    assert result == "/fake/path"


def test_download_kokoro_invokes_snapshot_download_for_correct_repo():
    calls = {}

    def fake_download(repo_id, **kwargs):
        calls["repo_id"] = repo_id
        return "/fake/kokoro"

    result = model_manager.download_kokoro(_downloader=fake_download)

    assert calls["repo_id"] == model_manager.KOKORO_REPO
    assert result == "/fake/kokoro"


def test_download_whisper_propagates_progress_callback():
    """Progress callback must be reachable from caller."""
    progress_log = []

    def fake_download(repo_id, **kwargs):
        # Simulate the downloader emitting progress.
        cb = kwargs.get("progress_cb")
        if cb is not None:
            cb("downloading", 0, 100)
            cb("downloading", 50, 100)
            cb("done", 100, 100)
        return "/fake"

    def progress(stage, current, total):
        progress_log.append((stage, current, total))

    model_manager.download_whisper(progress_cb=progress, _downloader=fake_download)

    assert progress_log == [
        ("downloading", 0, 100),
        ("downloading", 50, 100),
        ("done", 100, 100),
    ]


def test_download_whisper_wraps_network_errors_as_runtime_error():
    def fake_download(repo_id, **kwargs):
        raise OSError("network unreachable")

    with pytest.raises(RuntimeError, match="network unreachable"):
        model_manager.download_whisper(_downloader=fake_download)


# ----------------------------------------------------------------------
# Convenience
# ----------------------------------------------------------------------
def test_status_summary_returns_dict_with_all_three_flags():
    """status() returns {whisper: bool, kokoro: bool, api_key: bool}."""

    def fake_lookup(repo_id, filename):
        return None  # both absent

    summary = model_manager.status(api_key=None, _lookup=fake_lookup)
    assert summary == {"whisper": False, "kokoro": False, "api_key": False}


def test_status_reports_api_key_present_when_non_empty():
    def fake_lookup(repo_id, filename):
        return None

    summary = model_manager.status(api_key="abc123", _lookup=fake_lookup)
    assert summary["api_key"] is True
