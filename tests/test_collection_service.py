"""Tests de la fachada de Collections que consume la UI."""

import uuid
from datetime import datetime, timezone

import pytest

from domain.collections import (
    Crate,
    LayerMode,
    QueryLayer,
    SmartCollection,
    SortDirection,
    SortSpec,
)
from domain.query_ast import range_, tag
from domain.tags import Tag
from infrastructure.database import DatabaseManager
from services.collection_service import DEFAULT_PAGE_SIZE, CollectionService
from services.tagging_service import TaggingService
from storage.collection_repository import SqliteCollectionRepository
from storage.sqlite_track_repository import SqliteTrackRepository
from storage.tag_repository import SqliteTagRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def service(tmp_path):
    """Servicio sobre una librería de 12 tracks con tags derivados."""
    db = DatabaseManager(db_path=tmp_path / "servicio.db")
    tag_repo = SqliteTagRepository(db=db)

    with db.get_connection() as conn:
        for i in range(12):
            track_id = str(uuid.uuid4())
            bpm = 120.0 + i  # 120..131
            conn.execute(
                "INSERT INTO tracks (id, title, artist, duration, created_at, updated_at,"
                " source_platform) VALUES (?,?,?,?,?,?,?)",
                (track_id, f"Track {i:02d}", f"Artista {i % 3}", 300 + i,
                 _now(), _now(), "local"),
            )
            conn.execute(
                "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level,"
                " analyzed_at) VALUES (?,?,?,?,?)",
                (track_id, bpm, "8A", float(1 + i % 10), _now()),
            )
        conn.commit()

    TaggingService(tag_repo).backfill_derived()
    return CollectionService(
        collection_repository=SqliteCollectionRepository(db=db),
        track_repository=SqliteTrackRepository(db=db),
        tag_repository=tag_repo,
    )


class TestLifecycle:
    def test_create_returns_a_saved_collection(self, service):
        creada = service.create("Mi colección")
        assert creada.id is not None
        assert service.get(creada.id).name == "Mi colección"

    def test_an_empty_collection_is_the_whole_library(self, service):
        assert service.count(service.create("Vacía")) == 12

    def test_create_unique_avoids_collisions(self, service):
        primera = service.create_unique()
        segunda = service.create_unique()
        tercera = service.create_unique()
        assert [primera.name, segunda.name, tercera.name] == [
            "Nueva colección", "Nueva colección 2", "Nueva colección 3"
        ]

    def test_rename(self, service):
        creada = service.create("Vieja")
        service.rename(creada, "Nueva")
        assert [n for _i, n in service.list_names()] == ["Nueva"]

    def test_delete(self, service):
        creada = service.create("Efímera")
        assert service.delete(creada.id)
        assert service.list_names() == []

    def test_duplicate_copies_the_stack_under_another_name(self, service):
        original = service.add_layer(service.create("Original"), tag("bpm", "120-129"))
        copia = service.duplicate(original)
        assert copia.name == "Original (copia)"
        assert copia.id != original.id
        assert len(copia.layers) == 1
        assert service.count(copia) == service.count(original)

    def test_duplicating_twice_keeps_finding_a_free_name(self, service):
        original = service.create("Original")
        service.duplicate(original)
        assert service.duplicate(original).name == "Original (copia) 2"

    def test_a_duplicate_is_independent_of_its_original(self, service):
        original = service.add_layer(service.create("Original"), tag("bpm", "120-129"))
        copia = service.duplicate(original)
        service.remove_layer(original, 0)
        assert len(service.get(copia.id).layers) == 1


class TestStackEditing:
    def test_add_layer_persists(self, service):
        collection = service.add_layer(service.create("X"), tag("bpm", "120-129"))
        assert len(service.get(collection.id).layers) == 1

    def test_layers_stack_in_order(self, service):
        collection = service.create("X")
        collection = service.add_layer(collection, tag("bpm", "120-129"))
        collection = service.add_layer(collection, range_("bpm", 125, 131))
        assert [l.position for l in collection.ordered_layers()] == [0, 1]

    def test_each_layer_narrows_the_result(self, service):
        collection = service.create("X")
        assert service.count(collection) == 12
        collection = service.add_layer(collection, tag("bpm", "120-129"))
        assert service.count(collection) == 10
        collection = service.add_layer(collection, range_("bpm", 125, 131))
        assert service.count(collection) == 5

    def test_exclude_layer(self, service):
        collection = service.add_layer(
            service.create("X"), range_("bpm", 125, 131), LayerMode.EXCLUDE
        )
        assert service.count(collection) == 5

    def test_toggle_layer_round_trip(self, service):
        collection = service.add_layer(service.create("X"), range_("bpm", 125, 131))
        apagada = service.toggle_layer(collection, 0, False)
        assert service.count(apagada) == 12
        prendida = service.toggle_layer(apagada, 0, True)
        assert service.count(prendida) == 7

    def test_remove_layer(self, service):
        collection = service.add_layer(service.create("X"), range_("bpm", 125, 131))
        assert service.count(service.remove_layer(collection, 0)) == 12

    def test_move_layer_persists(self, service):
        collection = service.create("X")
        collection = service.add_layer(collection, tag("bpm", "120-129"))
        collection = service.add_layer(collection, range_("bpm", 125, 131), LayerMode.EXCLUDE)
        movida = service.move_layer(collection, 1, 0)
        assert movida.ordered_layers()[0].mode is LayerMode.EXCLUDE

    def test_set_sort_and_limit(self, service):
        collection = service.create("X")
        collection = service.set_sort(collection, SortSpec("bpm", SortDirection.DESC))
        collection = service.set_limit(collection, 5)
        vuelta = service.get(collection.id)
        assert vuelta.sort == SortSpec("bpm", SortDirection.DESC)
        assert vuelta.limit == 5

    def test_clearing_the_sort(self, service):
        collection = service.set_sort(service.create("X"), SortSpec("bpm"))
        assert service.set_sort(collection, None).sort is None


