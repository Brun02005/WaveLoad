"""
workers/analysis_worker.py
==========================
Background worker that runs the (CPU-bound) musical analysis for a single
track off the UI thread, and writes BPM/key into the file's ID3 tags so
external DJ tools (Rekordbox, Serato, Traktor) pick them up on import.
"""

import logging
import traceback
from pathlib import Path

from PySide6.QtCore import QRunnable, QObject, Signal

from services.analysis_service import AnalysisService, AnalysisResult

logger = logging.getLogger(__name__)


class AnalysisWorkerSignals(QObject):
    finished = Signal(str, object)  # track_id, AnalysisResult
    failed = Signal(str, str)       # track_id, error_message


class AnalysisWorker(QRunnable):
    def __init__(self, track_id: str, file_path: str):
        super().__init__()
        self.track_id = track_id
        self.file_path = Path(file_path)
        self.signals = AnalysisWorkerSignals()

    def run(self):
        try:
            result = AnalysisService.analyze_file(self.file_path)
            self._write_id3_tags(result)
            self.signals.finished.emit(self.track_id, result)
        except Exception as e:
            logger.error(f"Analysis failed for {self.file_path.name}: {e}")
            logger.debug(traceback.format_exc())
            self.signals.failed.emit(self.track_id, str(e))

    def _write_id3_tags(self, result: AnalysisResult):
        """Embed TBPM/TKEY so DJ software reads the analysis. Best-effort."""
        try:
            from mutagen.id3 import ID3, TBPM, TKEY, ID3NoHeaderError  # noqa: PLC0415
            if self.file_path.suffix.lower() != ".mp3":
                return
            try:
                tags = ID3(str(self.file_path))
            except ID3NoHeaderError:
                tags = ID3()
            tags.setall("TBPM", [TBPM(encoding=3, text=str(round(result.bpm)))])
            tags.setall("TKEY", [TKEY(encoding=3, text=result.key_camelot)])
            tags.save(str(self.file_path))
        except Exception as e:
            logger.debug(f"Could not write ID3 BPM/key for {self.file_path.name}: {e}")
