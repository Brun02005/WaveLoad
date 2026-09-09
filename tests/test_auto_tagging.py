"""Tests del etiquetado automático enganchado al event bus.

Headless: se usa un `EventBus` propio por test, nunca el global, para que no
queden suscriptores colgados entre tests.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest

from core.event_bus import EventBus, TrackAnalyzedEvent, TrackCreatedEvent
from domain.tags import Tag, TagSource
from infrastructure.database import DatabaseManager
from services.auto_tagging_service import AutoTaggingService
from services.tagging_service import TaggingService
from storage.tag_repository import SqliteTagRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FakeTrack:
    """Lo mínimo que el AutoTagger le pide a un Track."""
    id: str
    source_platform: Optional[str] = None
    source_playlist_name: Optional[str] = None


@pytest.fixture
def wiring(tmp_path):
    """``(bus, repo, track_id)`` con el AutoTagger ya suscripto."""
    db = DatabaseManager(db_path=tmp_path / "auto.db")
    repo = SqliteTagRepository(db=db)
    bus = EventBus()
    servicio = AutoTaggingService(TaggingService(repo), bus=bus)

    track_id = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO tracks (id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (track_id, "Nuevo", _now(), _now()),
        )
        conn.commit()
    # Se conserva la referencia al servicio: si el objeto muere, el bus queda
    # con un handler de un objeto muerto.
    return bus, repo, track_id, servicio


class TestInheritedOnCreate:
    def test_a_new_track_is_born_with_its_source_tags(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackCreatedEvent(track=FakeTrack(track_id, "youtube", "Summer Vibes")))
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == {
            "source:youtube", "playlist:summer-vibes"
        }

    def test_they_are_marked_as_inherited(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackCreatedEvent(track=FakeTrack(track_id, "local")))
        assert all(
            a.source is TagSource.INHERITED for a in repo.tags_for_track(track_id)
        )

    def test_a_track_without_source_gets_nothing(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackCreatedEvent(track=FakeTrack(track_id)))
        assert repo.tags_for_track(track_id) == []

    def test_emitting_the_same_event_twice_does_not_duplicate(self, wiring):
        bus, repo, track_id, _ = wiring
        evento = TrackCreatedEvent(track=FakeTrack(track_id, "youtube"))
        bus.emit(evento)
        bus.emit(evento)
        assert repo.count_assignments() == 1


class TestDerivedOnAnalysis:
    def test_analysis_produces_the_three_derived_tags(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackAnalyzedEvent(track_id, bpm=126.0, key_camelot="8A", energy=7))
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == {
            "bpm:120-129", "key:8a", "energy:high"
        }

    def test_they_are_marked_as_derived(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackAnalyzedEvent(track_id, bpm=126.0, key_camelot="8A", energy=7))
        assert all(a.source is TagSource.DERIVED for a in repo.tags_for_track(track_id))

    def test_a_reanalysis_moves_the_tags(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackAnalyzedEvent(track_id, bpm=126.0, key_camelot="8A", energy=7))
        bus.emit(TrackAnalyzedEvent(track_id, bpm=145.0, key_camelot="3B", energy=10))
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == {
            "bpm:140-149", "key:3b", "energy:peak"
        }

    def test_a_reanalysis_never_touches_manual_tags(self, wiring):
        bus, repo, track_id, _ = wiring
        repo.assign(track_id, Tag("genre", "minimal"), TagSource.MANUAL)
        bus.emit(TrackAnalyzedEvent(track_id, bpm=126.0, key_camelot="8A", energy=7))
        bus.emit(TrackAnalyzedEvent(track_id, bpm=90.0, key_camelot=None, energy=1))
        manual = repo.tags_for_track(track_id, TagSource.MANUAL)
        assert [a.tag.key for a in manual] == ["genre:minimal"]

    def test_a_failed_analysis_with_no_values_clears_the_derived_tags(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackAnalyzedEvent(track_id, bpm=126.0, key_camelot="8A", energy=7))
        bus.emit(TrackAnalyzedEvent(track_id, bpm=None, key_camelot=None, energy=None))
        assert repo.tags_for_track(track_id, TagSource.DERIVED) == []

    def test_derived_and_inherited_coexist_on_the_same_track(self, wiring):
        bus, repo, track_id, _ = wiring
        bus.emit(TrackCreatedEvent(track=FakeTrack(track_id, "youtube")))
        bus.emit(TrackAnalyzedEvent(track_id, bpm=126.0, key_camelot="8A", energy=7))
        assert len(repo.tags_for_track(track_id)) == 4


class TestFailuresDoNotBreakThePipeline:
    def test_a_track_that_is_not_in_the_library_does_not_raise(self, wiring):
        # La FK rechaza la asignación; el handler tiene que loguear y seguir.
        bus, repo, _track_id, _ = wiring
        bus.emit(TrackCreatedEvent(track=FakeTrack(str(uuid.uuid4()), "youtube")))
        assert repo.count_assignments() == 0

    def test_an_event_without_a_track_does_not_raise(self, wiring):
        bus, repo, _track_id, _ = wiring
        bus.emit(TrackCreatedEvent(track=None))
        assert repo.count_assignments() == 0

    def test_an_event_with_a_track_without_id_does_not_raise(self, wiring):
        bus, repo, _track_id, _ = wiring
        bus.emit(TrackCreatedEvent(track=FakeTrack(id="", source_platform="youtube")))
        assert repo.count_assignments() == 0

    def test_an_analysis_event_without_track_id_does_not_raise(self, wiring):
        bus, repo, _track_id, _ = wiring
        bus.emit(TrackAnalyzedEvent(track_id="", bpm=126.0))
        assert repo.count_assignments() == 0

    def test_other_subscribers_still_run_when_tagging_fails(self, wiring):
        # El bus captura por handler, así que un fallo del AutoTagger no puede
        # impedir que la UI se entere de que hay un track nuevo.
        bus, _repo, _track_id, _ = wiring
        vistos = []
        bus.subscribe(TrackCreatedEvent, lambda evento: vistos.append(evento))
        bus.emit(TrackCreatedEvent(track=FakeTrack(str(uuid.uuid4()), "youtube")))
        assert len(vistos) == 1


class TestBackfillIsStillTheSafetyNet:
    def test_backfill_repairs_a_track_the_hook_missed(self, wiring, tmp_path):
        # Si el hook falló (o el track entró antes de que existiera), el
        # backfill lo tiene que dejar igual que si el hook hubiera andado.
        bus, repo, track_id, _ = wiring
        with repo.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level,"
                " analyzed_at) VALUES (?,?,?,?,?)",
                (track_id, 126.0, "8A", 7.0, _now()),
            )
            conn.execute("UPDATE tracks SET source_platform = ? WHERE id = ?",
                         ("youtube", track_id))
            conn.commit()

        servicio = TaggingService(repo)
        servicio.backfill_derived()
        servicio.backfill_inherited()
        por_hook = {a.tag.key for a in repo.tags_for_track(track_id)}

        # Y ahora el hook sobre lo mismo: no cambia nada.
        bus.emit(TrackAnalyzedEvent(track_id, bpm=126.0, key_camelot="8A", energy=7))
        bus.emit(TrackCreatedEvent(track=FakeTrack(track_id, "youtube")))
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == por_hook


class TestWiring:
    def test_it_subscribes_to_both_events(self, tmp_path):
        db = DatabaseManager(db_path=tmp_path / "wiring.db")
        bus = EventBus()
        AutoTaggingService(TaggingService(SqliteTagRepository(db=db)), bus=bus)
        assert TrackCreatedEvent in bus._subscribers
        assert TrackAnalyzedEvent in bus._subscribers

    def test_the_bootstrap_container_wires_it(self):
        # Se lee el archivo en vez de importarlo: `application/bootstrap.py`
        # construye el contenedor entero al importarse, lo que levantaría Qt y
        # correría migraciones contra la librería real del usuario.
        from pathlib import Path
        fuente = (Path(__file__).resolve().parent.parent
                  / "application" / "bootstrap.py").read_text(encoding="utf-8")
        # La referencia tiene que quedar guardada en el contenedor: un
        # AutoTaggingService que se recolecta deja el bus con un handler de un
        # objeto muerto.
        assert "self.auto_tagging_service = AutoTaggingService(" in fuente
        assert "self.tagging_service = TaggingService(" in fuente
