from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from core.state_machine import DownloadState

@dataclass
class DownloadItem:
    """A single, transient download task in the queue.

    Carries queue state, progress, retries and temp paths — it lives only while
    a download is in flight. The persistent library counterpart is
    ``domain.track.Track``; the two are bridged by ``TrackDownloadedEvent`` and
    are deliberately kept separate.
    """
    id: str                 # Unique ID, can be the URL or a hash
    url: str                # YouTube or supported URL
    title: str              # Title of the media
    output_dir: Path        # Base output directory
    state: DownloadState = DownloadState.QUEUED
    
    # Metadata
    uploader: Optional[str] = None
    thumbnail_url: Optional[str] = None
    year: Optional[str] = None
    duration: int = 0
    
    # Progress
    progress_text: str = ""
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    
    # Paths
    final_mp3_path: Optional[Path] = None
    temp_download_path: Optional[Path] = None
    
    # Scheduling
    last_active_time: float = 0.0

    def update_state(self, new_state: DownloadState, message: str = ""):
        from core.state_machine import StateMachine
        StateMachine.validate_transition(self.state, new_state)
        self.state = new_state
        if message:
            self.progress_text = message
