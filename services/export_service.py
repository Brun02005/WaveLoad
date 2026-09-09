"""
services/export_service.py
==========================
Exports a generated set (ordered list of SetStep) to formats DJ software reads:
an extended M3U8 playlist and a rekordbox-compatible XML collection+playlist.
Pure/Qt-free string builders.
"""

import xml.sax.saxutils as _sx
from typing import List
from urllib.parse import quote


def build_m3u8(steps: List) -> str:
    """Extended M3U8 preserving set order. `steps` are SetStep objects."""
    lines = ["#EXTM3U"]
    for s in steps:
        t = s.track
        dur = int(t.get("duration") or 0)
        artist = (t.get("artist") or "").strip()
        title = (t.get("title") or "").strip()
        lines.append(f"#EXTINF:{dur},{artist} - {title}")
        lines.append(t.get("path") or "")
    return "\n".join(lines) + "\n"


def _rekordbox_location(path: str) -> str:
    """rekordbox Location = file://localhost/ + URL-encoded absolute path."""
    if not path:
        return ""
    p = path.replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p                       # Windows drive path -> /C:/...
    return "file://localhost" + quote(p, safe="/:")   # rekordbox keeps the drive ':'


def build_rekordbox_xml(steps: List, name: str = "WaveLoad Set") -> str:
    """rekordbox XML with a COLLECTION and a single ordered PLAYLIST node."""
    tracks_xml = []
    refs_xml = []
    for i, s in enumerate(steps, start=1):
        t = s.track
        key = t.get("key") or ""
        if key == "—":
            key = ""
        bpm = t.get("bpm") or ""
        try:
            avg_bpm = f"{float(bpm):.2f}"
        except (ValueError, TypeError):
            avg_bpm = "0.00"
        dur = int(t.get("duration") or 0)
        tracks_xml.append(
            f'    <TRACK TrackID="{i}" '
            f'Name={_sx.quoteattr(t.get("title") or "")} '
            f'Artist={_sx.quoteattr(t.get("artist") or "")} '
            f'TotalTime="{dur}" '
            f'AverageBpm="{avg_bpm}" '
            f'Tonality={_sx.quoteattr(key)} '
            f'Location={_sx.quoteattr(_rekordbox_location(t.get("path") or ""))}/>'
        )
        refs_xml.append(f'      <TRACK Key="{i}"/>')

    n = len(steps)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DJ_PLAYLISTS Version="1.0.0">\n'
        '  <PRODUCT Name="WaveLoad" Version="3.0" Company="WaveLoad"/>\n'
        f'  <COLLECTION Entries="{n}">\n'
        + "\n".join(tracks_xml) + "\n"
        '  </COLLECTION>\n'
        '  <PLAYLISTS>\n'
        '    <NODE Type="0" Name="ROOT" Count="1">\n'
        f'      <NODE Name={_sx.quoteattr(name)} Type="1" KeyType="0" Entries="{n}">\n'
        + "\n".join(refs_xml) + "\n"
        '      </NODE>\n'
        '    </NODE>\n'
        '  </PLAYLISTS>\n'
        '</DJ_PLAYLISTS>\n'
    )
