"""
services/spotify_resolver.py
=============================
Resolves a Spotify TRACK link to a matching YouTube URL, so the rest of the
download pipeline (which only ever speaks yt-dlp) never needs to know
Spotify exists. Spotify's own audio is DRM-protected and cannot be
downloaded or streamed outside their official clients — this module only
reads the public embed page's metadata (title/artists/duration), then finds
the best-matching public YouTube upload.

The official Web API is deliberately NOT used: Spotify now requires the app
owner to hold an active Premium subscription for catalog endpoints (they
return 403 otherwise), which would mean every person running a build of this
app needed their own Premium account and API keys. The public embed page
carries the same fields and needs no credentials.
"""

import asyncio
import difflib
import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import yt_dlp

from core.utils import clean_title
from domain.exceptions import SpotifyResolutionError

logger = logging.getLogger(__name__)

SPOTIFY_TRACK_URL_RE = re.compile(r"open\.spotify\.com/(?:intl-\w+/)?track/([a-zA-Z0-9]+)")

_EMBED_URL = "https://open.spotify.com/embed/track/{track_id}"
_EMBED_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_NAME_RE = re.compile(r'"name":"(.*?)","uri":"spotify:track:')
_ARTISTS_RE = re.compile(r'"artists":(\[.*?\])')
_DURATION_RE = re.compile(r'"duration":(\d+)')
_YEAR_RE = re.compile(r'"releaseDate":\{"isoString":"(\d{4})')
_COVER_RE = re.compile(r'"url":"(https://[^"]*?image[^"]*?)"')

# Matching thresholds/weights — tuned to prefer a confident "no match" over a
# wrong one, since a bad match means downloading (and hearing) the wrong song.
DURATION_WINDOW_SECONDS = 15
WEIGHT_TITLE = 0.50
WEIGHT_DURATION = 0.35
ARTIST_BONUS = 0.15
PENALTY_PER_TERM = 0.25
MIN_ACCEPT_SCORE = 0.55
BLACKLIST_TERMS = (
    "cover", "8d audio", "sped up", "nightcore", "karaoke",
    "reaction", "slowed", "instrumental", "remix",
)


def is_spotify_track_url(url: str) -> bool:
    return bool(SPOTIFY_TRACK_URL_RE.search(url or ""))


def _extract_track_id(url: str) -> str:
    match = SPOTIFY_TRACK_URL_RE.search(url or "")
    if not match:
        raise SpotifyResolutionError("El enlace no es un link de track de Spotify válido.")
    return match.group(1)


def parse_embed_html(html: str) -> Dict[str, Any]:
    """Pull title/artists/duration/year/cover out of a Spotify embed page."""
    name_match = _NAME_RE.search(html)
    if not name_match:
        raise SpotifyResolutionError("No se pudo leer la información de la canción en Spotify.")

    artists: List[str] = []
    artists_match = _ARTISTS_RE.search(html)
    if artists_match:
        try:
            artists = [a["name"] for a in json.loads(artists_match.group(1)) if a.get("name")]
        except (ValueError, KeyError, TypeError):
            artists = []

    duration_match = _DURATION_RE.search(html)
    year_match = _YEAR_RE.search(html)
    cover_match = _COVER_RE.search(html)

    return {
        "title": _unescape_json_text(name_match.group(1)),
        "artists": [_unescape_json_text(a) for a in artists] or ["Desconocido"],
        "duration_ms": int(duration_match.group(1)) if duration_match else 0,
        "year": year_match.group(1) if year_match else None,
        "cover_url": cover_match.group(1) if cover_match else None,
    }


def _unescape_json_text(text: str) -> str:
    try:
        return json.loads(f'"{text}"')
    except ValueError:
        return text


