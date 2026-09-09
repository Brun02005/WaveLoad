import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from core.config import BASE_DIR, ensure_writable_dir

LOG_DIR = BASE_DIR / "logs"
# Tolerant: this runs at import time, so raising here would crash the app
# before it can report the problem. BASE_DIR is already write-verified.
ensure_writable_dir(LOG_DIR)

APP_LOG_FILE = LOG_DIR / "waveload_app.log"
DOWNLOAD_LOG_FILE = LOG_DIR / "waveload_downloads.log"
ERROR_LOG_FILE = LOG_DIR / "waveload_errors.log"

# Define formats
APP_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DOWNLOAD_FORMAT = "%(asctime)s [%(levelname)s] [Worker-%(threadName)s] %(name)s: %(message)s"

def setup_logging():
    # Base configuration for root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Prevent duplicating handlers if setup_logging is called multiple times
    if root_logger.handlers:
        return

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(APP_FORMAT))
    root_logger.addHandler(console_handler)

    # Application Log Handler
    app_handler = RotatingFileHandler(APP_LOG_FILE, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(logging.Formatter(APP_FORMAT))
    root_logger.addHandler(app_handler)

    # Error Log Handler
    error_handler = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(APP_FORMAT))
    root_logger.addHandler(error_handler)

def get_download_logger(name: str) -> logging.Logger:
    """Returns a logger specifically configured for download activity."""
    logger = logging.getLogger(f"download.{name}")
    logger.propagate = False  # Avoid duplicating to root logger

    if not logger.handlers:
        dl_handler = RotatingFileHandler(DOWNLOAD_LOG_FILE, maxBytes=10*1024*1024, backupCount=3, encoding="utf-8")
        dl_handler.setLevel(logging.DEBUG)
        dl_handler.setFormatter(logging.Formatter(DOWNLOAD_FORMAT))
        logger.addHandler(dl_handler)
        
        # Also log errors to the main error log
        err_handler = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
        err_handler.setLevel(logging.ERROR)
        err_handler.setFormatter(logging.Formatter(DOWNLOAD_FORMAT))
        logger.addHandler(err_handler)

    return logger
