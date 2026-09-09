import uuid
import logging
from typing import Optional, List
from datetime import datetime, timezone
from pathlib import Path

from domain.track import Track, TrackAsset, AssetType
from domain.repositories.track_repository import TrackRepository
from infrastructure.database import DatabaseManager, get_db_manager

logger = logging.getLogger(__name__)

class SqliteTrackRepository(TrackRepository):
    """
    SQLite implementation of the TrackRepository domain contract.
    Operates on the new waveload_library.db initialized via DatabaseManager.
    """

    def __init__(self, db: "DatabaseManager | None" = None):
        # Inyectable: los tests pasan un DatabaseManager sobre una DB temporal.
        # Sin argumento usa la librería real (construida perezosamente).
        self.db = db or get_db_manager()

    def save(self, track: Track) -> None:
        """Saves a track and its associated assets."""
        try:
            with self.db.get_connection() as conn:
                # Upsert track
                conn.execute(
                    '''
                    INSERT INTO tracks (id, title, artist, album, duration, created_at, updated_at,
                                        source_platform, source_playlist_name, source_playlist_id, source_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        artist=excluded.artist,
                        album=excluded.album,
                        duration=excluded.duration,
                        updated_at=excluded.updated_at,
                        source_platform=excluded.source_platform,
                        source_playlist_name=excluded.source_playlist_name,
                        source_playlist_id=excluded.source_playlist_id,
                        source_url=excluded.source_url
                    ''',
                    (
                        str(track.id), track.title, track.artist, track.album, 
                        track.duration, track.created_at.isoformat(), track.updated_at.isoformat(),
                        track.source_platform, track.source_playlist_name, 
                        track.source_playlist_id, track.source_url
                    )
                )

                # Upsert assets (simplest approach: delete and re-insert for updates to collections)
                # Since assets are immutable or uniquely identifiable, we can do direct insert/updates
                for asset in track.assets:
                    conn.execute(
                        '''
                        INSERT INTO track_assets (id, track_id, asset_type, file_path, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            file_path=excluded.file_path,
                            updated_at=excluded.updated_at
                        ''',
                        (
                            str(asset.id), str(asset.track_id), asset.asset_type.name, 
                            str(asset.file_path), asset.created_at.isoformat(), asset.updated_at.isoformat()
                        )
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save Track {track.id}: {e}")
            raise

    def get_by_id(self, track_id: uuid.UUID) -> Optional[Track]:
        """Retrieves a track by its UUID."""
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    "SELECT t.*, a.bpm AS a_bpm, a.musical_key AS a_key, a.energy_level AS a_energy "
                    "FROM tracks t LEFT JOIN track_analysis a ON a.track_id = t.id WHERE t.id = ?",
                    (str(track_id),)
                ).fetchone()
                if not row:
                    return None

                track = self._row_to_track(row)

                # Load assets
                asset_rows = conn.execute("SELECT * FROM track_assets WHERE track_id = ?", (str(track_id),)).fetchall()
                for a_row in asset_rows:
                    track.assets.append(self._row_to_asset(a_row))

                return track
        except Exception as e:
            logger.error(f"Failed to get Track {track_id}: {e}")
            return None

    def get_all(self) -> List[Track]:
        """Retrieves all tracks in the library."""
        tracks = []
        try:
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    "SELECT t.*, a.bpm AS a_bpm, a.musical_key AS a_key, a.energy_level AS a_energy "
                    "FROM tracks t LEFT JOIN track_analysis a ON a.track_id = t.id"
                ).fetchall()
                for row in rows:
                    track = self._row_to_track(row)
                    
                    # Load assets
                    asset_rows = conn.execute("SELECT * FROM track_assets WHERE track_id = ?", (str(track.id),)).fetchall()
                    for a_row in asset_rows:
                        track.assets.append(self._row_to_asset(a_row))
                        
                    tracks.append(track)
            return tracks
        except Exception as e:
            logger.error(f"Failed to get all Tracks: {e}")
            return []

    def get_by_ids(self, track_ids: List[str]) -> List[Track]:
        """Retrieves the given tracks, preserving the order of ``track_ids``.

        One query for the tracks and one for their assets, then reassembled in
        Python: a page of a Collections result is a few hundred ids, and doing
        a round trip per track is how a grid ends up feeling slow.
        """
        wanted = [str(track_id) for track_id in track_ids]
        if not wanted:
            return []

        by_id: dict[str, Track] = {}
        try:
            with self.db.get_connection() as conn:
                # SQLite tops out around 32k host parameters; a result page is
                # far below that, but chunking keeps it honest for a "select all".
                for start in range(0, len(wanted), 900):
                    chunk = wanted[start:start + 900]
                    placeholders = ",".join("?" * len(chunk))
                    rows = conn.execute(
                        "SELECT t.*, a.bpm AS a_bpm, a.musical_key AS a_key, "
                        "a.energy_level AS a_energy "
                        "FROM tracks t LEFT JOIN track_analysis a ON a.track_id = t.id "
                        f"WHERE t.id IN ({placeholders})",
                        chunk,
                    ).fetchall()
                    for row in rows:
                        track = self._row_to_track(row)
                        by_id[str(track.id)] = track

                    asset_rows = conn.execute(
                        f"SELECT * FROM track_assets WHERE track_id IN ({placeholders})",
                        chunk,
                    ).fetchall()
                    for a_row in asset_rows:
                        owner = by_id.get(str(a_row["track_id"]))
                        if owner is not None:
                            owner.assets.append(self._row_to_asset(a_row))
        except Exception as e:
            logger.error(f"Failed to get Tracks by ids: {e}")
            return []

        # Ids that no longer exist simply do not appear; the caller asked for a
        # page of a query result, not for a guarantee that nothing changed.
        return [by_id[track_id] for track_id in wanted if track_id in by_id]

    def delete(self, track_id: uuid.UUID) -> bool:
        """Deletes a track and its associated assets."""
        try:
            with self.db.get_connection() as conn:
                # Deletion of assets handles via ON DELETE CASCADE in schema
                cursor = conn.execute("DELETE FROM tracks WHERE id = ?", (str(track_id),))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete Track {track_id}: {e}")
            return False

    def exists_by_path(self, file_path: str) -> bool:
        """Checks if a track asset with the given file path already exists."""
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT id FROM track_assets WHERE file_path = ?", (file_path,)).fetchone()
                return row is not None
        except Exception as e:
            logger.error(f"Failed to check existence of {file_path}: {e}")
            return False

    def save_analysis(self, track_id: uuid.UUID, bpm: float, key_camelot: str, energy: int) -> None:
        """Upserts the musical analysis for a track into the track_analysis table."""
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    '''
                    INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level, analyzed_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(track_id) DO UPDATE SET
                        bpm=excluded.bpm,
                        musical_key=excluded.musical_key,
                        energy_level=excluded.energy_level,
                        analyzed_at=excluded.analyzed_at
                    ''',
                    (str(track_id), bpm, key_camelot, energy,
                     datetime.now(timezone.utc).isoformat())
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save analysis for Track {track_id}: {e}")
            raise

    def _row_to_track(self, row) -> Track:
        # Check if the row contains the new source columns (handles older schema state before migration)
        keys = row.keys()
        has_source = 'source_platform' in keys
        has_analysis = 'a_bpm' in keys

        return Track(
            id=uuid.UUID(row['id']),
            title=row['title'],
            artist=row['artist'],
            album=row['album'],
            duration=row['duration'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            source_platform=row['source_platform'] if has_source else None,
            source_playlist_name=row['source_playlist_name'] if has_source else None,
            source_playlist_id=row['source_playlist_id'] if has_source else None,
            source_url=row['source_url'] if has_source else None,
            bpm=row['a_bpm'] if has_analysis else None,
            key_camelot=row['a_key'] if has_analysis else None,
            energy=row['a_energy'] if has_analysis else None,
        )

    def _row_to_asset(self, row) -> TrackAsset:
        return TrackAsset(
            id=uuid.UUID(row['id']),
            track_id=uuid.UUID(row['track_id']),
            asset_type=AssetType[row['asset_type']],
            file_path=Path(row['file_path']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )
