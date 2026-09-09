"""Regression tests for BatchValidationWorker's id/url split.

A Spotify link is resolved to a YouTube URL during validation. The item's
``url`` must become the resolved URL (that's what yt-dlp downloads), while
``id`` must stay the ORIGINAL pasted URL — DownloadManager._url_to_index is
keyed by the pasted URL, so swapping both would silently orphan every
progress/completion signal for resolved downloads.
"""

from pathlib import Path

from core.download_manager import BatchValidationWorker
from services.metadata_service import MetadataService

SPOTIFY_URL = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"
RESOLVED_URL = "https://www.youtube.com/watch?v=resolved123"


def _run_worker(monkeypatch, tmp_path, metadata):
    monkeypatch.setattr(MetadataService, "extract_metadata", classmethod(lambda cls, url: metadata))
    monkeypatch.setattr(
        "core.download_manager.cookie_service.initialize_session", lambda url: None
    )

    worker = BatchValidationWorker([SPOTIFY_URL], Path(tmp_path))
    captured = []
    worker.signals.batch_ready.connect(captured.append)
    worker.run()
    return captured[0] if captured else []


def test_resolved_url_is_downloaded_but_id_stays_original(monkeypatch, tmp_path):
    items = _run_worker(monkeypatch, tmp_path, {
        "url": RESOLVED_URL,
        "is_playlist": False,
        "title": "The Weeknd - Blinding Lights",
        "duration": 200,
    })

    assert len(items) == 1
    assert items[0].id == SPOTIFY_URL
    assert items[0].url == RESOLVED_URL


def test_url_falls_back_to_original_when_metadata_has_none(monkeypatch, tmp_path):
    items = _run_worker(monkeypatch, tmp_path, {
        "is_playlist": False,
        "title": "Some Track",
        "duration": 100,
    })

    assert len(items) == 1
    assert items[0].id == SPOTIFY_URL
    assert items[0].url == SPOTIFY_URL
