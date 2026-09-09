import logging
import uuid
from pathlib import Path
from typing import List
from PySide6.QtCore import QRunnable, QObject, Signal

from domain.track import Track, TrackAsset, AssetType
from domain.repositories.track_repository import TrackRepository
from core.event_bus import event_bus, TrackCreatedEvent

logger = logging.getLogger(__name__)

class ImportWorkerSignals(QObject):
    progress = Signal(int, int, str)  # current, total, text
    finished = Signal(dict)           # summary statistics

class ImportWorker(QRunnable):
    """
    Background worker that extracts metadata and persists Track entities
    without freezing the UI or modifying the original files.
    """
    def __init__(self, file_paths: List[Path], repository: TrackRepository):
        super().__init__()
        self.file_paths = file_paths
        self.repository = repository
        self.signals = ImportWorkerSignals()
        self._cancelled = False
        
        self.stats = {
            "discovered": len(file_paths),
            "supported": 0,
            "imported": 0,
            "skipped": 0,
            "unsupported": 0,
            "failed": 0
        }

    def cancel(self):
        self._cancelled = True

    def run(self):
        logger.info(f"Starting ImportWorker for {len(self.file_paths)} files")
        
        for idx, file_path in enumerate(self.file_paths):
            if self._cancelled:
                logger.info("ImportWorker cancelled.")
                break

            self.signals.progress.emit(idx + 1, self.stats["discovered"], f"Procesando: {file_path.name}")
            
            # Check duplicate (fast path)
            if self.repository.exists_by_path(str(file_path)):
                self.stats["skipped"] += 1
                continue
                
            try:
                # Metadata extraction
                track_entity = self._extract_metadata(file_path)
                if not track_entity:
                    self.stats["unsupported"] += 1
                    continue
                    
                self.stats["supported"] += 1
                
                # Persist
                self.repository.save(track_entity)
                self.stats["imported"] += 1
                
                # Emit event to trigger Library UI update
                event_bus.emit(TrackCreatedEvent(track=track_entity))
                
            except Exception as e:
                logger.error(f"Failed to import {file_path}: {e}")
                self.stats["failed"] += 1
                
        self.signals.finished.emit(self.stats)

    def _extract_metadata(self, file_path: Path) -> Track:
        """
        Uses mutagen to safely read audio tags in read-only mode.
        If mutagen is not installed, gracefully falls back to basic file information.
        Returns a populated Track entity or None if unsupported.
        """
        # Default values
        title = file_path.stem
        artist = "Unknown"
        album = "Unknown"
        duration = 0

        try:
            import mutagen
            audio = mutagen.File(file_path, easy=True)
            if audio is not None:
                # Extract tags safely
                if hasattr(audio, "tags") and audio.tags:
                    title = audio.tags.get("title", [title])[0]
                    artist = audio.tags.get("artist", [artist])[0]
                    album = audio.tags.get("album", [album])[0]
                    
                if hasattr(audio, "info") and audio.info:
                    duration = int(getattr(audio.info, "length", 0))
        except ImportError:
            logger.warning("Mutagen no está instalado. Fallback a metadatos básicos basados en el archivo.")
        except Exception as e:
            logger.warning(f"Error leyendo metadatos con mutagen para {file_path}: {e}")
            # Continue with default basic metadata rather than failing completely
                
        # Create domain entity
        track = Track(
            id=uuid.uuid4(),
            title=title,
            artist=artist,
            album=album,
            duration=duration,
            source_platform="local",
            source_url=str(file_path)
        )
        
        # Determine AssetType based on extension
        ext = file_path.suffix.lower()
        asset_type = AssetType.AUDIO_MP3
        if ext == ".flac":
            asset_type = AssetType.AUDIO_FLAC
        elif ext in [".wav", ".aiff"]:
            asset_type = AssetType.AUDIO_WAV
            
        # Create primary asset linking to original file
        asset = TrackAsset(
            id=uuid.uuid4(),
            track_id=track.id,
            asset_type=asset_type,
            file_path=file_path
        )
        track.add_asset(asset)
        
        return track
