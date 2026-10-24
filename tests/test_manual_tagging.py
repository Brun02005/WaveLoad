"""Etiquetado manual en lote y género leído del archivo."""

import uuid

import pytest

import services.tagging_service as tagging
from domain.tags import Tag, TagSource
from infrastructure.database import DatabaseManager
from services.tagging_service import TaggingService, genres_from_file_values
from storage.tag_repository import SqliteTagRepository


@pytest.fixture
def repo(tmp_path):
    return SqliteTagRepository(db=DatabaseManager(tmp_path / "library.db"))


@pytest.fixture
def service(repo):
    return TaggingService(repo)


@pytest.fixture
def _ids(repo):
    """Crea ``n`` tracks en la base (track_tags tiene clave foránea a tracks)."""
    def crear(n):
        ids = [str(uuid.uuid4()) for _ in range(n)]
        with repo.db.get_connection() as conn:
            for track_id in ids:
                conn.execute(
                    "INSERT INTO tracks (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                    (track_id, "Tema", "2026-10-21T00:00:00", "2026-10-21T00:00:00"),
                )
        return ids
    return crear


class TestGenresFromFile:
    @pytest.mark.parametrize("crudo, esperado", [
        (["Techno (Peak Time / Driving)"], ["techno"]),       # subgénero de Beatport
        (["Electronica/Dance"], ["electronic", "dance"]),
        (["House; Deep House"], ["house", "deep-house"]),
        (["Drum n Bass"], ["drum-bass"]),
        (["Melodic House & Techno"], ["melodic-house-techno"]),
        (["Reggaetón"], ["reggaeton"]),
        (["Tech House", "tech-house", "TECH HOUSE"], ["tech-house"]),
        (["(17)"], []),                                       # código ID3v1
        (["Other"], []),
        ([], []),
    ])
    def test_normalization(self, crudo, esperado):
        assert genres_from_file_values(crudo) == esperado

    def test_at_most_three(self):
        assert genres_from_file_values(["a/b/c/d/e"]) == ["a", "b", "c"]

    def test_reading_a_file(self, monkeypatch, tmp_path):
        class Fake:
            tags = {"genre": ["Afro House"]}
        monkeypatch.setattr("mutagen.File", lambda *a, **k: Fake())
        assert tagging.read_file_genres(tmp_path / "x.mp3") == ["afro-house"]

    def test_an_unreadable_file_has_no_genre(self, monkeypatch, tmp_path):
        def explota(*a, **k):
            raise OSError("archivo dañado")
        monkeypatch.setattr("mutagen.File", explota)
        assert tagging.read_file_genres(tmp_path / "x.mp3") == []


class TestApplyFileGenres:
    def test_a_track_without_genre_takes_the_file_one(self, service, monkeypatch, _ids):
        monkeypatch.setattr(tagging, "read_file_genres", lambda path: ["tech-house"])
        [track] = _ids(1)
        assert service.apply_file_genres(track, "x.mp3") == 1
        assert [t.key for t in service.manual_tags([track])[track]] == ["genre:tech-house"]

    def test_it_never_overwrites_a_genre_the_user_chose(self, service, monkeypatch, _ids):
        monkeypatch.setattr(tagging, "read_file_genres", lambda path: ["pop"])
        [track] = _ids(1)
        service.edit_manual([track], add=[Tag("genre", "techno")])
        assert service.apply_file_genres(track, "x.mp3") == 0
        assert [t.key for t in service.manual_tags([track])[track]] == ["genre:techno"]

    def test_it_is_stored_as_manual_so_the_user_can_remove_it(self, service, repo, monkeypatch, _ids):
        monkeypatch.setattr(tagging, "read_file_genres", lambda path: ["house"])
        [track] = _ids(1)
        service.apply_file_genres(track, "x.mp3")
        assert [a.source for a in repo.tags_for_track(track)] == [TagSource.MANUAL]
        service.edit_manual([track], remove=[Tag("genre", "house")])
        assert service.manual_tags([track])[track] == []


class TestEditManual:
    def test_add_to_many_tracks_at_once(self, service, _ids):
        tracks = _ids(3)
        agregados, _ = service.edit_manual(tracks, add=[Tag("genre", "techno"), Tag("mood", "dark")])
        assert agregados == 6
        assert all(set(t.key for t in v) == {"genre:techno", "mood:dark"}
                   for v in service.manual_tags(tracks).values())

    def test_adding_twice_does_not_duplicate(self, service, _ids):
        tracks = _ids(2)
        service.edit_manual(tracks, add=[Tag("genre", "techno")])
        agregados, _ = service.edit_manual(tracks, add=[Tag("genre", "techno")])
        assert agregados == 0

    def test_remove_only_from_the_selection(self, service, _ids):
        a, b = _ids(2)
        service.edit_manual([a, b], add=[Tag("status", "ready")])
        _, quitados = service.edit_manual([a], remove=[Tag("status", "ready")])
        assert quitados == 1
        tags = service.manual_tags([a, b])
        assert tags[a] == [] and [t.key for t in tags[b]] == ["status:ready"]

    def test_removing_manual_does_not_touch_other_sources(self, service, repo, _ids):
        [track] = _ids(1)
        repo.assign(track, Tag("genre", "techno"), TagSource.AI, 0.8)
        service.edit_manual([track], add=[Tag("genre", "techno")])
        service.edit_manual([track], remove=[Tag("genre", "techno")])
        assert [a.source for a in repo.tags_for_track(track)] == [TagSource.AI]

    def test_analysis_namespaces_are_not_editable(self, service, _ids):
        with pytest.raises(ValueError, match="no se edita a mano"):
            service.edit_manual(_ids(1), add=[Tag("bpm", "120-129")])

    def test_manual_tags_only_reports_the_manual_axes(self, service, repo, _ids):
        [track] = _ids(1)
        repo.assign(track, Tag("bpm", "120-129"), TagSource.DERIVED)
        service.edit_manual([track], add=[Tag("context", "peak-time")])
        assert [t.key for t in service.manual_tags([track])[track]] == ["context:peak-time"]
