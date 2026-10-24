from abc import ABC, abstractmethod
from typing import Optional, List
import uuid
from domain.track import Track

class TrackRepository(ABC):
    """
    Abstract Base Class defining the contract for Track persistence.
    This separates the domain logic from the storage implementation (e.g. SQLite).
    """

    @abstractmethod
    def save(self, track: Track) -> None:
        """
        Saves a new track or updates an existing one, along with its assets.
        """
        pass

    @abstractmethod
    def get_by_id(self, track_id: uuid.UUID) -> Optional[Track]:
        """
        Retrieves a track by its UUID.
        """
        pass

    @abstractmethod
    def get_all(self) -> List[Track]:
        """
        Retrieves all tracks in the library.
        """
        pass

    @abstractmethod
    def get_by_ids(self, track_ids: List[str]) -> List[Track]:
        """
        Retrieves the given tracks, preserving the order of ``track_ids``.

        This is what a Collections result page needs: the query engine returns
        an ordered list of ids and the UI has to show them in that order. Ids
        that no longer exist are skipped, not reported as an error.
        """
        pass

    @abstractmethod
    def delete(self, track_id: uuid.UUID) -> bool:
        """
        Deletes a track and its associated assets from persistence.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def delete_many(self, track_ids: List[str]) -> int:
        """
        Deletes several tracks (and everything that hangs from them) in a
        single transaction. Returns how many were deleted.
        """
        pass

    @abstractmethod
    def update_audio_path(self, track_id: str, new_path: str) -> bool:
        """
        Points a track's audio asset at a new location (the file was moved).
        Raises ValueError if that path already belongs to another track.
        """
        pass

    @abstractmethod
    def exists_by_path(self, file_path: str) -> bool:
        """
        Checks if a track asset with the given file path already exists.
        Used for deduplication during import.
        """
        pass

    @abstractmethod
    def save_analysis(self, track_id: uuid.UUID, bpm: float, key_camelot: str, energy: int) -> None:
        """
        Persists the musical analysis (BPM / key / energy) for a track.
        """
        pass
