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
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThreadPool

from core.event_bus import event_bus, TrackAnalyzedEvent
from domain.repositories.track_repository import TrackRepository
from workers.analysis_worker import AnalysisWorker

logger = logging.getLogger(__name__)


def check_analysis_engine() -> Optional[str]:
    """None si el motor de análisis se puede cargar; si no, el motivo.

    librosa importa numba al cargarse: si falta cualquiera de los dos, cada
    track falla con el mismo error. Se chequea una vez en vez de descubrirlo
    N veces.
    """
    try:
        import librosa  # noqa: F401, PLC0415
    except Exception as exc:  # noqa: BLE001 — ImportError, OSError de DLLs, etc.
        return f"{type(exc).__name__}: {exc}"
    return None


class AnalysisCoordinator(QObject):
    analysis_ready = Signal(str, object)  # track_id, AnalysisResult
    progress = Signal(int, int)           # done, total (total == 0 when idle)
    # El motor no se puede usar: se emite una vez por pedido, no una por track.
    engine_unavailable = Signal(str)      # motivo
    # Resumen de una corrida de librería que terminó con fallos.
    batch_finished = Signal(int, int)     # analizados, fallidos

    def __init__(self, repository: TrackRepository):
        super().__init__()
        self.repository = repository
        self.pool = QThreadPool()
        # Analysis is CPU-bound; keep concurrency modest so it doesn't starve
        # the download/convert pipeline.
        self.pool.setMaxThreadCount(min(2, QThreadPool.globalInstance().maxThreadCount()))
        # Tracks encolados o corriendo: pedir dos veces el mismo track no lanza
        # dos workers escribiendo el ID3 del mismo archivo.
        self._in_flight: set[str] = set()
        # Tracks de la corrida de librería en curso. El progreso cuenta sólo
        # éstos: un análisis suelto (descarga nueva) no lo descuadra.
        self._batch: set[str] = set()
        self._total = 0
        self._done = 0
        self._failed = 0
        self._engine_error: Optional[str] = None
        self._engine_checked = False

    def engine_error(self) -> Optional[str]:
        if not self._engine_checked:
            self._engine_error = check_analysis_engine()
            self._engine_checked = True
            if self._engine_error:
                logger.error("Motor de análisis no disponible: %s", self._engine_error)
        return self._engine_error

    def analyze_track(self, track_id: str, file_path: str) -> bool:
        """Queue analysis for a single track (used for freshly downloaded songs).

        Devuelve False si no se encoló (motor no disponible o ya en curso).
        """
        error = self.engine_error()
        if error:
            self.engine_unavailable.emit(error)
            return False
        return self._start(track_id, file_path)

    def analyze_library(self, tracks, force: bool = False) -> int:
        """Queue analysis for library tracks.

        By default only tracks without analysis are queued; ``force`` re-analyses
        everything (used after an algorithm change to refresh stale values).
        Returns the number of tracks queued.
        """
        error = self.engine_error()
        if error:
            self.engine_unavailable.emit(error)
            return 0

        pending = []
        for track in tracks:
            if track.bpm is not None and not force:
                continue
            track_id = str(track.id)
            if track_id in self._in_flight:
                continue
            path = self._primary_audio_path(track)
            if path:
                pending.append((track_id, path))

        if not pending:
            return 0
        self._batch.update(track_id for track_id, _ in pending)
        self._total += len(pending)
        self.progress.emit(self._done, self._total)
        for track_id, path in pending:
            self._start(track_id, path)
        return len(pending)

    def _start(self, track_id: str, file_path: str) -> bool:
        if track_id in self._in_flight:
            return False
        self._in_flight.add(track_id)
        worker = AnalysisWorker(track_id, file_path)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self.pool.start(worker)
        return True

    def _on_finished(self, track_id: str, result):
        try:
            self.repository.save_analysis(
                uuid.UUID(track_id), result.bpm, result.key_camelot, result.energy
            )
        except Exception as e:
            logger.error(f"Failed to persist analysis for {track_id}: {e}")
        else:
            # Only announce an analysis that actually made it to the database.
            # The derived tags are rebuilt from this event; emitting it after a
            # failed save would tag a track with values nobody can read back.
            event_bus.emit(
                TrackAnalyzedEvent(
                    track_id=track_id,
                    bpm=result.bpm,
                    key_camelot=result.key_camelot,
                    energy=result.energy,
                )
            )
        self._advance(track_id, failed=False)
        self.analysis_ready.emit(track_id, result)

    def _on_failed(self, track_id: str, error: str):
        self._advance(track_id, failed=True)

    def _advance(self, track_id: str, failed: bool):
        self._in_flight.discard(track_id)
        if track_id not in self._batch:
            return
        self._batch.discard(track_id)
        self._done += 1
        if failed:
            self._failed += 1
        self.progress.emit(self._done, self._total)
        if not self._batch:
            ok, bad = self._done - self._failed, self._failed
            self._total = self._done = self._failed = 0
            self.progress.emit(0, 0)
            if bad:
                self.batch_finished.emit(ok, bad)

    @staticmethod
    def _primary_audio_path(track):
        for asset in track.assets:
            if asset.asset_type.name.startswith("AUDIO"):
                return str(asset.file_path)
        return None
