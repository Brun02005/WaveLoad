import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any

from core.config import BASE_DIR
from domain.models import DownloadItem
from core.state_machine import DownloadState

logger = logging.getLogger(__name__)

class SessionStore:
    """
    Persists the state of the download queue to a SQLite database
    to recover from crashes safely even with thousands of items.
    """
    def __init__(self, db_file: Path = BASE_DIR / "waveload_session.db"):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id TEXT PRIMARY KEY,
                        url TEXT,
                        title TEXT,
                        output_dir TEXT,
                        state TEXT,
                        uploader TEXT,
                        thumbnail_url TEXT,
                        year TEXT,
                        duration INTEGER,
                        progress_text TEXT,
                        error_message TEXT,
                        retry_count INTEGER,
                        max_retries INTEGER,
                        final_mp3_path TEXT,
                        temp_download_path TEXT,
                        last_active_time REAL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite session DB: {e}")

    def save_session(self, items: List[DownloadItem]):
        """Serializes the current list of items to the sqlite database."""
        try:
            self._init_db()  # ensure schema exists (defensive against legacy dropped tables)
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # We use UPSERT (INSERT OR REPLACE)
                records = []
                for item in items:
                    records.append((
                        item.id,
                        item.url,
                        item.title,
                        str(item.output_dir),
                        item.state.value,
                        item.uploader,
                        item.thumbnail_url,
                        item.year,
                        item.duration,
                        item.progress_text,
                        item.error_message,
                        item.retry_count,
                        item.max_retries,
                        str(item.final_mp3_path) if item.final_mp3_path else None,
                        str(item.temp_download_path) if item.temp_download_path else None,
                        item.last_active_time
                    ))
                    
                cursor.executemany("""
                    INSERT OR REPLACE INTO downloads 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, records)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save session to SQLite: {e}")

    def load_session(self) -> List[DownloadItem]:
        """Loads items from the session database. Returns an empty list if none."""
        if not self.db_file.exists():
            return []
            
        items = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM downloads")
                rows = cursor.fetchall()
                
                for r in rows:
                    (id_val, url, title, output_dir, state_str, uploader, thumbnail_url,
                     year, duration, progress_text, error_message, retry_count,
                     max_retries, final_mp3_path, temp_download_path, last_active_time) = r
                    
                    state = DownloadState(state_str)
                    # Revert active states to QUEUED on crash recovery
                    if state.is_active or state == DownloadState.PAUSED:
                        state = DownloadState.QUEUED
                        
                    item = DownloadItem(
                        id=id_val,
                        url=url,
                        title=title,
                        output_dir=Path(output_dir),
                        state=state,
                        uploader=uploader,
                        thumbnail_url=thumbnail_url,
                        year=year,
                        duration=duration,
                        progress_text=progress_text,
                        error_message=error_message,
                        retry_count=retry_count,
                        max_retries=max_retries,
                        final_mp3_path=Path(final_mp3_path) if final_mp3_path else None,
                        temp_download_path=Path(temp_download_path) if temp_download_path else None,
                        last_active_time=last_active_time
                    )
                    items.append(item)
            return items
        except Exception as e:
            logger.error(f"Failed to load session from SQLite: {e}")
            return []

    def clear_session(self):
        """Clears all queued items (e.g. when all downloads finish successfully).

        We truncate the table instead of dropping it: dropping the table left
        the schema missing, so any subsequent save_session() failed with
        "no such table: downloads".
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM downloads")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to clear session DB: {e}")
