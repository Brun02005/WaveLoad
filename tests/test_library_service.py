"""Quitar pistas, detectar archivos faltantes y ubicar archivos movidos."""

import uuid
from pathlib import Path

import pytest

from domain.tags import Tag, TagSource
from domain.track import AssetType, Track, TrackAsset
from infrastructure.database import DatabaseManager
from services.library_service import LibraryService
from storage.sqlite_track_repository import SqliteTrackRepository
from storage.tag_repository import SqliteTagRepository


class FakeTrash:
    """Papelera de mentira: registra qué se mandó y puede fallar a pedido."""

    def __init__(self, fail_on=()):
        self.sent: list[Path] = []
        self.fail_on = {Path(p) for p in fail_on}

    def __call__(self, path: Path):
        if Path(path) in self.fail_on:
            raise OSError("el archivo está abierto en otro programa")
        self.sent.append(Path(path))
        Path(path).unlink()


@pytest.fixture
def db(tmp_path):
    return DatabaseManager(tmp_path / "library.db")


@pytest.fixture
def repo(db):
    return SqliteTrackRepository(db=db)


def _track(repo, tmp_path, title: str, with_file: bool = True) -> Track:
    track_id = uuid.uuid4()
    path = tmp_path / f"{title}.mp3"
    if with_file:
        path.write_bytes(b"ID3")
    track = Track(id=track_id, title=title, assets=[
        TrackAsset(id=uuid.uuid4(), track_id=track_id, asset_type=AssetType.AUDIO_MP3, file_path=path)
    ])
    repo.save(track)
    return repo.get_by_id(track_id)


class TestMissingFiles:
    def test_a_deleted_file_is_reported_as_missing(self, repo, tmp_path):
        presente = _track(repo, tmp_path, "presente")
        ausente = _track(repo, tmp_path, "ausente", with_file=False)
        service = LibraryService(repo, trash=FakeTrash())
        assert service.check_missing_files() == [str(ausente.id)]
        assert not service.is_missing(presente)

    def test_relocate_points_the_track_at_the_new_file(self, repo, tmp_path):
        track = _track(repo, tmp_path, "movido", with_file=False)
        nuevo = tmp_path / "otra carpeta" / "movido.mp3"
        nuevo.parent.mkdir()
        nuevo.write_bytes(b"ID3")
        service = LibraryService(repo, trash=FakeTrash())

        service.relocate(str(track.id), str(nuevo))

        vuelta = repo.get_by_id(track.id)
        assert Path(vuelta.assets[0].file_path) == nuevo
        assert not service.is_missing(vuelta)

    def test_relocate_keeps_the_analysis(self, repo, tmp_path):
        # Es lo que lo distingue de quitar e importar de nuevo.
        track = _track(repo, tmp_path, "con-analisis", with_file=False)
        repo.save_analysis(track.id, 126.0, "8A", 7)
        nuevo = tmp_path / "con-analisis-nuevo.mp3"
        nuevo.write_bytes(b"ID3")
        LibraryService(repo, trash=FakeTrash()).relocate(str(track.id), str(nuevo))
        assert repo.get_by_id(track.id).bpm == 126.0

    def test_relocate_rejects_a_file_that_does_not_exist(self, repo, tmp_path):
        track = _track(repo, tmp_path, "x", with_file=False)
        with pytest.raises(ValueError, match="No existe"):
            LibraryService(repo, trash=FakeTrash()).relocate(str(track.id), str(tmp_path / "nada.mp3"))

    def test_relocate_rejects_an_unsupported_format(self, repo, tmp_path):
        track = _track(repo, tmp_path, "x", with_file=False)
        texto = tmp_path / "notas.txt"
        texto.write_text("hola")
        with pytest.raises(ValueError, match="Formato"):
            LibraryService(repo, trash=FakeTrash()).relocate(str(track.id), str(texto))

    def test_relocate_rejects_a_file_that_is_already_another_track(self, repo, tmp_path):
        otra = _track(repo, tmp_path, "otra")
        movida = _track(repo, tmp_path, "movida", with_file=False)
        with pytest.raises(ValueError, match="ya está en la librería"):
            LibraryService(repo, trash=FakeTrash()).relocate(
                str(movida.id), str(otra.assets[0].file_path)
            )


class TestRemoveTracks:
    def test_removing_keeps_the_files_by_default(self, repo, tmp_path):
        track = _track(repo, tmp_path, "solo-libreria")
        trash = FakeTrash()
        report = LibraryService(repo, trash=trash).remove_tracks([track])
        assert report.removed == 1 and report.files_trashed == 0
        assert repo.get_by_id(track.id) is None
        assert (tmp_path / "solo-libreria.mp3").exists()
        assert trash.sent == []

    def test_removing_with_files_sends_them_to_the_trash(self, repo, tmp_path):
        a = _track(repo, tmp_path, "a")
        b = _track(repo, tmp_path, "b")
        trash = FakeTrash()
        report = LibraryService(repo, trash=trash).remove_tracks([a, b], delete_files=True)
        assert report.removed == 2 and report.files_trashed == 2
        assert sorted(p.name for p in trash.sent) == ["a.mp3", "b.mp3"]

    def test_a_file_that_cannot_be_trashed_keeps_its_track(self, repo, tmp_path):
        # Si se quitara igual, el archivo quedaría en el disco sin que nada lo
        # muestre: el usuario creería que lo borró.
        abierto = _track(repo, tmp_path, "abierto")
        libre = _track(repo, tmp_path, "libre")
        trash = FakeTrash(fail_on=[abierto.assets[0].file_path])
        report = LibraryService(repo, trash=trash).remove_tracks(
            [abierto, libre], delete_files=True
        )
        assert report.removed == 1
        assert [Path(p).name for p, _ in report.kept] == ["abierto.mp3"]
        assert repo.get_by_id(abierto.id) is not None
        assert repo.get_by_id(libre.id) is None

    def test_a_track_without_file_is_removed_without_touching_the_trash(self, repo, tmp_path):
        ausente = _track(repo, tmp_path, "ausente", with_file=False)
        trash = FakeTrash()
        report = LibraryService(repo, trash=trash).remove_tracks([ausente], delete_files=True)
        assert report.removed == 1 and report.files_trashed == 0 and trash.sent == []

    def test_removing_cascades_to_analysis_and_tags(self, db, repo, tmp_path):
        track = _track(repo, tmp_path, "con-todo")
        repo.save_analysis(track.id, 124.0, "6A", 8)
        tags = SqliteTagRepository(db=db)
        tags.set_tags_for_source(str(track.id), TagSource.MANUAL, [Tag("genre", "techno")])

        LibraryService(repo, trash=FakeTrash()).remove_tracks([track])

        with db.get_connection() as conn:
            for tabla in ("track_assets", "track_analysis", "track_tags"):
                assert conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0, tabla

    def test_removing_many_at_once(self, repo, tmp_path):
        tracks = [_track(repo, tmp_path, f"t{i}") for i in range(620)]  # más de un lote de 500
        report = LibraryService(repo, trash=FakeTrash()).remove_tracks(tracks)
        assert report.removed == 620
        assert repo.get_all() == []
