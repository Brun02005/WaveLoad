"""
services/filename_cleaner_service.py
=====================================
Recovers artist/title/year from tracks whose metadata is just a mangled
filename — files ripped by web tools (klickaud.co and friends) arrive with
no ID3 title/artist at all, only a name like::

    1994_-_Tyree_Cooper_-_Acid_Over_Remix_by_Paul_Oakenfold_KLICKAUD

Parsing is deliberately conservative: it only reports what is unambiguously
present in the name. A wrong "fix" is worse than no fix, because it silently
corrupts identity for duplicate detection, sets and compatibility — so
anything uncertain is reported as such and left for a human to confirm.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

# Ripper watermarks seen in the wild, matched at the end of the name.
_WATERMARKS = ("klickaud", "y2mate", "ytmp3", "320kbps", "audiomack")

_SEPARATOR = " - "
_YEAR_PREFIX_RE = re.compile(r"^(19\d{2}|20\d{2})\s*-\s*")
# A trailing "mp3" glued onto the last word ("Extended_Mixmp3").
_GLUED_EXT_RE = re.compile(r"(?<=[a-z])mp3$", re.IGNORECASE)
# Windows' duplicate-file suffix, which can trail the watermark: "... KLICKAUD (1)".
_DUP_SUFFIX_RE = re.compile(r"\s*\(\d+\)$")


@dataclass(frozen=True)
class CleanedName:
    """Result of parsing one mangled name.

    ``confidence`` is 'high' when an artist/title separator was found,
    'medium' when only the title could be cleaned, and 'none' when the name
    needed no change at all.
    """
    original: str
    title: str
    artist: Optional[str]
    year: Optional[str]
    confidence: str

    @property
    def changed(self) -> bool:
        return self.confidence != "none"


def looks_mangled(title: str) -> bool:
    """True when a title looks like a raw ripper filename rather than a name."""
    if not title:
        return False
    lowered = title.lower()
    if any(mark in lowered for mark in _WATERMARKS):
        return True
    return title.count("_") >= 2


def _strip_watermarks(text: str) -> str:
    """Peel trailing watermarks and duplicate suffixes, in any order.

    They interleave in the wild — "... KLICKAUD (1)" puts Windows' duplicate
    marker after the watermark — so this loops until nothing more comes off.
    """
    changed = True
    while changed:
        changed = False
        stripped = _DUP_SUFFIX_RE.sub("", text).strip(" -_")
        if stripped != text.strip(" -_"):
            changed = True
        for mark in _WATERMARKS:
            if stripped.lower().endswith(mark):
                stripped = stripped[: -len(mark)]
                changed = True
                break
        text = stripped
    return text.strip(" -_")


def clean_name(raw: str) -> CleanedName:
    """Parse one mangled name into artist/title/year."""
    if not raw or not raw.strip():
        return CleanedName(raw, raw, None, None, "none")

    text = raw.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = _strip_watermarks(text)
    text = _GLUED_EXT_RE.sub("", text).strip()

    year = None
    year_match = _YEAR_PREFIX_RE.match(text)
    if year_match:
        year = year_match.group(1)
        text = text[year_match.end():].strip()

    artist = None
    confidence = "medium"
    if _SEPARATOR in text:
        left, _, right = text.partition(_SEPARATOR)
        left, right = left.strip(), right.strip()
        # Both sides must be non-empty and plausible for the split to mean
        # "artist - title"; otherwise keep the whole string as the title.
        if left and right:
            artist, text, confidence = left, right, "high"

    title = text.strip()
    if not title:
        return CleanedName(raw, raw, None, None, "none")

    if title == raw and artist is None and year is None:
        return CleanedName(raw, raw, None, None, "none")

    return CleanedName(raw, title, artist, year, confidence)


def plan_cleanup(rows: List[dict]) -> List[dict]:
    """Build a change plan for library rows.

    ``rows`` are dicts with at least ``id``, ``title`` and ``artist``.
    Returns one entry per row that would actually change, each carrying the
    proposed new values plus the parse confidence.
    """
    plan = []
    for row in rows:
        title = row.get("title") or ""
        if not looks_mangled(title):
            continue
        result = clean_name(title)
        if not result.changed:
            continue

        current_artist = (row.get("artist") or "").strip()
        artist_is_placeholder = current_artist.lower() in ("", "unknown", "desconocido")
        # Never overwrite an artist the user already has — only fill blanks.
        new_artist = result.artist if (result.artist and artist_is_placeholder) else None

        if result.title == title and new_artist is None:
            continue

        plan.append({
            "id": row.get("id"),
            "old_title": title,
            "new_title": result.title,
            "old_artist": row.get("artist"),
            "new_artist": new_artist,
            "year": result.year,
            "confidence": result.confidence,
        })
    return plan
