"""
services/stream_resolver_service.py
====================================
Resolves a yt-dlp-supported page URL to a direct, streamable audio URL
without downloading anything to disk. Used for in-app preview playback of
tracks that aren't in the local library yet (QMediaPlayer can play the
resolved URL directly — no ffmpeg piping needed).
"""

import logging
from typing import Optional

import yt_dlp

from domain.exceptions import UnsupportedFormatError
from services.cookie_service import cookie_service

logger = logging.getLogger(__name__)


class StreamResolverService:
    @classmethod
    def resolve_audio_url(cls, url: str) -> str:
        """Blocking. Call off the UI thread (see workers/stream_resolve_worker.py)."""
        cookie_file = cookie_service.get_cookie_file()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "android", "tv"],
                }
            },
        }
        if cookie_file:
            opts["cookiefile"] = cookie_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise UnsupportedFormatError(f"yt-dlp returned no info for: {url}")

                if "entries" in info:
                    info = next(iter(info["entries"]), None)
                    if info is None:
                        raise UnsupportedFormatError("Empty playlist.")

                formats: list = info.get("formats", [])
                audio_formats = [
                    f for f in formats if f.get("vcodec") == "none" and f.get("url")
                ] or [f for f in formats if f.get("url")]

                if not audio_formats:
                    direct_url: Optional[str] = info.get("url")
                    if not direct_url:
                        raise UnsupportedFormatError("No direct stream URL found for this content.")
                    return direct_url

                best = max(audio_formats, key=lambda f: f.get("abr") or f.get("tbr") or 0)
                return best["url"]

        except (UnsupportedFormatError,):
            raise
        except yt_dlp.utils.DownloadError as exc:
            raise UnsupportedFormatError(f"yt-dlp error: {exc}", cause=exc) from exc
        except Exception as exc:
            raise UnsupportedFormatError(f"Unexpected error resolving stream URL: {exc}", cause=exc) from exc
