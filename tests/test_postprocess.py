"""La conversión a MP3: qué comando se arma y qué pasa cuando falla."""

from pathlib import Path

import pytest

import core.config as config
from core.scheduler import Scheduler
from domain.models import DownloadItem
from workers.postprocess_worker import PostProcessWorker


def _item(tmp_path) -> DownloadItem:
    return DownloadItem(id="u", url="https://example.com/x", title="Tema", output_dir=tmp_path)


def test_the_bitrate_chosen_in_settings_reaches_ffmpeg(tmp_path):
    # Antes el comando decía 320k siempre, eligiera lo que eligiera el usuario.
    worker = PostProcessWorker(_item(tmp_path), str(tmp_path / "in.webm"), bitrate="192")
    cmd = worker._build_ffmpeg_cmd(tmp_path / "Tema.mp3")
    assert cmd[cmd.index("-b:a") + 1] == "192k"


def test_the_default_bitrate_is_320(tmp_path):
    worker = PostProcessWorker(_item(tmp_path), str(tmp_path / "in.webm"))
    cmd = worker._build_ffmpeg_cmd(tmp_path / "Tema.mp3")
    assert cmd[cmd.index("-b:a") + 1] == "320k"


def test_the_scheduler_rejects_a_bitrate_it_does_not_know():
    scheduler = Scheduler.__new__(Scheduler)  # sin QTimer: sólo la validación
    scheduler.configure("999", use_browser_auth=False)
    assert scheduler.audio_quality == "320"
    assert scheduler.use_browser_auth is False


def test_ffmpeg_comes_from_the_bundle_when_frozen(tmp_path, monkeypatch):
    # En el .exe onefile ffmpeg vive en _MEIPASS, que no está en el PATH.
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert config.ffmpeg_executable() == str(tmp_path / "ffmpeg.exe")


def test_ffmpeg_falls_back_to_the_path_in_development(monkeypatch):
    monkeypatch.delattr(config.sys, "_MEIPASS", raising=False)
    assert config.ffmpeg_executable() == "ffmpeg"


def test_a_missing_ffmpeg_is_reported_once_not_retried(tmp_path, monkeypatch):
    worker = PostProcessWorker(_item(tmp_path), str(tmp_path / "in.webm"))
    monkeypatch.setattr(config, "ffmpeg_executable", lambda: str(tmp_path / "no-existe.exe"))
    with pytest.raises(Exception, match="FFmpeg no está instalado"):
        worker._convert_to_mp3(tmp_path / "Tema.mp3")


def test_a_failed_conversion_does_not_leave_a_partial_mp3(tmp_path, monkeypatch):
    # Un MP3 a medias se marcaba como "duplicado" en la tanda siguiente.
    salida = tmp_path / "Tema.mp3"

    class FakeProcess:
        returncode = 1

        def communicate(self):
            salida.write_bytes(b"medio archivo")
            return b"", b"Conversion failed!"

    monkeypatch.setattr("workers.postprocess_worker.subprocess.Popen", lambda *a, **k: FakeProcess())
    worker = PostProcessWorker(_item(tmp_path), str(tmp_path / "in.webm"))
    with pytest.raises(Exception):
        worker._convert_to_mp3(salida)
    assert not salida.exists()


def test_a_file_that_was_already_there_is_never_deleted(tmp_path, monkeypatch):
    salida = tmp_path / "Tema.mp3"
    salida.write_bytes(b"del usuario")

    class FakeProcess:
        returncode = 1

        def communicate(self):
            return b"", b"Conversion failed!"

    monkeypatch.setattr("workers.postprocess_worker.subprocess.Popen", lambda *a, **k: FakeProcess())
    worker = PostProcessWorker(_item(tmp_path), str(tmp_path / "in.webm"))
    with pytest.raises(Exception):
        worker._convert_to_mp3(salida)
    assert salida.read_bytes() == b"del usuario"
