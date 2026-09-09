"""
application/analysis_coordinator.py
===================================
Orchestrates background musical analysis (BPM / key / energy) across a bounded
thread pool: runs AnalysisWorkers, persists their results, and reports progress.

Lives on the main (UI) thread so workers and their signals have correct thread
affinity. It knows nothing about presentation — it emits ``analysis_ready`` and
the UI layer maps the updated Track for display.
"""

import logging
import uuid

from PySide6.QtCore import QObject, Signal, QThreadPool

from domain.repositories.track_repository import TrackRepository
from workers.analysis_worker import AnalysisWorker

logger = logging.getLogger(__name__)


class AnalysisCoordinator(QObject):
    analysis_ready = Signal(str, object)  # track_id, AnalysisResult
    progress = Signal(int, int)           # done, total (total == 0 when idle)

    def __init__(self, repository: TrackRepository):
        super().__init__()
        self.repository = repository
        self.pool = QThreadPool()
        # Analysis is CPU-bound; keep concurrency modest so it doesn't starve
        # the download/convert pipeline.
        self.pool.setMaxThreadCount(min(2, QThreadPool.globalInstance().maxThreadCount()))
        self._total = 0
        self._done = 0

    def analyze_track(self, track_id: str, file_path: str):
        """Queue analysis for a single track (used for freshly downloaded songs)."""
        worker = AnalysisWorker(track_id, file_path)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self.pool.start(worker)

    def analyze_library(self, tracks, force: bool = False) -> int:
        """Queue analysis for library tracks.

        By default only tracks without analysis are queued; ``force`` re-analyses
        everything (used after an algorithm change to refresh stale values).
        Returns the number of tracks queued.
        """
        pending = []
        for track in tracks:
            if track.bpm is not None and not force:
                continue
            path = self._primary_audio_path(track)
            if path:
                pending.append((str(track.id), path))

        self._total = len(pending)
        self._done = 0
        self.progress.emit(self._done, self._total)
        for track_id, path in pending:
            self.analyze_track(track_id, path)
        return len(pending)

    def _on_finished(self, track_id: str, result):
        try:
            self.repository.save_analysis(
                uuid.UUID(track_id), result.bpm, result.key_camelot, result.energy
            )
        except Exception as e:
            logger.error(f"Failed to persist analysis for {track_id}: {e}")
        self._advance()
        self.analysis_ready.emit(track_id, result)

    def _on_failed(self, track_id: str, error: str):
        self._advance()

    def _advance(self):
        if self._total:
            self._done += 1
            self.progress.emit(self._done, self._total)
            if self._done >= self._total:
                self._total = 0
                self._done = 0

    @staticmethod
    def _primary_audio_path(track):
        for asset in track.assets:
            if asset.asset_type.name.startswith("AUDIO"):
                return str(asset.file_path)
        return None
