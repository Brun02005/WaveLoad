import logging
import asyncio
import threading
from PySide6.QtCore import QObject, Signal, QThread

from services.metadata_service import MetadataService
from core.utils import friendly_error_message

logger = logging.getLogger(__name__)

class BackgroundValidator(QObject):
    """
    Validates URLs using true async I/O.
    Runs a dedicated asyncio event loop in a background thread.
    """
    validation_started = Signal(str)  # url
    validation_finished = Signal(str, dict)  # url, metadata
    validation_failed = Signal(str, str)     # url, error

    def __init__(self, use_browser_auth: bool = True):
        super().__init__()
        self.use_browser_auth = use_browser_auth # Kept for compatibility
        self._in_flight: set = set()

        # Setup dedicated asyncio loop in a background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._start_loop, daemon=True)
        self._thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def validate_url(self, url: str):
        if url in self._in_flight:
            return
        self._in_flight.add(url)
        self.validation_started.emit(url)
        
        # Dispatch the async coroutine safely from the Qt main thread to the asyncio loop
        asyncio.run_coroutine_threadsafe(self._validate_coroutine(url), self._loop)

    async def _validate_coroutine(self, url: str):
        try:
            metadata = await MetadataService.extract_metadata_async(url)
            self._on_finished(url, metadata)
        except Exception as e:
            msg = friendly_error_message(str(e))
            self._on_failed(url, msg)

    def _on_finished(self, url: str, metadata: dict):
        self._in_flight.discard(url)
        # Emit signal to main thread
        self.validation_finished.emit(url, metadata)

    def _on_failed(self, url: str, error: str):
        self._in_flight.discard(url)
        # Emit signal to main thread
        self.validation_failed.emit(url, error)
