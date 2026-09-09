"""Tests de la persistencia de collections y crates."""

import json
import uuid
from datetime import datetime, timezone

import pytest

from domain.collections import (
    CollectionError,
    Crate,
    LayerMode,
    QueryLayer,
    SmartCollection,
    SortDirection,
    SortSpec,
)
from domain.query_ast import and_, not_, or_, range_, tag, tag_any, text
from infrastructure.database import DatabaseManager
from storage.collection_repository import (
    CollectionNotFound,
    SqliteCollectionRepository,
    UnsupportedAstVersion,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def repo(tmp_path):
    return SqliteCollectionRepository(db=DatabaseManager(db_path=tmp_path / "collections.db"))


@pytest.fixture
def tracks(repo):
    """Tres tracks reales, porque `crate_entries` tiene FK contra `tracks`."""
    ids = []
    with repo.db.get_connection() as conn:
        for i in range(3):
            track_id = str(uuid.uuid4())
            ids.append(track_id)
            conn.execute(
                "INSERT INTO tracks (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                (track_id, f"T{i}", _now(), _now()),
            )
        conn.commit()
    return ids


def _stack() -> SmartCollection:
    return SmartCollection(
        name="Peak time techno",
        layers=(
            QueryLayer(or_(tag("genre", "techno"), tag("genre", "minimal")),
                       LayerMode.FILTER, 0),
            QueryLayer(range_("bpm", 122, 128), LayerMode.FILTER, 1),
            QueryLayer(tag("context", "already-played"), LayerMode.EXCLUDE, 2, enabled=False),
        ),
        sort=SortSpec("bpm", SortDirection.DESC),
        limit=40,
    )


class TestSaveAndLoad:
    def test_save_assigns_an_id(self, repo):
        guardada = repo.save(SmartCollection(name="Nueva"))
        assert guardada.id is not None

    def test_roundtrip_preserves_the_whole_stack(self, repo):
        guardada = repo.save(_stack())
        leida = repo.get(guardada.id)

        assert leida.name == "Peak time techno"
        assert leida.limit == 40
        assert leida.sort == SortSpec("bpm", SortDirection.DESC)
        assert [l.position for l in leida.ordered_layers()] == [0, 1, 2]
        assert [l.mode for l in leida.ordered_layers()] == [
            LayerMode.FILTER, LayerMode.FILTER, LayerMode.EXCLUDE
        ]
        assert [l.enabled for l in leida.ordered_layers()] == [True, True, False]

    def test_the_predicates_survive_the_roundtrip(self, repo):
        original = _stack()
        leida = repo.get(repo.save(original).id)
        assert [l.predicate for l in leida.ordered_layers()] == [
            l.predicate for l in original.ordered_layers()
        ]

    def test_a_collection_without_layers_roundtrips(self, repo):
        leida = repo.get(repo.save(SmartCollection(name="Vacía")).id)
        assert leida.layers == ()

    def test_a_collection_without_sort_or_limit(self, repo):
        leida = repo.get(repo.save(SmartCollection(name="Simple")).id)
        assert leida.sort is None
        assert leida.limit is None

    def test_deeply_nested_predicates_survive(self, repo):
        predicado = and_(
            or_(tag("genre", "techno"), and_(tag_any("mood"), range_("bpm", 120, 130))),
            not_(text("title", "remix")),
        )
        collection = SmartCollection(
            name="Anidada", layers=(QueryLayer(predicado, LayerMode.FILTER, 0),)
        )
        leida = repo.get(repo.save(collection).id)
        assert leida.ordered_layers()[0].predicate == predicado

    def test_layers_come_back_with_their_database_ids(self, repo):
        leida = repo.get(repo.save(_stack()).id)
        assert all(l.id is not None for l in leida.ordered_layers())

    def test_created_at_and_updated_at_come_back_as_datetimes(self, repo):
        leida = repo.get(repo.save(SmartCollection(name="X")).id)
        assert isinstance(leida.created_at, datetime)
        assert isinstance(leida.updated_at, datetime)


class TestUpdate:
    def test_saving_an_existing_collection_replaces_its_stack(self, repo):
        guardada = repo.save(_stack())
        recortada = guardada.without_layer(2)
        vuelta = repo.save(recortada)
        assert len(vuelta.layers) == 2
        # Y no quedaron capas huérfanas de la versión anterior.
        with repo.db.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM collection_layers").fetchone()[0]
        assert total == 2

    def test_rename(self, repo):
        from dataclasses import replace
        guardada = repo.save(SmartCollection(name="Viejo"))
        repo.save(replace(guardada, name="Nuevo"))
        assert repo.get(guardada.id).name == "Nuevo"
        assert not repo.exists("Viejo")

    def test_toggling_a_layer_persists(self, repo):
        guardada = repo.save(_stack())
        repo.save(guardada.with_layer_toggled(0, False))
        assert repo.get(guardada.id).ordered_layers()[0].enabled is False

    def test_reordering_persists(self, repo):
        guardada = repo.save(_stack())
        repo.save(guardada.with_layer_moved(2, 0))
        leida = repo.get(guardada.id)
        assert leida.ordered_layers()[0].mode is LayerMode.EXCLUDE

    def test_updating_a_collection_that_was_deleted(self, repo):
        from dataclasses import replace
        guardada = repo.save(SmartCollection(name="Efímera"))
        repo.delete(guardada.id)
        with pytest.raises(CollectionNotFound):
            repo.save(replace(guardada, name="Otra"))

    def test_updated_at_moves_forward(self, repo):
        guardada = repo.save(SmartCollection(name="X"))
        from dataclasses import replace
        vuelta = repo.save(replace(guardada, limit=10))
        assert vuelta.updated_at >= guardada.updated_at


class TestNamesAreUnique:
    def test_two_collections_cannot_share_a_name(self, repo):
        repo.save(SmartCollection(name="Repetida"))
        with pytest.raises(CollectionError, match="Ya existe una collection"):
            repo.save(SmartCollection(name="Repetida"))

    def test_a_failed_save_leaves_nothing_behind(self, repo):
        repo.save(SmartCollection(name="Repetida"))
        with pytest.raises(CollectionError):
            repo.save(SmartCollection(
                name="Repetida",
                layers=(QueryLayer(tag("genre", "techno"), LayerMode.FILTER, 0),),
            ))
        with repo.db.get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM collection_layers").fetchone()[0] == 0

    def test_exists(self, repo):
        assert not repo.exists("Nada")
        repo.save(SmartCollection(name="Algo"))
        assert repo.exists("Algo")


class TestListAndFind:
    def test_list_all_is_sorted_by_name(self, repo):
        for nombre in ("Zeta", "alfa", "Beta"):
            repo.save(SmartCollection(name=nombre))
        assert [c.name for c in repo.list_all()] == ["alfa", "Beta", "Zeta"]

    def test_list_all_loads_the_layers(self, repo):
        repo.save(_stack())
        assert len(repo.list_all()[0].layers) == 3

    def test_list_names_is_cheap_and_ordered(self, repo):
        repo.save(SmartCollection(name="B"))
        repo.save(SmartCollection(name="A"))
        assert [nombre for _id, nombre in repo.list_names()] == ["A", "B"]

    def test_get_by_name(self, repo):
        repo.save(_stack())
        assert repo.get_by_name("Peak time techno").limit == 40

    def test_get_by_name_that_does_not_exist(self, repo):
        with pytest.raises(CollectionNotFound):
            repo.get_by_name("Fantasma")

    def test_get_by_id_that_does_not_exist(self, repo):
        with pytest.raises(CollectionNotFound):
            repo.get(999)

    def test_list_all_on_an_empty_database(self, repo):
        assert repo.list_all() == []


class TestDelete:
    def test_delete_removes_the_layers_too(self, repo):
        guardada = repo.save(_stack())
        assert repo.delete(guardada.id)
        with repo.db.get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM collection_layers").fetchone()[0] == 0

    def test_deleting_twice_reports_that_it_was_not_there(self, repo):
        guardada = repo.save(SmartCollection(name="X"))
        assert repo.delete(guardada.id)
        assert not repo.delete(guardada.id)


class TestAstVersion:
    def test_a_future_ast_version_is_refused_instead_of_misread(self, repo):
        # Una collection guardada por una versión posterior tiene que fallar
        # fuerte: leerla con reglas viejas daría resultados silenciosamente
        # equivocados.
        guardada = repo.save(_stack())
        with repo.db.get_connection() as conn:
            conn.execute("UPDATE collections SET ast_version = 99 WHERE id = ?",
                         (guardada.id,))
            conn.commit()
        with pytest.raises(UnsupportedAstVersion, match="99"):
            repo.get(guardada.id)

    def test_a_corrupt_ast_json_is_reported_with_the_layer_id(self, repo):
        guardada = repo.save(_stack())
        with repo.db.get_connection() as conn:
            conn.execute(
                "UPDATE collection_layers SET ast_json = ? WHERE collection_id = ?",
                ("{no es json", guardada.id),
            )
            conn.commit()
        with pytest.raises(CollectionError, match="ilegible"):
            repo.get(guardada.id)

    def test_an_unknown_operator_in_a_saved_layer_is_reported(self, repo):
        guardada = repo.save(_stack())
        with repo.db.get_connection() as conn:
            conn.execute(
                "UPDATE collection_layers SET ast_json = ? WHERE collection_id = ?"
                " AND position = 0",
                (json.dumps({"op": "in_collection", "id": 3}), guardada.id),
            )
            conn.commit()
        with pytest.raises(CollectionError, match="AST inválido"):
            repo.get(guardada.id)


class TestCrates:
    def test_roundtrip_keeps_the_order(self, repo, tracks):
        guardado = repo.save_crate(Crate(name="Viernes", track_ids=tuple(reversed(tracks))))
        assert repo.get_crate(guardado.id).track_ids == tuple(reversed(tracks))

    def test_an_empty_crate(self, repo):
        guardado = repo.save_crate(Crate(name="Vacío"))
        assert repo.get_crate(guardado.id).track_ids == ()

    def test_reordering_persists(self, repo, tracks):
        guardado = repo.save_crate(Crate(name="Viernes", track_ids=tuple(tracks)))
        repo.save_crate(guardado.moved(2, 0))
        assert repo.get_crate(guardado.id).track_ids[0] == tracks[2]

    def test_removing_a_track_persists(self, repo, tracks):
        guardado = repo.save_crate(Crate(name="Viernes", track_ids=tuple(tracks)))
        repo.save_crate(guardado.without_track(tracks[1]))
        assert len(repo.get_crate(guardado.id)) == 2

    def test_crate_names_are_unique(self, repo):
        repo.save_crate(Crate(name="Viernes"))
        with pytest.raises(CollectionError, match="Ya existe un crate"):
            repo.save_crate(Crate(name="Viernes"))

    def test_list_crates_is_sorted_by_name(self, repo):
        for nombre in ("Sábado", "Domingo"):
            repo.save_crate(Crate(name=nombre))
        assert [c.name for c in repo.list_crates()] == ["Domingo", "Sábado"]

    def test_delete_removes_the_entries(self, repo, tracks):
        guardado = repo.save_crate(Crate(name="Viernes", track_ids=tuple(tracks)))
        assert repo.delete_crate(guardado.id)
        with repo.db.get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM crate_entries").fetchone()[0] == 0

    def test_get_a_crate_that_does_not_exist(self, repo):
        with pytest.raises(CollectionNotFound):
            repo.get_crate(999)

    def test_deleting_a_track_removes_it_from_its_crates(self, repo, tracks):
        # El crate no puede quedar apuntando a un track que ya no existe: la FK
        # tiene ON DELETE CASCADE.
        guardado = repo.save_crate(Crate(name="Viernes", track_ids=tuple(tracks)))
        with repo.db.get_connection() as conn:
            conn.execute("DELETE FROM tracks WHERE id = ?", (tracks[0],))
            conn.commit()
        assert len(repo.get_crate(guardado.id)) == 2

    def test_saving_a_crate_with_a_track_that_does_not_exist(self, repo):
        with pytest.raises(Exception):
            repo.save_crate(Crate(name="Roto", track_ids=("no-existe",)))

    def test_a_failed_crate_save_leaves_nothing_behind(self, repo):
        with pytest.raises(Exception):
            repo.save_crate(Crate(name="Roto", track_ids=("no-existe",)))
        with repo.db.get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM crates").fetchone()[0] == 0


class TestCollectionsAndCratesAreIndependent:
    def test_a_collection_and_a_crate_can_share_a_name(self, repo):
        repo.save(SmartCollection(name="Viernes"))
        repo.save_crate(Crate(name="Viernes"))
        assert repo.exists("Viernes")
        assert [c.name for c in repo.list_crates()] == ["Viernes"]

    def test_deleting_a_collection_does_not_touch_the_crates(self, repo):
        guardada = repo.save(SmartCollection(name="Una"))
        repo.save_crate(Crate(name="Otro"))
        repo.delete(guardada.id)
        assert len(repo.list_crates()) == 1