class TestPaging:
    def test_a_page_carries_real_tracks(self, service):
        pagina = service.page(service.create("X"), page_size=5)
        assert len(pagina) == 5
        assert all(hasattr(track, "title") for track in pagina.tracks)

    def test_tracks_come_in_the_order_the_query_gave(self, service):
        collection = service.set_sort(service.create("X"), SortSpec("bpm", SortDirection.DESC))
        pagina = service.page(collection, page_size=3)
        assert [t.title for t in pagina.tracks] == ["Track 11", "Track 10", "Track 09"]

    def test_second_page_continues_where_the_first_ended(self, service):
        collection = service.set_sort(service.create("X"), SortSpec("title"))
        primera = service.page(collection, page_size=5)
        segunda = service.page(collection, offset=5, page_size=5)
        assert [t.title for t in segunda.tracks] == [
            "Track 05", "Track 06", "Track 07", "Track 08", "Track 09"
        ]
        assert not ({t.id for t in primera.tracks} & {t.id for t in segunda.tracks})

    def test_has_more_and_page_number(self, service):
        collection = service.create("X")
        primera = service.page(collection, page_size=5)
        assert primera.has_more and primera.page_number == 1
        ultima = service.page(collection, offset=10, page_size=5)
        assert not ultima.has_more and ultima.page_number == 3

    def test_total_is_the_whole_result_not_the_page(self, service):
        pagina = service.page(service.create("X"), page_size=3)
        assert len(pagina) == 3 and pagina.total == 12

    def test_a_saved_limit_caps_the_total(self, service):
        collection = service.set_limit(
            service.set_sort(service.create("X"), SortSpec("bpm")), 4
        )
        pagina = service.page(collection, page_size=10)
        assert pagina.total == 4

    def test_the_default_page_size_is_the_documented_one(self, service):
        assert service.page(service.create("X")).page_size == DEFAULT_PAGE_SIZE

    def test_a_page_beyond_the_end_is_empty_not_an_error(self, service):
        pagina = service.page(service.create("X"), offset=500, page_size=10)
        assert len(pagina) == 0 and not pagina.has_more

    def test_the_page_reports_what_it_cost(self, service):
        assert service.page(service.create("X")).elapsed_ms >= 0


class TestLayerCounts:
    def test_counts_step_by_step(self, service):
        collection = service.create("X")
        collection = service.add_layer(collection, tag("bpm", "120-129"))
        collection = service.add_layer(collection, range_("bpm", 125, 131))
        assert [c.after for c in service.layer_counts(collection)] == [12, 10, 5]


class TestWarnings:
    def test_a_union_first_is_flagged(self, service):
        collection = service.add_layer(
            service.create("X"), tag("bpm", "120-129"), LayerMode.UNION
        )
        assert any("primera capa suma" in aviso for aviso in service.warnings(collection))

    def test_all_layers_off_is_flagged(self, service):
        collection = service.add_layer(service.create("X"), tag("bpm", "120-129"))
        apagada = service.toggle_layer(collection, 0, False)
        assert any("apagadas" in aviso for aviso in service.warnings(apagada))

    def test_a_limit_without_a_sort_is_flagged(self, service):
        collection = service.set_limit(service.create("X"), 10)
        assert any("no un orden" in aviso for aviso in service.warnings(collection))

    def test_a_limit_with_a_sort_is_not_flagged(self, service):
        collection = service.set_sort(service.create("X"), SortSpec("bpm"))
        collection = service.set_limit(collection, 10)
        assert service.warnings(collection) == []

    def test_a_healthy_collection_has_no_warnings(self, service):
        collection = service.add_layer(service.create("X"), tag("bpm", "120-129"))
        assert service.warnings(collection) == []


