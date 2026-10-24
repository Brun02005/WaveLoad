import logging
import time
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QThreadPool, Signal

from core.queue_manager import QueueManager
from core.state_machine import DownloadState
from domain.models import DownloadItem
from workers.download_worker import DownloadWorker
from workers.postprocess_worker import PostProcessWorker
from core.config import MAX_CONCURRENT_DOWNLOADS

logger = logging.getLogger(__name__)

VALID_BITRATES = {"320", "256", "192", "128"}


class SchedulerSignals(QObject):
    item_updated = Signal(str) # item_id
    batch_finished = Signal()

class Scheduler(QObject):
    """
    Central scheduler that manages concurrency limits, pulls from the queue,
    handles retries with backoff, and monitors worker health.
    """
    def __init__(self, queue_manager: QueueManager):
        super().__init__()
        self.queue = queue_manager
        self.signals = SchedulerSignals()
        
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(MAX_CONCURRENT_DOWNLOADS * 2) # Allow space for post-processing
        
        self.max_downloads = MAX_CONCURRENT_DOWNLOADS
        self._active_downloads = set() # Set of item IDs currently downloading
        self._active_workers = {}      # item_id -> QRunnable
        self._finished_workers = []    # Keep references to prevent GC crashes during signal emits
        
        self._is_running = False
        
        # Periodic watchdog and dispatcher
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        
        self.stalled_timeout = 300 # 5 minutes

        # Opciones de la tanda en curso, elegidas en Ajustes. Antes la UI las
        # mandaba y nadie las usaba: el MP3 salía siempre a 320k y las cookies
        # se probaban aunque el usuario las hubiera apagado.
        self.audio_quality = "320"
        self.use_browser_auth = True

    def configure(self, audio_quality: str = "320", use_browser_auth: bool = True):
        self.audio_quality = audio_quality if str(audio_quality) in VALID_BITRATES else "320"
        self.use_browser_auth = bool(use_browser_auth)

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._timer.start(1000) # Check every second
            logger.info("Scheduler started.")

    def stop(self):
        if self._is_running:
            self._is_running = False
            self._timer.stop()
            self._cancel_all_workers()
            logger.info("Scheduler stopped.")

    def _cancel_all_workers(self):
        for worker in self._active_workers.values():
            if hasattr(worker, 'cancel'):
                worker.cancel()
        self._active_workers.clear()
        self._active_downloads.clear()
        self._finished_workers.clear()

    def _tick(self):
        """Called every second to dispatch tasks and monitor health."""
        if not self._is_running:
            return

        # Clear finished workers to let them GC safely now that their threads are done
        self._finished_workers.clear()

        self._check_stalled_workers()
        self._dispatch_retries()
        self._dispatch_new_downloads()

        if self.queue.is_finished and not self._active_downloads and not self._active_workers:
            if self._is_running:
                self.stop()
                self.signals.batch_finished.emit()

    def _check_stalled_workers(self):
        now = time.time()
        for item in self.queue.get_all_items():
            if item.state in (DownloadState.DOWNLOADING, DownloadState.POST_PROCESSING):
                if now - item.last_active_time > self.stalled_timeout:
                    logger.warning(f"Worker for {item.id} is stalled. Cancelling and retrying.")
                    self._handle_failure(item.id, "Stalled worker timeout", is_transient=True)
                    
                    # Force remove worker tracking but keep alive to avoid GC crash if emitting
                    worker = self._active_workers.pop(item.id, None)
                    if worker:
                        self._finished_workers.append(worker)
                        if hasattr(worker, 'cancel'):
                            worker.cancel()

    def _dispatch_new_downloads(self):
        while len(self._active_downloads) < self.max_downloads:
            item = self.queue.get_next_queued_item()
            if not item:
                break
                
            self._start_download(item)

    def _dispatch_retries(self):
        # Allow retry if under limit
        if len(self._active_downloads) >= self.max_downloads:
            return
            
        now = time.time()
        for item in self.queue.get_all_items():
            if item.state == DownloadState.RETRYING:
                # Exponential backoff: 2, 4, 8, 16... seconds
                delay = 2 ** item.retry_count
                if now - item.last_active_time > delay:
                    self._start_download(item)
                    if len(self._active_downloads) >= self.max_downloads:
                        break

    def _start_download(self, item: DownloadItem):
        logger.info(f"Dispatching download for {item.id}")
        self.queue.update_item_state(item.id, DownloadState.DOWNLOADING, "Descargando...")
        item.last_active_time = time.time()
        
        self._active_downloads.add(item.id)
        
        worker = DownloadWorker(item, use_cookies=self.use_browser_auth)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_download_finished)
        worker.signals.failed.connect(self._on_download_failed)
        
        self._active_workers[item.id] = worker
        self.thread_pool.start(worker)
        self.signals.item_updated.emit(item.id)

    def _on_progress(self, item_id: str, progress_text: str):
        item = self.queue.get_item(item_id)
        if item:
            item.progress_text = progress_text
            item.last_active_time = time.time()
            self.signals.item_updated.emit(item_id)

    def _on_download_finished(self, item_id: str, temp_path: str):
        self._active_downloads.discard(item_id)
        worker = self._active_workers.pop(item_id, None)
        if worker:
            self._finished_workers.append(worker)
        
        item = self.queue.get_item(item_id)
        if not item:
            return
            
        logger.info(f"Download finished for {item_id}, starting post-processing.")
        self.queue.update_item_state(item_id, DownloadState.POST_PROCESSING, "Convirtiendo a MP3...")
        item.temp_download_path = Path(temp_path)
        item.last_active_time = time.time()
        self.signals.item_updated.emit(item_id)
        
        # Start PostProcessing
        pp_worker = PostProcessWorker(item, temp_path, bitrate=self.audio_quality)
        pp_worker.signals.progress.connect(self._on_progress)
        pp_worker.signals.finished.connect(self._on_postprocess_finished)
        pp_worker.signals.failed.connect(self._on_postprocess_failed)
        
        self._active_workers[item_id] = pp_worker
        self.thread_pool.start(pp_worker)

    def _on_download_failed(self, item_id: str, error_msg: str, is_transient: bool):
        self._active_downloads.discard(item_id)
        worker = self._active_workers.pop(item_id, None)
        if worker:
            self._finished_workers.append(worker)
        self._handle_failure(item_id, error_msg, is_transient)

    def _on_postprocess_finished(self, item_id: str, final_mp3_path: str):
        worker = self._active_workers.pop(item_id, None)
        if worker:
            self._finished_workers.append(worker)
        
        item = self.queue.get_item(item_id)
        if not item:
            return
            
        logger.info(f"Post-processing finished for {item_id}")
        item.final_mp3_path = Path(final_mp3_path)
        self.queue.update_item_state(item_id, DownloadState.COMPLETED, "Completado")
        self.signals.item_updated.emit(item_id)

    def _on_postprocess_failed(self, item_id: str, error_msg: str):
        worker = self._active_workers.pop(item_id, None)
        if worker:
            self._finished_workers.append(worker)
        self._handle_failure(item_id, error_msg, is_transient=False)

    def _handle_failure(self, item_id: str, error_msg: str, is_transient: bool):
        item = self.queue.get_item(item_id)
        if not item:
            return
            
        item.last_active_time = time.time()
        item.error_message = error_msg
        
        if is_transient and item.retry_count < item.max_retries:
            item.retry_count += 1
            self.queue.update_item_state(item_id, DownloadState.RETRYING, f"Reintentando ({item.retry_count}/{item.max_retries})...")
            logger.info(f"Transient error for {item_id}, scheduled retry {item.retry_count}")
        else:
            state = DownloadState.CANCELLED if "Cancelado" in error_msg else DownloadState.FAILED
            self.queue.update_item_state(item_id, state, error_msg)
            logger.error(f"Permanent failure for {item_id}: {error_msg}")
            
        self.signals.item_updated.emit(item_id)

    def cancel_item(self, item_id: str):
        worker = self._active_workers.get(item_id)
        if worker and hasattr(worker, 'cancel'):
            worker.cancel()
        else:
            # If not active, just update state directly
            self.queue.update_item_state(item_id, DownloadState.CANCELLED, "Cancelado por el usuario")
            self.signals.item_updated.emit(item_id)
