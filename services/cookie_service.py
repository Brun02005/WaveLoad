import logging
import threading
from typing import Optional

from infrastructure.browser_auth import get_cookies_for_ytdlp, cleanup_cookie_file

logger = logging.getLogger(__name__)

class CookieService:
    """
    Manages a single browser cookie session for a batch of downloads.
    Ensures that browser databases are only accessed once per session
    to prevent concurrent access errors and locked DBs.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(CookieService, cls).__new__(cls)
                    cls._instance._cookie_file_path = None
                    cls._instance._is_initialized = False
        return cls._instance

    def initialize_session(self, url: str) -> Optional[str]:
        """
        Attempts to extract cookies for the given URL domain.
        If already initialized, returns the existing cookie file path.
        Returns None if extraction fails.
        """
        with self._lock:
            if self._is_initialized:
                return self._cookie_file_path

            logger.info("Initializing cookie session...")
            try:
                self._cookie_file_path = get_cookies_for_ytdlp(url)
                self._is_initialized = True
                if self._cookie_file_path:
                    logger.info(f"Cookie session initialized successfully: {self._cookie_file_path}")
                else:
                    logger.warning("Cookie session initialized but no cookies found. Proceeding without cookies.")
            except Exception as e:
                logger.error(f"Failed to initialize cookie session: {e}")
                self._cookie_file_path = None
                self._is_initialized = True # Mark as initialized to prevent repeated failed attempts

            return self._cookie_file_path

    def get_cookie_file(self) -> Optional[str]:
        """Returns the current cookie file path if initialized."""
        with self._lock:
            return self._cookie_file_path

    def cleanup_session(self):
        """Cleans up the temporary cookie file."""
        with self._lock:
            if self._cookie_file_path:
                logger.info("Cleaning up cookie session...")
                cleanup_cookie_file(self._cookie_file_path)
                self._cookie_file_path = None
            self._is_initialized = False

# Global instance
cookie_service = CookieService()
