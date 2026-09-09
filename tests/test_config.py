import os
import sys

import pytest

import core.config as cfg


# --------------------------------------------------------------------------
# Writability probe
# --------------------------------------------------------------------------

def test_ensure_writable_dir_creates_and_confirms(tmp_path):
    target = tmp_path / "nested" / "downloads"
    assert cfg.ensure_writable_dir(target) is True
    assert target.is_dir()
    # The probe file must not be left behind.
    assert list(target.iterdir()) == []


def test_ensure_writable_dir_returns_false_instead_of_raising(tmp_path):
    """Regression: a bare mkdir() at import time crashed the frozen app with
    'PermissionError: [WinError 5]' before it could report anything. The probe
    must report failure, never raise."""
    blocker = tmp_path / "a_file"
    blocker.write_text("not a directory")

    assert cfg.ensure_writable_dir(blocker / "downloads") is False


# --------------------------------------------------------------------------
# Internal data location (library DB, cache, logs)
# --------------------------------------------------------------------------

def test_resolve_base_dir_falls_back_when_preferred_is_unusable(tmp_path, monkeypatch):
    """Regression: WaveLoad crashed on any PC where the folder holding the .exe
    refused writes (Controlled Folder Access, restricted Desktop). It must fall
    back to a writable location instead."""
    blocker = tmp_path / "a_file"
    blocker.write_text("not a directory")
    unusable = blocker / "WaveLoad"
    fallback = tmp_path / "fallback"

    monkeypatch.setattr(cfg, "_preferred_base_dir", lambda: unusable)
    monkeypatch.setattr(cfg, "_fallback_base_dirs", lambda: [fallback])

    assert cfg._resolve_base_dir() == fallback
    assert fallback.is_dir()


def test_resolve_base_dir_prefers_the_exe_folder_when_writable(tmp_path, monkeypatch):
    """Portable behaviour must be preserved: when the folder next to the .exe
    is writable, data stays there rather than in a user folder."""
    preferred = tmp_path / "next_to_exe"
    fallback = tmp_path / "fallback"

    monkeypatch.setattr(cfg, "_preferred_base_dir", lambda: preferred)
    monkeypatch.setattr(cfg, "_fallback_base_dirs", lambda: [fallback])

    assert cfg._resolve_base_dir() == preferred
    assert not fallback.exists()


def test_fallback_dirs_are_absolute_and_user_scoped():
    candidates = cfg._fallback_base_dirs()
    assert candidates, "there must be at least one fallback location"
    for path in candidates:
        assert path.is_absolute()
        assert path.name == cfg.APP_FOLDER_NAME


# --------------------------------------------------------------------------
# Download location — the user's own music files
# --------------------------------------------------------------------------

def test_downloads_default_to_the_desktop(tmp_path, monkeypatch):
    """Songs must land on the Desktop, where the user can actually find them."""
    desktop = tmp_path / "Desktop"
    music = tmp_path / "Music"
    monkeypatch.setattr(cfg, "_user_folder", lambda fid, name: tmp_path / name)
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path / "appdata")

    resolved = cfg.resolve_download_dir()

    assert resolved == desktop / cfg.APP_FOLDER_NAME
    assert resolved.is_dir()
    assert not (music / cfg.APP_FOLDER_NAME).exists()


def test_downloads_fall_back_to_music_when_desktop_is_blocked(tmp_path, monkeypatch):
    """If the Desktop refuses writes (Controlled Folder Access), songs go to
    Music — still a visible, permanent place."""
    blocker = tmp_path / "blocked_desktop"
    blocker.write_text("not a directory")

    def fake_user_folder(folder_id, name):
        return blocker if name == "Desktop" else tmp_path / name

    monkeypatch.setattr(cfg, "_user_folder", fake_user_folder)
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path / "appdata")

    assert cfg.resolve_download_dir() == tmp_path / "Music" / cfg.APP_FOLDER_NAME


def test_user_chosen_folder_wins_over_the_desktop(tmp_path, monkeypatch):
    """A folder the user picked themselves must always take precedence."""
    chosen = tmp_path / "mi carpeta"
    monkeypatch.setattr(cfg, "_user_folder", lambda fid, name: tmp_path / name)
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path / "appdata")

    assert cfg.resolve_download_dir(chosen) == chosen
    # The Desktop default must not be created behind the user's back.
    assert not (tmp_path / "Desktop" / cfg.APP_FOLDER_NAME).exists()


def test_unusable_user_folder_falls_back_to_the_desktop(tmp_path, monkeypatch):
    """Regression: an unplugged drive or deleted folder used to make every
    download fail; it must degrade to the default instead."""
    blocker = tmp_path / "a_file"
    blocker.write_text("not a directory")
    monkeypatch.setattr(cfg, "_user_folder", lambda fid, name: tmp_path / name)
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path / "appdata")

    resolved = cfg.resolve_download_dir(blocker / "gone")

    assert resolved == tmp_path / "Desktop" / cfg.APP_FOLDER_NAME


def test_importing_config_creates_no_download_folder(tmp_path, monkeypatch):
    """OUTPUT_DIR is only a default. Creating it at import time would litter
    the Desktop of users who chose their own folder."""
    monkeypatch.setattr(cfg, "_user_folder", lambda fid, name: tmp_path / name)
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path / "appdata")

    assert cfg._download_dir_candidates()[0] == tmp_path / "Desktop" / cfg.APP_FOLDER_NAME
    assert not (tmp_path / "Desktop").exists()


def test_downloads_never_default_into_appdata():
    """The user's music must never be hidden away in AppData: it reads as
    temporary and gets wiped by cleanup tools."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        pytest.skip("LOCALAPPDATA not set on this machine")

    for candidate in cfg._download_dir_candidates():
        assert local_appdata.lower() not in str(candidate).lower(), (
            f"download candidate {candidate} lives inside AppData"
        )


def test_download_dir_is_separate_from_internal_data():
    """Songs and the library DB must not share a folder, so that relocating
    one never drags the other along."""
    assert cfg._download_dir_candidates()[0] != cfg.BASE_DIR


# --------------------------------------------------------------------------
# Windows known folders
# --------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only shell API")
def test_known_folders_resolve_to_real_directories():
    """Regression: Path.home()/'Desktop' is wrong whenever OneDrive redirects
    the Desktop — that path does not exist, so downloads would land in an
    invisible folder. The shell API must return the real one."""
    for folder_id in (cfg._FOLDERID_DESKTOP, cfg._FOLDERID_DOCUMENTS, cfg._FOLDERID_MUSIC):
        resolved = cfg._known_folder(folder_id)
        assert resolved is not None
        assert resolved.is_dir(), f"{resolved} should exist"


def test_user_folder_falls_back_when_lookup_fails(monkeypatch):
    monkeypatch.setattr(cfg, "_known_folder", lambda folder_id: None)
    assert cfg._user_folder("whatever", "Desktop").name == "Desktop"
