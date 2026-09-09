import atexit
import os
import logging
from typing import Set

logger = logging.getLogger(__name__)

_TEMP_FILES: Set[str] = set()

def register_temp_file(path: str):
    """Register a temporary file to be deleted on application exit."""
    _TEMP_FILES.add(path)
    logger.debug(f"Registered temp file: {path}")

def cleanup_temp_files():
    """Delete all registered temporary files."""
    for path in _TEMP_FILES:
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.debug(f"Cleaned up temp file: {path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp file {path}: {e}")

# Ensure cleanup happens when python exits normally
atexit.register(cleanup_temp_files)
