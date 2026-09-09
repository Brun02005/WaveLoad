import threading
from typing import List, Optional, Dict
from domain.models import DownloadItem
from core.state_machine import DownloadState

class QueueManager:
    """
    Thread-safe manager for the download queue.
    """
    def __init__(self):
        self._items: Dict[str, DownloadItem] = {}
        self._lock = threading.RLock()

    def add_item(self, item: DownloadItem):
        with self._lock:
            self._items[item.id] = item

    def get_item(self, item_id: str) -> Optional[DownloadItem]:
        with self._lock:
            return self._items.get(item_id)

    def get_all_items(self) -> List[DownloadItem]:
        with self._lock:
            return list(self._items.values())

    def update_item_state(self, item_id: str, state: DownloadState, message: str = "") -> bool:
        with self._lock:
            item = self._items.get(item_id)
            if item:
                item.update_state(state, message)
                return True
            return False

    def get_next_queued_item(self) -> Optional[DownloadItem]:
        """Returns the first QUEUED item."""
        with self._lock:
            for item in self._items.values():
                if item.state == DownloadState.QUEUED:
                    return item
        return None
        
    def get_next_retrying_item(self) -> Optional[DownloadItem]:
        """Returns a RETRYING item that is ready to be retried (e.g. backoff complete)."""
        # For simplicity, we just return the first retrying item. The scheduler will handle delays.
        with self._lock:
            for item in self._items.values():
                if item.state == DownloadState.RETRYING:
                    return item
        return None

    def remove_item(self, item_id: str):
        with self._lock:
            if item_id in self._items:
                del self._items[item_id]

    def clear(self):
        with self._lock:
            self._items.clear()

    @property
    def active_count(self) -> int:
        """Returns the number of items currently being processed."""
        with self._lock:
            return sum(1 for i in self._items.values() if i.state.is_active)

    @property
    def is_finished(self) -> bool:
        """Returns True if all items are in terminal states."""
        with self._lock:
            if not self._items:
                return True
            return all(i.state.is_terminal for i in self._items.values())
