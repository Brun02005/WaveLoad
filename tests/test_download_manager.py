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


# --- Enlaces que fallan al validarse -------------------------------------------
# Antes la tarjeta se pintaba de rojo pero no contaba como fallida: el resumen
# decía "0 fallidas", el progreso no llegaba al total y, si fallaban todos, la
# tanda no terminaba nunca.

import pytest  # noqa: E402

from core.download_manager import DownloadManager  # noqa: E402
from storage.session_store import SessionStore  # noqa: E402


@pytest.fixture
def manager(monkeypatch, tmp_path):
    real_init = SessionStore.__init__
    monkeypatch.setattr(
        SessionStore, "__init__",
        lambda self, db_file=None: real_init(self, tmp_path / "session.db"),
    )
    monkeypatch.setattr("core.download_manager.cookie_service.cleanup_session", lambda: None)
    m = DownloadManager()
    m._total_batch = 3
    events = {"finished": [], "progress": [], "batch_finished": 0}
    m.item_finished.connect(lambda i, s, n: events["finished"].append((i, s, n)))
    m.batch_progress.connect(lambda c, t: events["progress"].append((c, t)))
    m.batch_finished.connect(lambda: events.__setitem__("batch_finished", events["batch_finished"] + 1))
    return m, events


def test_a_link_that_fails_validation_counts_as_failed(manager):
    m, events = manager
    m._on_item_validated(
        0, "—", "error",
        "\x1b[0;31mERROR:\x1b[0m [youtube] qruvRVkz_WQ: It was removed following a copyright removal request",
    )
    assert events["finished"] == [(0, "error", "Eliminado de YouTube por un reclamo de copyright.")]
    assert events["progress"] == [(1, 3)]


def test_a_duplicate_is_finished_but_not_as_an_error(manager):
    m, events = manager
    m._on_item_validated(1, "Tema", "duplicado", "Ya existe en la carpeta.")
    assert events["finished"] == [(1, "duplicado", "Ya existe en la carpeta.")]


def test_a_valid_link_is_not_finished_yet(manager):
    m, events = manager
    m._on_item_validated(2, "Tema", "valido", "Listo para descargar.")
    assert events["finished"] == [] and events["progress"] == []


def test_a_batch_where_nothing_is_downloadable_ends(manager):
    m, events = manager
    m._on_batch_validated([])
    assert events["batch_finished"] == 1


def test_the_worker_emits_global_indices(monkeypatch, tmp_path):
    def falla(cls, url):
        raise RuntimeError("This video is not available")
    monkeypatch.setattr(MetadataService, "extract_metadata", classmethod(falla))
    monkeypatch.setattr("core.download_manager.cookie_service.initialize_session", lambda url: None)
    worker = BatchValidationWorker(["https://youtu.be/a", "https://youtu.be/b"], Path(tmp_path), start_index=5)
    indices = []
    worker.signals.item_validated.connect(lambda i, *_: indices.append(i))
    worker.run()
    assert indices == [5, 6]
