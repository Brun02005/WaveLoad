import logging
from typing import List, Optional
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread, QRunnable, QThreadPool

from domain.models import DownloadItem
from core.state_machine import DownloadState
from core.queue_manager import QueueManager
from core.scheduler import Scheduler
from storage.session_store import SessionStore
from services.cookie_service import cookie_service
from services.metadata_service import MetadataService
from core.config import MAX_CONCURRENT_DOWNLOADS, resolve_download_dir

logger = logging.getLogger(__name__)

class ValidationSignals(QObject):
    log = Signal(str)
    item_validated = Signal(int, str, str, str) # index, title, status_code, detail
    item_progress = Signal(int, str)
    batch_ready = Signal(list) # list of items
    batch_finished = Signal()

class BatchValidationWorker(QRunnable):
    def __init__(self, urls: List[str], output_dir: Path):
        super().__init__()
        self.urls = urls
        self.output_dir = output_dir
        self.signals = ValidationSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        valid_items = []
        total = len(self.urls)
        
        # Initialize cookie session once for the batch
        if self.urls:
            cookie_service.initialize_session(self.urls[0])

        for index, url in enumerate(self.urls):
            if self._cancelled:
                break
                
            self.signals.item_progress.emit(index, "Validando...")
            try:
                metadata = MetadataService.extract_metadata(url)
                
                # Check for duplicates or invalid using the unified path builder
                from core.utils import build_final_mp3_path
                title = metadata.get("title", "Desconocido")
                final_mp3 = build_final_mp3_path(self.output_dir, title)
                
                if final_mp3.exists():
                    self.signals.item_validated.emit(index, title, "duplicado", "Ya existe en la carpeta.")
                    continue
                    
                if metadata.get("is_playlist"):
                    self.signals.item_validated.emit(index, title, "playlist", "Las playlists todavía no están soportadas.")
                    continue
                    
                resolved_url = metadata.get("url") or url
                item = DownloadItem(
                    id=url,
                    url=resolved_url,
                    title=title,
                    output_dir=self.output_dir,
                    uploader=metadata.get("uploader"),
                    thumbnail_url=metadata.get("thumbnail_url"),
                    year=metadata.get("year"),
                    duration=metadata.get("duration", 0),
                    final_mp3_path=final_mp3
                )
                valid_items.append(item)
                self.signals.item_validated.emit(index, title, "valido", "Listo para descargar.")
                
            except Exception as e:
                self.signals.item_validated.emit(index, "—", "error", str(e))
                
        self.signals.batch_ready.emit(valid_items)
        self.signals.batch_finished.emit()

class DownloadManager(QObject):
    """
    Facade for the UI to interact with the download system.
    Maintains the same signal contract as the old DownloadController.
    """
    log            = Signal(str)
    item_validated = Signal(int, str, str, str)
    item_progress  = Signal(int, str)
    item_finished  = Signal(int, str, str) # index, final_status, final_name
    batch_progress = Signal(int, int)
    batch_finished = Signal()
    batch_error    = Signal(str)

    def __init__(self):
        super().__init__()
        self.queue_manager = QueueManager()
        self.scheduler = Scheduler(self.queue_manager)
        self.session_store = SessionStore()
        
        self.scheduler.signals.item_updated.connect(self._on_item_updated)
        self.scheduler.signals.batch_finished.connect(self._on_scheduler_batch_finished)
        
        self._url_to_index = {} # Map URLs to UI indices
        self._total_batch = 0
        self._completed_in_batch = 0
        
        self.thread_pool = QThreadPool()

        # Try to recover session
        self._recover_session()

    def _recover_session(self):
        items = self.session_store.load_session()
        if items:
            self.log.emit(f"🔄 Recuperando sesión anterior con {len(items)} descargas.")
            for item in items:
                # Add to queue but don't emit index-based signals yet since UI doesn't know about them
                self.queue_manager.add_item(item)
            # Starting scheduler to process recovered queue
            self.scheduler.start()

    def start(
        self,
        urls: List[str],
        output_dir: Optional[Path] = None,
        use_browser_auth: bool = True,
        audio_quality: str = "320",
        max_workers: Optional[int] = None,
        write_id3_tags: bool = True,
    ):
        """Called by UI to enqueue new downloads."""
        # resolve_download_dir() creates the folder and falls back if it's not
        # writable, so a download never fails just because it's missing.
        output_dir = resolve_download_dir(output_dir)
        
        # We need to map new URLs to new UI indices
        start_index = len(self._url_to_index)
        for i, url in enumerate(urls):
            self._url_to_index[url] = start_index + i
            
        self._total_batch += len(urls)

        worker = BatchValidationWorker(urls, output_dir)
        worker.signals.log.connect(self.log.emit)
        
        # Wrap index mapping
        def emit_validated(idx, t, s, d):
            # idx is relative to the current batch, map it globally
            global_idx = start_index + idx
            self.item_validated.emit(global_idx, t, s, d)
            
        def emit_progress(idx, p):
            global_idx = start_index + idx
            self.item_progress.emit(global_idx, p)
            
        worker.signals.item_validated.connect(emit_validated)
        worker.signals.item_progress.connect(emit_progress)
        worker.signals.batch_ready.connect(self._on_batch_validated)
        
        self.thread_pool.start(worker)

    def _on_batch_validated(self, items: List[DownloadItem]):
        for item in items:
            self.queue_manager.add_item(item)
            
        self._save_session()
        
        if items:
            self.log.emit(f"⬇️ Añadidas {len(items)} canciones a la cola.")
            self.scheduler.start()
        else:
            self.log.emit("⚠️ No hay links válidos para procesar.")

    def _on_item_updated(self, item_id: str):
        item = self.queue_manager.get_item(item_id)
        if not item:
            return
            
        index = self._url_to_index.get(item_id, -1)
        if index == -1:
            return

        # Emit progress
        if item.progress_text:
            self.item_progress.emit(index, item.progress_text)
            
        # Emit finished
        if item.state.is_terminal:
            status = "ok" if item.state == DownloadState.COMPLETED else ("cancelado" if item.state == DownloadState.CANCELLED else "error")
            name = item.final_mp3_path.name if item.final_mp3_path else (item.error_message or item.title)
            self.item_finished.emit(index, status, name)
            
            self._completed_in_batch += 1
            self.batch_progress.emit(self._completed_in_batch, self._total_batch)
            
            self._save_session()

    def _on_scheduler_batch_finished(self):
        # Once all tasks in queue are terminal
        self.log.emit("🏁 Toda la cola ha finalizado.")
        self.batch_finished.emit()
        self.session_store.clear_session()
        cookie_service.cleanup_session()

    def cancel(self):
        self.log.emit("⛔ Cancelación solicitada. Vaciando cola...")
        self.scheduler.stop()
        for item in self.queue_manager.get_all_items():
            if not item.state.is_terminal:
                self.queue_manager.update_item_state(item.id, DownloadState.CANCELLED, "Cancelado")
                self._on_item_updated(item.id)
        
        self.session_store.clear_session()
        cookie_service.cleanup_session()

    def _save_session(self):
        # Save session periodically on state changes
        items = self.queue_manager.get_all_items()
        self.session_store.save_session(items)
