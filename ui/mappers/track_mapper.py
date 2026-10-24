"""
ui/mappers/track_mapper.py
==========================
Isolates the presentation layer from the domain layer.
Responsible for converting pure Domain entities (like Track) into
ViewModel-compatible formats optimized for Qt rendering.
"""

from typing import Dict, Any, List
from domain.tags import NS_GENRE
from domain.track import Track
from ui.mappers.tag_labels import tag_label

class TrackPresentationMapper:
    """
    Maps domain.track.Track objects to dictionaries.
    Designed so that it can be easily upgraded to return a typed TrackViewModel
    dataclass in the future without breaking the LibraryWorkspace interface.
    """

    # Función ``ids -> {id: [Tag]}`` que se inyecta al arrancar. Así todas las
    # pantallas que mapean pistas (librería, colecciones, grafo) reciben sus
    # tags sin que cada una tenga que pedirlos: una consulta por lista, no por
    # fila.
    _tag_provider = None

    @classmethod
    def set_tag_provider(cls, provider) -> None:
        cls._tag_provider = provider

    @classmethod
    def _tags_for(cls, track_ids):
        if cls._tag_provider is None or not track_ids:
            return {}
        try:
            return cls._tag_provider(track_ids)
        except Exception:  # noqa: BLE001 — sin tags la tabla igual se dibuja
            import logging  # noqa: PLC0415
            logging.getLogger(__name__).exception("No se pudieron leer los tags")
            return {}

    @classmethod
    def to_presentation(cls, track: Track, tags=None) -> Dict[str, Any]:
        """
        Extracts only what is needed for presentation.
        Formatting (like duration in MM:SS) happens here or in the delegate,
        but we pass raw numbers where sorting is required (e.g. duration).
        """
        # Determine format/quality based on assets
        formats = []
        filesize = "—"
        folder = "—"
        file_path = ""
        missing = True

        for asset in track.assets:
            if "MP3" in asset.asset_type.name:
                formats.append("MP3")
            elif "WAV" in asset.asset_type.name:
                formats.append("WAV")
            elif "FLAC" in asset.asset_type.name:
                formats.append("FLAC")

            # Absolute path of the (first) audio asset — needed for exporting.
            if asset.asset_type.name.startswith("AUDIO") and not file_path:
                file_path = str(asset.file_path)
                missing = not asset.file_path.exists()

            # Use the first valid audio asset to extract physical metadata
            if asset.file_path.exists():
                try:
                    size_bytes = asset.file_path.stat().st_size
                    filesize = f"{size_bytes / (1024 * 1024):.1f} MB"
                except Exception:
                    pass
                
                # Get the name of the directory containing the file
                folder = asset.file_path.parent.name
        
        # Simple string for format column
        format_str = ", ".join(set(formats)) if formats else "—"
        
        # We assume the library tracks are fully processed and ready, 
        # unless they have some error state. For now, "Ready" is default.
        status = "Disponible"

        if tags is None:
            tags = cls._tags_for([str(track.id)]).get(str(track.id), [])
        por_eje: Dict[str, List[str]] = {}
        for tag in tags:
            por_eje.setdefault(tag.namespace, []).append(tag.value)
        generos = por_eje.get(NS_GENRE, [])

        return {
            "id": str(track.id),
            "title": track.title or "—",
            "artist": track.artist or "—",
            "album": track.album or "—",
            "remix": "—",  # Future metadata extraction
            "genre": ", ".join(tag_label(NS_GENRE, g) for g in generos) or "—",
            # Los tags que edita el usuario, por eje: {"genre": ["techno"], ...}
            "tags": por_eje,
            "bpm": str(round(track.bpm)) if track.bpm else "—",
            "key": track.key_camelot or "—",
            "energy": int(track.energy) if track.energy is not None else None,
            "duration": track.duration, # Raw int for sorting
            "quality": "—",             # Placeholder for future extraction
            "format": format_str,
            "folder": folder,
            "path": file_path,
            "date_added": track.created_at.strftime("%Y-%m-%d"),
            "status": "Archivo no encontrado" if missing else status,
            # El archivo ya no está donde la librería lo espera (borrado o
            # movido): la tabla lo marca y el menú ofrece ubicarlo o quitarlo.
            "missing": missing,
            
            # Additional context panel fields
            "bitrate": "—",             # Needs mutagen extraction in future
            "samplerate": "—",          # Needs mutagen extraction in future
            "filesize": filesize
        }

    @classmethod
    def to_presentation_list(cls, tracks: List[Track]) -> List[Dict[str, Any]]:
        """Optimized bulk mapping: los tags de toda la lista en una consulta."""
        tags = cls._tags_for([str(t.id) for t in tracks])
        return [cls.to_presentation(t, tags.get(str(t.id), [])) for t in tracks]
