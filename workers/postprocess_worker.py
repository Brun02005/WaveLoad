import logging
import subprocess
import os
import traceback
from pathlib import Path
from PySide6.QtCore import QRunnable, QObject, Signal

from domain.models import DownloadItem

logger = logging.getLogger(__name__)

class PostProcessSignals(QObject):
    progress = Signal(str, str) # item_id, progress_text
    finished = Signal(str, str) # item_id, final_mp3_path
    failed = Signal(str, str)   # item_id, error_message

class PostProcessWorker(QRunnable):
    """
    Worker for converting downloaded media to MP3 and embedding metadata.
    Runs ffmpeg directly.
    """
    def __init__(self, item: DownloadItem, downloaded_file_path: str, bitrate: str = "320"):
        super().__init__()
        self.item = item
        self.bitrate = bitrate
        self.downloaded_file_path = Path(downloaded_file_path)
        self.signals = PostProcessSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        logger.info(f"Worker started post-processing {self.downloaded_file_path}")
        
        try:
            if self._cancelled:
                raise Exception("Cancelado por el usuario")

            self.signals.progress.emit(self.item.id, "Convirtiendo a MP3...")

            from core.utils import build_final_mp3_path
            final_mp3_path = build_final_mp3_path(self.item.output_dir, self.item.title)

            # If the downloaded file is already the final mp3 file, we just rename or keep it
            if self.downloaded_file_path.resolve() == final_mp3_path.resolve():
                logger.info(f"File is already MP3: {final_mp3_path}")
            else:
                # Make sure the destination directory exists (e.g. after a folder change).
                final_mp3_path.parent.mkdir(parents=True, exist_ok=True)

                self._convert_to_mp3(final_mp3_path)

                # Cleanup original downloaded file if it's different
                try:
                    if self.downloaded_file_path.exists():
                        self.downloaded_file_path.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete temporary file {self.downloaded_file_path}: {e}")

            if self._cancelled:
                # If cancelled during post-processing, we might leave a partial file, but we should report cancellation
                raise Exception("Cancelado por el usuario")

            self.signals.finished.emit(self.item.id, str(final_mp3_path))

            # --- WaveLoad 4.5: Emit event to decouple from library domain ---
            try:
                from core.event_bus import event_bus, TrackDownloadedEvent
                event_bus.emit(TrackDownloadedEvent(
                    item_id=self.item.id,
                    title=self.item.title,
                    uploader=self.item.uploader or "",
                    year=self.item.year or "",
                    duration=self.item.duration or 0,
                    final_mp3_path=str(final_mp3_path)
                ))
            except Exception as e:
                logger.error(f"Failed to emit TrackDownloadedEvent: {e}")
            # ----------------------------------------------------------------

        except Exception as e:
            msg = str(e)
            if "Cancelado" in msg or "cancelado" in msg.lower():
                self.signals.failed.emit(self.item.id, "Cancelado")
            else:
                logger.error(f"Post-processing failed for {self.item.url}: {msg}")
                logger.debug(traceback.format_exc())
                self.signals.failed.emit(self.item.id, msg)

    def _build_ffmpeg_cmd(self, final_mp3_path: Path) -> list:
        from core.config import ffmpeg_executable
        cmd = [
            ffmpeg_executable(),
            "-hide_banner",      # skip the version/config banner noise in stderr
            "-loglevel", "error",  # so captured stderr is the actual error, not info
            "-y",                # overwrite
            "-i", str(self.downloaded_file_path),
            "-vn",               # no video
            "-ar", "44100",
            "-ac", "2",
            "-b:a", f"{self.bitrate}k",
        ]
        if self.item.title:
            cmd.extend(["-metadata", f"title={self.item.title}"])
        if self.item.uploader:
            cmd.extend(["-metadata", f"artist={self.item.uploader}"])
            cmd.extend(["-metadata", f"album={self.item.uploader}"])
        if self.item.year:
            cmd.extend(["-metadata", f"date={self.item.year}"])
        cmd.append(str(final_mp3_path))
        return cmd

    def _convert_to_mp3(self, final_mp3_path: Path, attempts: int = 2):
        """Runs ffmpeg to produce the final MP3, retrying once on failure.

        Surfaces the *real* ffmpeg error (last meaningful stderr line) instead of
        a generic message, and verifies the output file was actually written.
        """
        last_error = ""
        # Un archivo que ya estaba es del usuario: si ffmpeg falla, no se borra.
        existed_before = final_mp3_path.exists()
        for attempt in range(1, attempts + 1):
            if self._cancelled:
                raise Exception("Cancelado por el usuario")

            cmd = self._build_ffmpeg_cmd(final_mp3_path)
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
            except FileNotFoundError:
                # No tiene sentido reintentar: el binario no está.
                raise Exception("FFmpeg no está instalado o no está en el PATH.")
            out, err = process.communicate()
            stderr_text = err.decode("utf-8", errors="replace").strip()

            output_ok = final_mp3_path.exists() and final_mp3_path.stat().st_size > 0

            if process.returncode == 0 and output_ok:
                return  # success

            # Extract the most informative stderr line (last non-empty one).
            error_lines = [ln.strip() for ln in stderr_text.splitlines() if ln.strip()]
            last_error = error_lines[-1] if error_lines else "sin salida de error"
            logger.error(
                f"FFmpeg attempt {attempt}/{attempts} failed (rc={process.returncode}) "
                f"for '{final_mp3_path.name}': {last_error}"
            )
            if not output_ok and process.returncode == 0:
                last_error = "FFmpeg terminó sin generar el archivo MP3."

            # Remove any partial/corrupt output before retrying. Un MP3 a medias
            # que queda en disco se marca como "duplicado" en la próxima tanda.
            try:
                if final_mp3_path.exists() and not existed_before:
                    final_mp3_path.unlink()
            except Exception:
                pass

        raise Exception(self._friendly_ffmpeg_error(last_error))

    @staticmethod
    def _friendly_ffmpeg_error(stderr_line: str) -> str:
        low = (stderr_line or "").lower()
        if "invalid argument" in low or "error opening output" in low:
            return "Nombre de archivo no válido para el sistema."
        if "no such file" in low:
            return "El archivo descargado no se encontró para convertir."
        if "permission denied" in low:
            return "Sin permisos de escritura en la carpeta de destino."
        if "no space left" in low:
            return "No hay espacio en disco para guardar el MP3."
        return f"Fallo en la conversión a MP3: {stderr_line}" if stderr_line else "Fallo en la conversión a MP3 con FFmpeg."
