"""
workers/stream_resolve_worker.py
=================================
Resolves a direct streamable audio URL off the UI thread, so playback
requests never block Qt's event loop while yt-dlp talks to the network.
"""

import logging
import traceback

from PySide6.QtCore import QRunnable, QObject, Signal

from core.utils import friendly_error_message
from services.stream_resolver_service import StreamResolverService

logger = logging.getLogger(__name__)


class StreamResolveSignals(QObject):
    resolved = Signal(str, str)   # source_key, direct_stream_url
    failed = Signal(str, str)     # source_key, error_message


class StreamResolveWorker(QRunnable):
    def __init__(self, source_key: str):
        super().__init__()
        self.source_key = source_key
        self.signals = StreamResolveSignals()

    def run(self):
        try:
            stream_url = StreamResolverService.resolve_audio_url(self.source_key)
            self.signals.resolved.emit(self.source_key, stream_url)
        except Exception as e:
            logger.debug(f"Stream resolve failed for {self.source_key}: {e}")
            logger.debug(traceback.format_exc())
            self.signals.failed.emit(self.source_key, friendly_error_message(str(e)))
