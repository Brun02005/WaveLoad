import logging
from pathlib import Path
from PySide6.QtCore import QObject, QSettings, Signal
from core.config import ensure_writable_dir, resolve_download_dir

logger = logging.getLogger(__name__)

class SettingsService(QObject):
    """
    Centralized service for managing all application settings.
    Handles storage (QSettings), validation, and runtime change notifications.
    """
    setting_changed = Signal(str, object)  # key, new_value

    def __init__(self):
        super().__init__()
        self.settings = QSettings("WaveLoad", "WaveLoadv3")
        logger.info("Downloads will be saved to: %s", self.get_output_dir())

    def get_output_dir(self) -> Path:
        """Returns the folder downloads go to, creating it.

        The user's saved choice wins; if it's gone or no longer writable
        (external drive unplugged, folder deleted, settings carried over to a
        different machine) this falls back to the Desktop rather than failing
        every download.
        """
        saved_value = self.settings.value("output_dir", None)
        saved = Path(saved_value) if saved_value else None

        resolved = resolve_download_dir(saved)
        if saved is not None and resolved != saved:
            logger.warning(
                "Saved output directory '%s' is not writable; using '%s' instead.",
                saved, resolved,
            )
        return resolved

    def set_output_dir(self, path_str: str) -> bool:
        """
        Validates, creates (if needed), and persists the output directory.
        Returns True if successful, False if invalid or inaccessible.
        """
        try:
            path = Path(path_str).resolve()
        except OSError as e:
            logger.error(f"Invalid output directory '{path_str}': {e}")
            return False

        if not ensure_writable_dir(path):
            logger.error(f"Output directory '{path}' is not writable.")
            return False

        self.settings.setValue("output_dir", str(path))
        self.setting_changed.emit("output_dir", path)
        logger.info(f"Output directory updated to: {path}")
        return True

    def get_audio_quality(self) -> str:
        return self.settings.value("audio_quality", "320")

    def set_audio_quality(self, quality: str):
        self.settings.setValue("audio_quality", quality)
        self.setting_changed.emit("audio_quality", quality)

    def get_use_cookies(self) -> bool:
        # Defaults to True
        return self.settings.value("use_browser_auth", "true") == "true"

    def set_use_cookies(self, enabled: bool):
        val = "true" if enabled else "false"
        self.settings.setValue("use_browser_auth", val)
        self.setting_changed.emit("use_browser_auth", enabled)

    def get_auto_open_folder(self) -> bool:
        # Defaults to True
        return self.settings.value("auto_open_folder", "true") == "true"

    def set_auto_open_folder(self, enabled: bool):
        val = "true" if enabled else "false"
        self.settings.setValue("auto_open_folder", val)
        self.setting_changed.emit("auto_open_folder", enabled)
