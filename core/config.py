import ctypes
import logging
import os
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

APP_NAME = "WaveLoad v3"
# Folder name used inside the user's Desktop / Documents / Music.
APP_FOLDER_NAME = "WaveLoad"

_logger = logging.getLogger(__name__)

# Windows "known folder" GUIDs. These are the only reliable way to locate the
# Desktop, Documents and Music folders: when OneDrive backs up a machine it
# redirects them (Desktop becomes ~/OneDrive/Desktop), so the obvious
# ``Path.home() / "Desktop"`` points at a path that does not even exist and
# would silently create a folder the user never sees.
_FOLDERID_DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
_FOLDERID_DOCUMENTS = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"
_FOLDERID_MUSIC = "4BD8D571-6D19-48D3-BE97-422220080E43"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


def _known_folder(folder_id: str) -> Path | None:
    """Resolve a Windows known folder via SHGetKnownFolderPath.

    Returns None off Windows or if the lookup fails, so callers fall back to a
    plain guess.
    """
    if sys.platform != "win32":
        return None

    try:
        raw = uuid.UUID(folder_id).bytes_le
        guid = _GUID(
            int.from_bytes(raw[0:4], "little"),
            int.from_bytes(raw[4:6], "little"),
            int.from_bytes(raw[6:8], "little"),
            (ctypes.c_byte * 8)(*raw[8:16]),
        )
        buffer = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(buffer)
        )
        if result != 0:
            return None
        try:
            return Path(buffer.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(buffer)
    except (OSError, AttributeError, ValueError):
        return None


def _user_folder(folder_id: str, fallback_name: str) -> Path:
    """A known folder, or a best-effort guess under the home directory."""
    resolved = _known_folder(folder_id)
    return resolved if resolved is not None else Path.home() / fallback_name


def ensure_writable_dir(directory: Path) -> bool:
    """Create ``directory`` if needed and prove it is actually writable.

    Returns True on success, False if the directory can't be created or
    written to. Never raises — callers use it to choose a location rather
    than to crash.

    ``mkdir(exist_ok=True)`` alone doesn't prove writability: on Windows, a
    directory can exist and still refuse new files (e.g. Controlled Folder
    Access protecting Desktop/Documents from unrecognized apps, or a synced
    OneDrive folder with restricted permissions) — that only surfaces as a
    PermissionError once something is actually written inside it.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".waveload_write_test"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def _preferred_base_dir() -> Path:
    """Directory next to the executable (frozen) or the project root (dev).

    When frozen by PyInstaller, ``__file__`` points inside the ephemeral
    _MEIPASS extraction dir that is wiped on exit — so persistent data must
    instead live next to the executable (portable-app style). In dev, it's the
    project root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _fallback_base_dirs() -> list[Path]:
    """Safe locations to fall back to when the preferred directory (next to
    the .exe) is protected or read-only.
    """
    candidates = [_user_folder(_FOLDERID_DOCUMENTS, "Documents") / APP_FOLDER_NAME]

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / APP_FOLDER_NAME)

    candidates.append(_user_folder(_FOLDERID_MUSIC, "Music") / APP_FOLDER_NAME)
    return candidates


def _resolve_base_dir() -> Path:
    """Directory for internal data (library DB, session, cache, logs).

    Tries the preferred location first and only falls back if it genuinely
    can't be written to, so the app never depends on admin rights or a
    specific machine's folder permissions to start. This is NOT where
    downloaded music goes — see ``_resolve_download_dir``.
    """
    preferred = _preferred_base_dir()
    if ensure_writable_dir(preferred):
        return preferred

    candidates = _fallback_base_dirs()
    for candidate in candidates:
        if ensure_writable_dir(candidate):
            _logger.warning(
                "'%s' is not writable; using '%s' for WaveLoad data instead.",
                preferred, candidate,
            )
            return candidate

    raise PermissionError(
        "No writable location found for WaveLoad data. Tried: "
        + ", ".join(str(p) for p in [preferred, *candidates])
    )


def _download_dir_candidates() -> list[Path]:
    """Where downloaded music goes, best first.

    Deliberately kept separate from BASE_DIR and never pointed at AppData:
    songs are the user's own files, so they must land somewhere visible and
    permanent — a hidden AppData folder reads as temporary and gets wiped by
    cleanup tools.
    """
    return [
        _user_folder(_FOLDERID_DESKTOP, "Desktop") / APP_FOLDER_NAME,
        _user_folder(_FOLDERID_MUSIC, "Music") / APP_FOLDER_NAME,
        BASE_DIR / "mp3_downloads",
    ]


def resolve_download_dir(preferred: Path | None = None) -> Path:
    """Return a usable download folder, creating it.

    ``preferred`` is the user's own choice and always wins when it works.
    Otherwise this walks the default candidates (Desktop first) and falls back
    only when a location genuinely refuses writes.

    Nothing is created until this is called, so a user who picked their own
    folder never gets a stray empty one on their Desktop.
    """
    candidates = _download_dir_candidates()
    if preferred is not None:
        candidates.insert(0, preferred)

    for candidate in candidates:
        if ensure_writable_dir(candidate):
            return candidate

    # Downloads aren't needed to start the app and the UI lets the user pick
    # another folder, so report instead of raising.
    _logger.error(
        "No writable download folder found. Tried: %s",
        ", ".join(str(p) for p in candidates),
    )
    return candidates[0]


BASE_DIR = _resolve_base_dir()

# The default download folder as a plain path. Deliberately NOT created here —
# SettingsService.get_output_dir() resolves and creates the folder actually in
# use, which may be one the user picked instead.
OUTPUT_DIR = _download_dir_candidates()[0]

MAX_LINKS_PER_BATCH = 500

DEFAULT_WINDOW_WIDTH = 980
DEFAULT_WINDOW_HEIGHT = 680
MAX_CONCURRENT_DOWNLOADS = 5
