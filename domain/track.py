from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from pathlib import Path
from enum import Enum, auto
from typing import List, Optional

class AssetType(Enum):
    """Type of a file/data asset associated with a library Track."""
    AUDIO_MP3 = auto()
    AUDIO_WAV = auto()
    AUDIO_FLAC = auto()
    THUMBNAIL = auto()

@dataclass
class TrackAsset:
    """
    Represents a specific physical or logical file/data asset belonging to a Track.
    """
    id: uuid.UUID
    track_id: uuid.UUID
    asset_type: AssetType
    file_path: Path
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class Track:
    """The aggregate root representing a music entity in the user's library.

    This is the *persistent* library model. It is intentionally separate from
    ``domain.models.DownloadItem`` (the *transient* download-queue task): a
    DownloadItem lives only for the duration of a download and carries queue
    state/progress/retries, whereas a Track is the permanent library entry and
    is decoupled from how it was fetched. The bridge between them is
    ``TrackDownloadedEvent`` (emitted on successful post-processing), which
    ``TrackService`` turns into a Track. Do not merge the two.
    """
    id: uuid.UUID
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Source metadata — preserves provenance for future Collection features
    source_platform: Optional[str] = None       # e.g. "youtube", "spotify", "local"
    source_playlist_name: Optional[str] = None   # e.g. "Summer Vibes 2025"
    source_playlist_id: Optional[str] = None     # e.g. YouTube playlist ID
    source_url: Optional[str] = None             # e.g. original URL

    # Musical analysis (populated by the AnalysisService; None until analysed)
    bpm: Optional[float] = None                  # beats per minute
    key_camelot: Optional[str] = None            # Camelot code, e.g. "8A"
    energy: Optional[int] = None                 # coarse 1..10

    # Internal list of assets associated with this track
    assets: List[TrackAsset] = field(default_factory=list)

    def add_asset(self, asset: TrackAsset):
        if asset.track_id != self.id:
            raise ValueError("Asset does not belong to this track.")
        self.assets.append(asset)
        self.updated_at = datetime.now(timezone.utc)
