import logging
import traceback
from PySide6.QtCore import QRunnable, QObject, Signal

from domain.models import DownloadItem
from core.state_machine import DownloadState
from services.download_service import DownloadService

logger = logging.getLogger(__name__)

class DownloadWorkerSignals(QObject):
    progress = Signal(str, str) # item_id, progress_text
    finished = Signal(str, str) # item_id, downloaded_file_path
    failed = Signal(str, str, bool) # item_id, error_message, is_transient

class DownloadWorker(QRunnable):
    """
    Worker for the download phase. 
    Only acquires the media file (no post-processing).
    """
    def __init__(self, item: DownloadItem, use_cookies: bool = True):
        super().__init__()
        self.item = item
        self.use_cookies = use_cookies
        self.signals = DownloadWorkerSignals()
        self._cancelled = False
        self._downloaded_file = None

    def cancel(self):
        self._cancelled = True

    def _progress_hook(self, d: dict):
        if self._cancelled:
            raise Exception("Cancelado por el usuario")

        status = d.get("status")
        if status == "downloading":
            percent = d.get("_percent_str", "").strip()
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            parts = [p for p in [percent, speed, f"ETA {eta}" if eta else ""] if p]
            text = " | ".join(parts) if parts else "Descargando..."
            self.signals.progress.emit(self.item.id, text)
        elif status == "finished":
            self._downloaded_file = d.get("filename")
            self.signals.progress.emit(self.item.id, "Descarga completada")

    def run(self):
        logger.info(f"Worker started downloading {self.item.url}")
        
        # Build the yt-dlp output template (download to original format)
        # We will convert it to mp3 in the post-processing phase.
        from core.utils import build_output_template
        outtmpl = build_output_template(self.item.output_dir, self.item.title)

        try:
            if self._cancelled:
                raise Exception("Cancelado por el usuario")

            DownloadService.download(
                url=self.item.url,
                output_template=outtmpl,
                audio_quality="320", # Not strictly used here if no postprocessor in yt-dlp
                progress_hook=self._progress_hook,
                use_cookies=self.use_cookies,
            )

            if self._cancelled:
                raise Exception("Cancelado por el usuario")
                
            if not self._downloaded_file:
                raise Exception("El archivo descargado no se encontró tras finalizar.")

            self.signals.finished.emit(self.item.id, self._downloaded_file)

        except Exception as e:
            msg = str(e)
            is_transient = self._is_transient_error(msg)
            
            if "Cancelado" in msg or "cancelado" in msg.lower():
                self.signals.failed.emit(self.item.id, "Cancelado", False)
            else:
                logger.error(f"Download failed for {self.item.url}: {msg}")
                logger.debug(traceback.format_exc())
                self.signals.failed.emit(self.item.id, msg, is_transient)

    def _is_transient_error(self, msg: str) -> bool:
        """Determines if an error is transient and should trigger a retry."""
        msg_lower = msg.lower()
        transient_keywords = [
            "network", "timeout", "http error 429", "http error 5", 
            "connection reset", "temporary", "read error"
        ]
        return any(k in msg_lower for k in transient_keywords)