async def _fetch_track(track_id: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
    url = _EMBED_URL.format(track_id=track_id)
    try:
        async with session.get(url, headers=_EMBED_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 404:
                raise SpotifyResolutionError("No se encontró esa canción en Spotify.")
            if resp.status != 200:
                raise SpotifyResolutionError(f"Error de Spotify al buscar la canción (código {resp.status}).")
            html = await resp.text()
    except aiohttp.ClientError as e:
        raise SpotifyResolutionError("No se pudo conectar con Spotify.") from e

    return parse_embed_html(html)


def _search_youtube_candidates_sync(query: str, count: int = 8) -> List[dict]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{query}", download=False)
    if not info:
        return []
    return [e for e in info.get("entries", []) if e]


async def _search_youtube_candidates(query: str, count: int = 8) -> List[dict]:
    return await asyncio.to_thread(_search_youtube_candidates_sync, query, count)


def _normalize_for_match(text: str) -> str:
    text = _flatten(text)
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)
    text = re.sub(r"\bfeat\.?\b|\bft\.?\b", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _flatten(text: str) -> str:
    """Lowercase + strip diacritics, KEEPING bracketed content — blacklist
    terms on YouTube almost always live in brackets ("(Karaoke Version)",
    "[8D AUDIO]"), so penalties must be checked before brackets are dropped."""
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def score_youtube_candidate(
    spotify_title: str,
    spotify_artists: List[str],
    spotify_duration_ms: int,
    candidate_title: str,
    candidate_duration_sec: Optional[float],
) -> float:
    expected = _normalize_for_match(f"{spotify_artists[0] if spotify_artists else ''} {spotify_title}")
    cand_norm = _normalize_for_match(candidate_title)

    title_sim = difflib.SequenceMatcher(None, expected, cand_norm).ratio()

    artist_bonus = 0.0
    for artist in spotify_artists:
        norm_artist = _normalize_for_match(artist)
        if norm_artist and norm_artist in cand_norm:
            artist_bonus = ARTIST_BONUS
            break

    if candidate_duration_sec is None:
        duration_score = 0.0
    else:
        diff = abs(candidate_duration_sec - spotify_duration_ms / 1000)
        duration_score = max(0.0, 1.0 - diff / DURATION_WINDOW_SECONDS)

    cand_flat = _flatten(candidate_title)
    spotify_flat = _flatten(spotify_title)
    penalty = 0.0
    for term in BLACKLIST_TERMS:
        if term in cand_flat and term not in spotify_flat:
            penalty += PENALTY_PER_TERM

    score = (WEIGHT_TITLE * title_sim) + (WEIGHT_DURATION * duration_score) + artist_bonus - penalty
    return max(0.0, min(1.0, score))


def find_best_youtube_match(
    spotify_title: str,
    spotify_artists: List[str],
    spotify_duration_ms: int,
    candidates: List[dict],
) -> Tuple[Optional[dict], float]:
    best_entry: Optional[dict] = None
    best_score = 0.0
    for entry in candidates:
        if not entry or not entry.get("title"):
            continue
        score = score_youtube_candidate(
            spotify_title, spotify_artists, spotify_duration_ms,
            entry["title"], entry.get("duration"),
        )
        if score > best_score:
            best_entry, best_score = entry, score

    if best_entry is None or best_score < MIN_ACCEPT_SCORE:
        return None, best_score
    return best_entry, best_score


def _entry_to_youtube_url(entry: dict) -> str:
    url = entry.get("url") or entry.get("webpage_url")
    if not url and entry.get("id"):
        url = f"https://www.youtube.com/watch?v={entry['id']}"
    if not url:
        raise SpotifyResolutionError("No se pudo construir la URL del video de YouTube encontrado.")
    return url


async def resolve_spotify_url_async(url: str) -> Dict[str, Any]:
    """Resolve a Spotify track URL to a MetadataService-shaped dict pointing
    at the best-matching YouTube video. Raises SpotifyResolutionError on any
    failure (track not found, no confident match)."""
    track_id = _extract_track_id(url)

    async with aiohttp.ClientSession() as session:
        track = await _fetch_track(track_id, session)

        title = track["title"]
        artists = track["artists"]
        duration_ms = track["duration_ms"]
        cover_url = track["cover_url"]
        year = track["year"]

        query = f"{artists[0]} {title}"
        candidates = await _search_youtube_candidates(query)

    best, score = find_best_youtube_match(title, artists, duration_ms, candidates)
    if best is None:
        raise SpotifyResolutionError(
            "No se encontró un video de YouTube que coincida con esta canción de Spotify."
        )

    logger.info("Spotify resolve: '%s - %s' -> '%s' (score=%.2f)", artists[0], title, best.get("title"), score)

    duration_sec = round(duration_ms / 1000) if duration_ms else 0

    return {
        "url": _entry_to_youtube_url(best),
        "is_playlist": False,
        "title": clean_title(f"{artists[0]} - {title}"),
        "artist": artists[0],
        "uploader": best.get("channel") or best.get("uploader") or "YouTube",
        "thumbnail_path": None,
        "thumbnail_url": cover_url or best.get("thumbnail"),
        "duration": duration_sec,
        "estimated_size_mb": (duration_sec * 40000) / (1024 * 1024),
        "year": year,
        "source_platform": "spotify",
    }


def resolve_spotify_url_sync(url: str) -> Dict[str, Any]:
    """Sync entry point — only safe on a thread with no running event loop
    (e.g. a QRunnable worker thread). Never call from BackgroundValidator's
    dedicated always-running asyncio loop thread; await the async version
    there instead."""
    return asyncio.run(resolve_spotify_url_async(url))