class TestFreezeToCrate:
    def test_freezing_materializes_the_current_result(self, service):
        collection = service.add_layer(service.create("X"), range_("bpm", 125, 131))
        crate = service.freeze_to_crate(collection)
        assert len(crate) == service.count(collection) == 7

    def test_the_crate_keeps_the_order_of_the_result(self, service):
        collection = service.set_sort(
            service.add_layer(service.create("X"), range_("bpm", 125, 131)),
            SortSpec("bpm", SortDirection.DESC),
        )
        crate = service.freeze_to_crate(collection)
        titulos = [t.title for t in service.crate_tracks(crate)]
        assert titulos[0] == "Track 11"

    def test_the_crate_does_not_change_when_the_collection_does(self, service):
        # Es el punto entero de congelar: a partir de acá son cosas
        # independientes.
        collection = service.add_layer(service.create("X"), range_("bpm", 125, 131))
        crate = service.freeze_to_crate(collection)
        service.remove_layer(collection, 0)
        assert len(service.repo.get_crate(crate.id)) == 7

    def test_the_default_name_says_where_it_came_from(self, service):
        crate = service.freeze_to_crate(service.create("Peak time"))
        assert crate.name == "Peak time (congelada)"

    def test_an_explicit_name_wins(self, service):
        crate = service.freeze_to_crate(service.create("X"), name="Set del viernes")
        assert crate.name == "Set del viernes"

    def test_freezing_twice_does_not_collide(self, service):
        collection = service.create("X")
        service.freeze_to_crate(collection)
        assert service.freeze_to_crate(collection).name == "X (congelada) 2"

    def test_freezing_an_empty_result_gives_an_empty_crate(self, service):
        collection = service.add_layer(service.create("X"), range_("bpm", 900, 999))
        assert len(service.freeze_to_crate(collection)) == 0


class TestCrates:
    def test_crate_tracks_come_in_order(self, service):
        collection = service.set_sort(service.create("X"), SortSpec("bpm", SortDirection.DESC))
        crate = service.freeze_to_crate(collection)
        titulos = [t.title for t in service.crate_tracks(crate)]
        assert titulos == sorted(titulos, reverse=True)

    def test_list_crates(self, service):
        service.freeze_to_crate(service.create("A"))
        service.freeze_to_crate(service.create("B"))
        assert len(service.list_crates()) == 2

    def test_an_empty_crate_resolves_to_no_tracks(self, service):
        assert service.crate_tracks(Crate(name="Vacío")) == ()


class TestGetByIds:
    def test_preserves_the_order_it_was_asked_for(self, service):
        todos = service.tracks.get_all()
        ids = [str(t.id) for t in todos][:5]
        pedidos = service.tracks.get_by_ids(list(reversed(ids)))
        assert [str(t.id) for t in pedidos] == list(reversed(ids))

    def test_skips_ids_that_no_longer_exist(self, service):
        real = str(service.tracks.get_all()[0].id)
        resultado = service.tracks.get_by_ids([real, str(uuid.uuid4())])
        assert [str(t.id) for t in resultado] == [real]

    def test_an_empty_request_returns_nothing(self, service):
        assert service.tracks.get_by_ids([]) == []

    def test_tracks_come_back_with_their_analysis(self, service):
        track = service.tracks.get_by_ids([str(service.tracks.get_all()[0].id)])[0]
        assert track.bpm is not None


class TestVocabularyForTheBuilder:
    def test_namespace_values_are_ordered_by_usage(self, service):
        # 12 tracks: bpm 120..131 -> 10 en 120-129 y 2 en 130-139.
        valores = service.namespace_values("bpm")
        assert valores == [("120-129", 10), ("130-139", 2)]

    def test_an_empty_namespace_gives_nothing(self, service):
        assert service.namespace_values("mood") == []

    def test_used_namespaces_are_the_ones_with_values(self, service):
        assert service.used_namespaces() == ["bpm", "energy", "key"]

    def test_without_a_tag_repository_the_vocabulary_is_empty(self, tmp_path):
        db = DatabaseManager(db_path=tmp_path / "sin_tags.db")
        sin_tags = CollectionService(
            collection_repository=SqliteCollectionRepository(db=db),
            track_repository=SqliteTrackRepository(db=db),
        )
        assert sin_tags.namespace_values("genre") == []
        assert sin_tags.used_namespaces() == []


class TestTagRepositoryVocabulary:
    def test_values_in_namespace_is_sorted_alphabetically(self, service):
        assert service.tags.values_in_namespace("bpm") == ["120-129", "130-139"]

    def test_an_unknown_namespace_gives_nothing(self, service):
        assert service.tags.values_in_namespace("genre") == []

    def test_usage_counts_distinct_tracks(self, service):
        por_uso = dict(service.tags.usage_by_namespace("key"))
        assert por_uso == {"8a": 12}

    def test_a_tag_in_the_vocabulary_with_no_tracks_reports_zero(self, service):
        from domain.tags import Tag
        with service.tags.db.get_connection() as conn:
            service.tags.get_or_create_tag_id(Tag("genre", "huerfano"), conn)
            conn.commit()
        assert service.tags.usage_by_namespace("genre") == [("huerfano", 0)]
