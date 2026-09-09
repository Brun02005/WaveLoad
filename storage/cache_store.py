import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any

from core.config import BASE_DIR

logger = logging.getLogger(__name__)

class CacheStore:
    """
    A simple file-backed cache for storing metadata across application runs.
    Useful for avoiding repeated YouTube API calls.

    Thread-safe: reads/writes happen from multiple worker threads, so every
    access to the backing dict is guarded by a lock and _save() serializes a
    snapshot copy (previously this raised "dictionary changed size during
    iteration" when a worker mutated the dict mid-dump).
    """
    def __init__(self, cache_file: Path = BASE_DIR / "waveload_cache.json"):
        self.cache_file = cache_file
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
                self._data = {}

    def _save(self):
        try:
            with self._lock:
                snapshot = dict(self._data)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any):
        with self._lock:
            self._data[key] = value
        self._save()

    def clear(self):
        with self._lock:
            self._data = {}
        self._save()

# Global instance for easy access
metadata_cache = CacheStore()
