import logging
import uuid
from pathlib import Path

from core.event_bus import event_bus, TrackDownloadedEvent, TrackCreatedEvent
from domain.track import Track, TrackAsset, AssetType
from domain.repositories.track_repository import TrackRepository
from storage.sqlite_track_repository import SqliteTrackRepository

logger = logging.getLogger(__name__)

class TrackService:
    """
    Orchestrates Track creation, updates, and lifecycle management.
    Acts as the bridge between the EventBus and the TrackRepository.
    """
    def __init__(self, repository: TrackRepository):
        self.repository = repository
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        """Registers handlers to the application event bus."""
        event_bus.subscribe(TrackDownloadedEvent, self.handle_track_downloaded)

    def handle_track_downloaded(self, event: TrackDownloadedEvent):
        """
        Handler for TrackDownloadedEvent.
        Creates a new Track and its primary audio asset, then persists it.
        """
        logger.info(f"TrackService processing downloaded track: {event.title}")
        
        try:
            # Check for duplicate path before attempting to save
            if self.repository.exists_by_path(event.final_mp3_path):
                logger.warning(f"Track already exists in repository, skipping: {event.final_mp3_path}")
                return
                
            track = Track(
                id=uuid.uuid4(),
                title=event.title,
                artist=event.uploader,
                duration=event.duration,
                source_platform="youtube",
                source_url=event.item_id
                # Note: 'year' from event could be mapped to 'album' or a new field later
            )

            # Create primary MP3 asset
            mp3_asset = TrackAsset(
                id=uuid.uuid4(),
                track_id=track.id,
                asset_type=AssetType.AUDIO_MP3,
                file_path=Path(event.final_mp3_path)
            )
            track.add_asset(mp3_asset)

            # Persist to repository
            self.repository.save(track)
            logger.info(f"Successfully created and persisted Track {track.id}")

            # Notify listeners (e.g. the library UI) that a new Track exists.
            event_bus.emit(TrackCreatedEvent(track=track))

        except Exception as e:
            logger.error(f"TrackService failed to process downloaded track '{event.title}': {e}")
