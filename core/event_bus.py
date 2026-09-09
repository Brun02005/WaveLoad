import logging
from typing import Callable, Dict, List, Type, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# --- Event Definitions ---

class Event:
    """Base class for all domain events."""
    pass

@dataclass
class TrackDownloadedEvent(Event):
    """
    Emitted when a download finishes post-processing successfully.
    Contains raw data from the DownloadItem to avoid passing the whole item.
    """
    item_id: str
    title: str
    uploader: str
    year: str
    duration: int
    final_mp3_path: str

@dataclass
class TrackCreatedEvent(Event):
    """
    Emitted when a Track is successfully persisted in the library.
    Contains the domain Track object (avoids circular imports by typing as Any).
    """
    track: Any

# --- Event Bus ---

class EventBus:
    """
    Simple synchronous Pub/Sub event bus.
    Decouples the download engine from the music library.
    """
    def __init__(self):
        self._subscribers: Dict[Type[Event], List[Callable]] = {}

    def subscribe(self, event_type: Type[Event], handler: Callable):
        """Registers a handler for a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(f"Subscribed {handler.__name__} to {event_type.__name__}")

    def emit(self, event: Event):
        """Dispatches an event to all registered handlers."""
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])
        logger.debug(f"Emitting {event_type.__name__} to {len(handlers)} handlers.")
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error handling event {event_type.__name__} in {handler.__name__}: {e}")

# Global instance
event_bus = EventBus()
