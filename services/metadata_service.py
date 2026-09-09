import logging
import yt_dlp
import urllib.request
import tempfile
import asyncio
import aiohttp
import json
import re
from typing import Dict, Any, Optional

from storage.cache_store import metadata_cache
from services.cookie_service import cookie_service
from services.spotify_resolver import is_spotify_track_url, resolve_spotify_url_async, resolve_spotify_url_sync
from core.utils import friendly_error_message, clean_title
from core.temp_registry import register_temp_file

logger = logging.getLogger(__name__)

# Regex to extract the ytInitialPlayerResponse from youtube html
YT_INITIAL_PLAYER_RE = re.compile(r"ytInitialPlayerResponse\s*=\s*({.+?})\s*;\s*(?:var\s+meta|<\/script|\n)")

class MetadataService:
    """
    Service for extracting metadata from URLs.
    Uses caching and asynchronous I/O to avoid repeated API requests to YouTube.
    """

    @classmethod
    async def extract_metadata_async(cls, url: str) -> Dict[str, Any]:
        """
        Fully asynchronous metadata extraction. Fast path for YouTube videos.
        Uses aiohttp. Falls back to yt-dlp in a background thread if it fails.
        """
        cached_data = metadata_cache.get(url)
        if cached_data:
            logger.debug(f"Metadata cache hit for: {url}")
            return cached_data

        logger.debug(f"Async metadata cache miss for: {url}. Extracting from source...")

        if is_spotify_track_url(url):
            metadata = await resolve_spotify_url_async(url)
            metadata_cache.set(url, metadata)
            return metadata

        if "youtube.com/watch" in url or "youtu.be/" in url:
            # Fast path
            try:
                metadata = await cls._fast_youtube_extract(url)
                if metadata:
                    metadata_cache.set(url, metadata)
                    return metadata
            except Exception as e:
                logger.debug(f"Fast path failed for {url}, falling back to yt-dlp: {e}")

        # Slow path (yt-dlp)
        metadata = await asyncio.to_thread(cls.extract_metadata, url)
        return metadata

    @classmethod
    async def _fast_youtube_extract(cls, url: str) -> Optional[Dict[str, Any]]:
        """Fast extraction directly from YouTube HTML without yt-dlp."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return None
                html = await response.text()
                
        match = YT_INITIAL_PLAYER_RE.search(html)
        if not match:
            return None
            
        data = json.loads(match.group(1))
        
        playability = data.get("playabilityStatus", {}).get("status")
        if playability not in ("OK", "UNPLAYABLE", "LOGIN_REQUIRED"):
            # UNPLAYABLE or LOGIN_REQUIRED might mean it's private, but yt-dlp might handle it if we have cookies.
            # So if it's not OK, let's fallback to yt-dlp just in case.
            if playability != "OK":
                return None

        video_details = data.get("videoDetails")
        if not video_details:
            return None
            
        title = video_details.get("title", "Desconocido")
        uploader = video_details.get("author", "Canal Desconocido")
        duration_sec = int(video_details.get("lengthSeconds", "0"))
        
        thumbnails = video_details.get("thumbnail", {}).get("thumbnails", [])
        thumb_url = None
        if thumbnails:
            # Get the highest resolution thumbnail
            thumb_url = thumbnails[-1].get("url")
            # Usually ends with a query string like ?sqp=..., we can strip it for the base image
            if thumb_url and "?" in thumb_url:
                thumb_url = thumb_url.split("?")[0]
        
        metadata = {
            "url": url,
            "is_playlist": False,
            "title": clean_title(title),
            "uploader": uploader,
            "thumbnail_path": None,
            "duration": duration_sec,
            "estimated_size_mb": (duration_sec * 40000) / (1024 * 1024),
            "thumbnail_url": thumb_url,
            "year": None
        }

        # Download thumbnail asynchronously
        if thumb_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(thumb_url, timeout=5) as resp:
                        if resp.status == 200:
                            img_data = await resp.read()
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
                                f.write(img_data)
                                metadata["thumbnail_path"] = f.name
                                register_temp_file(f.name)
            except Exception as e:
                logger.debug(f"Async thumbnail download failed: {e}")

        return metadata

    @classmethod
    def extract_metadata(cls, url: str) -> Dict[str, Any]:
        """
        Synchronous metadata extraction using yt-dlp.
        """
        cached_data = metadata_cache.get(url)
        if cached_data:
            return cached_data

        if is_spotify_track_url(url):
            metadata = resolve_spotify_url_sync(url)
            metadata_cache.set(url, metadata)
            return metadata

        cookie_file = cookie_service.get_cookie_file()
        
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "android", "tv"]
                }
            }
        }
        if cookie_file:
            opts["cookiefile"] = cookie_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("No se pudo obtener información del enlace.")

                is_playlist = info.get("_type") == "playlist" or "entries" in info
                
                metadata = {
                    "url": url,
                    "is_playlist": is_playlist,
                    "title": clean_title(info.get("title", "Desconocido")),
                    "uploader": info.get("uploader") or info.get("playlist_uploader") or "Canal Desconocido",
                    "thumbnail_path": None,
                    "duration": 0,
                    "estimated_size_mb": 0.0,
                    "thumbnail_url": None,
                    "year": None
                }

                upload_date = info.get("upload_date", "")
                if upload_date:
                    metadata["year"] = upload_date[:4]

                thumb_url = info.get("thumbnail")
                if not thumb_url and is_playlist and info.get("entries"):
                    first_entry = info["entries"][0]
                    if first_entry:
                        thumb_url = first_entry.get("thumbnail")
                        
                metadata["thumbnail_url"] = thumb_url

                if thumb_url:
                    try:
                        with urllib.request.urlopen(thumb_url, timeout=5) as response:
                            data = response.read()
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
                                f.write(data)
                                metadata["thumbnail_path"] = f.name
                                register_temp_file(f.name)
                    except Exception as e:
                        logger.debug(f"Failed to download thumbnail for {url}: {e}")

                if is_playlist:
                    entries = info.get("entries", [])
                    metadata["track_count"] = len(entries)
                    
                    total_dur = 0
                    track_urls = []
                    for entry in entries:
                        if entry:
                            total_dur += entry.get("duration") or 0
                            entry_url = entry.get("url") or entry.get("webpage_url")
                            if not entry_url and entry.get("id"):
                                entry_url = f"https://www.youtube.com/watch?v={entry['id']}"
                            if entry_url:
                                track_urls.append((entry_url, entry.get("title", "Video")))
                                
                    metadata["duration"] = total_dur
                    metadata["entries"] = track_urls
                    metadata["estimated_size_mb"] = (total_dur * 40000) / (1024 * 1024)
                else:
                    duration = info.get("duration") or 0
                    metadata["duration"] = duration
                    metadata["estimated_size_mb"] = (duration * 40000) / (1024 * 1024)

                metadata_cache.set(url, metadata)
                return metadata

        except Exception as e:
            msg = friendly_error_message(str(e))
            logger.error(f"Metadata extraction failed for {url}: {msg}")
            raise Exception(msg)
