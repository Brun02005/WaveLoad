import logging
import yt_dlp
from typing import Callable, Optional

from services.cookie_service import cookie_service

logger = logging.getLogger(__name__)

class DownloadService:
    """
    Handles the execution of yt-dlp for downloading media.
    Separates the yt-dlp specific options from the worker thread.
    """
    
    @classmethod
    def download(
        cls, 
        url: str, 
        output_template: str, 
        audio_quality: str, 
        progress_hook: Callable[[dict], None],
        use_cookies: bool = True,
    ):
        """
        Executes the yt-dlp download process.
        """
        # Con las cookies apagadas en Ajustes no se toca ningún navegador.
        cookie_file = cookie_service.get_cookie_file() if use_cookies else None
        
        opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "windowsfilenames": True,
            "noplaylist": True,
            "extractor_args": {
                "youtube": {"player_client": ["web", "android", "tv"]}
            },
            "progress_hooks": [progress_hook],
            # Note: We do post-processing separately now, so NO ffmpeg here in yt-dlp 
            # We just download the best audio format.
        }
        if cookie_file:
            opts["cookiefile"] = cookie_file

        try:
            logger.debug(f"Starting download for {url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            err_text = str(e).lower()
            is_auth_error = any(p in err_text for p in (
                "sign in", "login required", "http error 403",
                "this video is only available",
            ))
            if cookie_file and is_auth_error:
                logger.warning(f"Auth error with cookies for {url}. Retrying without cookies...")
                opts["cookiefile"] = None
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            else:
                raise e
