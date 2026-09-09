"""
ui/mappers/track_mapper.py
==========================
Isolates the presentation layer from the domain layer.
Responsible for converting pure Domain entities (like Track) into
ViewModel-compatible formats optimized for Qt rendering.
"""

from typing import Dict, Any, List
from domain.track import Track

class TrackPresentationMapper:
    """
    Maps domain.track.Track objects to dictionaries.
    Designed so that it can be easily upgraded to return a typed TrackViewModel
    dataclass in the future without breaking the LibraryWorkspace interface.
    """

    @staticmethod
    def to_presentation(track: Track) -> Dict[str, Any]:
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
        status = "Ready"

        return {
            "id": str(track.id),
            "title": track.title or "—",
            "artist": track.artist or "—",
            "album": track.album or "—",
            "remix": "—",  # Future metadata extraction
            "genre": "—",  # Future metadata extraction
            "bpm": str(round(track.bpm)) if track.bpm else "—",
            "key": track.key_camelot or "—",
            "energy": int(track.energy) if track.energy is not None else None,
            "duration": track.duration, # Raw int for sorting
            "quality": "—",             # Placeholder for future extraction
            "format": format_str,
            "folder": folder,
            "path": file_path,
            "date_added": track.created_at.strftime("%Y-%m-%d"),
            "status": status,
            
            # Additional context panel fields
            "bitrate": "—",             # Needs mutagen extraction in future
            "samplerate": "—",          # Needs mutagen extraction in future
            "filesize": filesize
        }

    @staticmethod
    def to_presentation_list(tracks: List[Track]) -> List[Dict[str, Any]]:
        """Optimized bulk mapping."""
        return [TrackPresentationMapper.to_presentation(t) for t in tracks]
