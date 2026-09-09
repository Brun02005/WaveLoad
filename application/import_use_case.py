import logging
import os
from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import QThreadPool

from domain.repositories.track_repository import TrackRepository
from workers.import_worker import ImportWorker, ImportWorkerSignals

logger = logging.getLogger(__name__)

class ImportUseCase:
    """
    Orchestrates the discovery of audio files and kicks off the background import worker.
    Designed to be reusable for future Folder Monitoring features.
    """
    SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aiff"}

    def __init__(self, repository: TrackRepository):
        self.repository = repository
        self.thread_pool = QThreadPool.globalInstance()

    def execute(self, paths: List[str]) -> Optional[ImportWorkerSignals]:
        """
        Discovers files from the provided paths (files or directories)
        and starts the background import process.
        Returns the signals object so the UI can listen to progress.
        """
        discovered_files = self._discover_files(paths)
        if not discovered_files:
            logger.info("No supported audio files discovered.")
            return None
            
        worker = ImportWorker(discovered_files, self.repository)
        self.thread_pool.start(worker)
        
        return worker.signals

    def _discover_files(self, paths: List[str]) -> List[Path]:
        """Recursively scans paths and filters for supported audio files."""
        discovered = []
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                continue
                
            if path.is_file():
                if path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    discovered.append(path)
            elif path.is_dir():
                for root, _, files in os.walk(path):
                    for file in files:
                        file_path = Path(root) / file
                        if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                            discovered.append(file_path)
                            
        return discovered
