import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from domain.repositories.track_repository import TrackRepository

logger = logging.getLogger(__name__)

# Formatos que la importación acepta; ubicar un archivo movido acepta lo mismo.
SUPPORTED_AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".aiff"}


def audio_path(track) -> Optional[Path]:
    """La ruta del audio de un track, o None si no tiene asset de audio."""
    for asset in track.assets:
        if asset.asset_type.name.startswith("AUDIO"):
            return Path(asset.file_path)
    return None


@dataclass
class RemovalReport:
    """Qué pasó al quitar pistas de la librería."""
    removed: int = 0
    files_trashed: int = 0
    # (ruta, motivo) de los archivos que no se pudieron mandar a la Papelera.
    # Esas pistas NO se quitan de la librería: si se quitaran, el archivo
    # quedaría en el disco sin que nada lo muestre.
    kept: List[tuple] = field(default_factory=list)


class LibraryService:
    """
    High-level orchestration for the entire music library.
    This service will handle operations that span across multiple tracks.
    """
    def __init__(self, repository: TrackRepository,
                 trash: Optional[Callable[[Path], None]] = None):
        self.repository = repository
        # Inyectable: los tests no mandan nada a la Papelera real.
        if trash is None:
            from infrastructure.recycle_bin import send_to_recycle_bin  # noqa: PLC0415
            trash = send_to_recycle_bin
        self._trash = trash

    def get_all_tracks(self) -> List["domain.track.Track"]:
        """
        Retrieves all tracks from the persistent library.
        Future methods (search, filter, get_track) will follow this same pattern.
        """
        return self.repository.get_all()

    def is_duplicate(self, file_path: str) -> bool:
        """
        Checks if a file has already been imported into the library.
        """
        return self.repository.exists_by_path(file_path)

    # --- archivos faltantes ------------------------------------------------

    @staticmethod
    def is_missing(track) -> bool:
        """El archivo de audio del track no está donde la librería lo espera."""
        path = audio_path(track)
        return path is None or not path.exists()

    def check_missing_files(self, tracks: Optional[Iterable] = None) -> List[str]:
        """Ids de los tracks cuyo archivo de audio ya no existe.

        La librería es la fuente de verdad, así que borrar o mover un archivo
        no saca la pista: queda apuntando a una ruta vacía. Esto es lo que
        permite mostrarlo en vez de fingir que todo está bien.
        """
        tracks = self.repository.get_all() if tracks is None else tracks
        return [str(t.id) for t in tracks if self.is_missing(t)]

    def relocate(self, track_id: str, new_path: str) -> None:
        """Apunta una pista a su archivo en una ubicación nueva.

        Conserva todo lo que la pista ya tenía (análisis, etiquetas, crates):
        es la diferencia con quitarla e importarla de nuevo.
        """
        path = Path(new_path)
        if not path.is_file():
            raise ValueError(f"No existe el archivo {path}")
        if path.suffix.lower() not in SUPPORTED_AUDIO:
            raise ValueError(f"Formato no soportado: {path.suffix or 'sin extensión'}")
        if not self.repository.update_audio_path(track_id, str(path)):
            raise ValueError("La pista ya no está en la librería")

    # --- quitar ------------------------------------------------------------

    def remove_tracks(self, tracks: Iterable, delete_files: bool = False) -> RemovalReport:
        """Quita pistas de la librería y, si se pide, manda sus archivos a la
        Papelera de reciclaje (nunca un borrado permanente).

        Con ``delete_files``, primero va el archivo y después la fila: si el
        archivo no se pudo mover (está abierto en otro programa, sin permisos),
        la pista se queda en la librería y se informa. Una pista sin archivo
        se quita igual: no hay nada que mandar a la Papelera.
        """
        report = RemovalReport()
        to_delete: List[str] = []
        for track in tracks:
            path = audio_path(track)
            if delete_files and path is not None and path.exists():
                try:
                    self._trash(path)
                    report.files_trashed += 1
                except OSError as exc:
                    logger.warning("No se pudo mandar a la Papelera %s: %s", path, exc)
                    report.kept.append((str(path), str(exc)))
                    continue
            to_delete.append(str(track.id))
        report.removed = self.repository.delete_many(to_delete)
        return report
