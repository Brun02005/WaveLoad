"""Tests del modelo de Collections y del evaluador de la pila de capas."""

import uuid
from datetime import datetime, timezone

import pytest

from domain.collections import (
    Crate,
    CollectionError,
    LayerMode,
    QueryLayer,
    SmartCollection,
    SortDirection,
    SortSpec,
)
from domain.query_ast import and_, compare, or_, range_, source, tag, tag_any, text
from domain.tags import Tag
from infrastructure.database import DatabaseManager
from services.collection_evaluator import (
    CollectionEvaluator,
    build_collection_count_query,
    build_collection_query,
    build_layer_counts_query,
)
from services.tagging_service import TaggingService
from storage.tag_repository import SqliteTagRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _layer(predicate, mode=LayerMode.FILTER, position=0, enabled=True) -> QueryLayer:
    return QueryLayer(predicate=predicate, mode=mode, position=position, enabled=enabled)


# =============================================================================
# Modelo de dominio
# =============================================================================

class TestSortSpec:
    def test_defaults_to_ascending(self):
        assert SortSpec("bpm").direction is SortDirection.ASC

    def test_roundtrip(self):
        spec = SortSpec("bpm", SortDirection.DESC)
        assert SortSpec.from_dict(spec.to_dict()) == spec

    def test_from_dict_of_none_is_none(self):
        assert SortSpec.from_dict(None) is None

    def test_rejects_a_field_that_is_not_sortable(self):
        with pytest.raises(CollectionError, match="No se puede ordenar"):
            SortSpec("source_platform")

    def test_describe(self):
        assert SortSpec("bpm", SortDirection.DESC).describe() == "por bpm descendente"


class TestQueryLayer:
    def test_defaults_to_filter_and_enabled(self):
        layer = _layer(tag("genre", "techno"))
        assert layer.mode is LayerMode.FILTER
        assert layer.enabled

    def test_roundtrip_through_dict(self):
        layer = _layer(and_(tag("genre", "techno"), range_("bpm", 122, 128)),
                       LayerMode.EXCLUDE, position=2, enabled=False)
        assert QueryLayer.from_dict(layer.to_dict()) == layer

    def test_rejects_a_predicate_that_is_not_a_node(self):
        with pytest.raises(CollectionError, match="nodo del AST"):
            QueryLayer(predicate={"op": "tag"})

    def test_from_dict_reports_a_broken_ast(self):
        with pytest.raises(CollectionError, match="AST inválido"):
            QueryLayer.from_dict({"ast": {"op": "no_existe"}, "mode": "filter"})

    def test_from_dict_needs_an_ast(self):
        with pytest.raises(CollectionError, match="'ast'"):
            QueryLayer.from_dict({"mode": "filter"})

    def test_rejects_a_negative_position(self):
        with pytest.raises(CollectionError):
            QueryLayer(predicate=tag("genre", "techno"), position=-1)

    def test_describe_shows_the_mode_and_the_off_state(self):
        assert _layer(tag("genre", "techno")).describe() == "filtrar: genre:techno"
        apagada = _layer(tag("genre", "techno"), enabled=False)
        assert apagada.describe().endswith("[apagada]")


class TestSmartCollectionModel:
    def test_needs_a_name(self):
        with pytest.raises(CollectionError, match="nombre"):
            SmartCollection(name="   ")

    def test_rejects_a_non_positive_limit(self):
        with pytest.raises(CollectionError, match="positivo"):
            SmartCollection(name="X", limit=0)

    def test_rejects_two_layers_at_the_same_position(self):
        with pytest.raises(CollectionError, match="misma posición"):
            SmartCollection(name="X", layers=(
                _layer(tag("genre", "techno"), position=0),
                _layer(tag("mood", "dark"), position=0),
            ))

    def test_active_layers_skips_the_disabled_ones(self):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(tag("mood", "dark"), position=1, enabled=False),
            _layer(tag_any("context"), position=2),
        ))
        assert len(collection.ordered_layers()) == 3
        assert len(collection.active_layers()) == 2

    def test_layers_come_out_in_position_order_not_insertion_order(self):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("mood", "dark"), position=1),
            _layer(tag("genre", "techno"), position=0),
        ))
        assert [l.position for l in collection.ordered_layers()] == [0, 1]

    def test_with_layer_appends_at_the_end(self):
        collection = SmartCollection(name="X").with_layer(_layer(tag("genre", "techno")))
        collection = collection.with_layer(_layer(tag("mood", "dark")))
        assert [l.position for l in collection.ordered_layers()] == [0, 1]

    def test_with_layer_does_not_mutate_the_original(self):
        original = SmartCollection(name="X")
        original.with_layer(_layer(tag("genre", "techno")))
        assert original.layers == ()

    def test_without_layer_compacts_positions(self):
        collection = SmartCollection(name="X")
        for value in ("techno", "minimal", "house"):
            collection = collection.with_layer(_layer(tag("genre", value)))
        collection = collection.without_layer(1)
        assert [l.position for l in collection.ordered_layers()] == [0, 1]
        assert [l.predicate.value for l in collection.ordered_layers()] == ["techno", "house"]

    def test_without_a_layer_that_does_not_exist(self):
        with pytest.raises(CollectionError, match="posición 7"):
            SmartCollection(name="X").without_layer(7)

    def test_toggling_a_layer_keeps_it(self):
        collection = SmartCollection(name="X").with_layer(_layer(tag("genre", "techno")))
        apagada = collection.with_layer_toggled(0, False)
        assert len(apagada.layers) == 1
        assert apagada.active_layers() == ()

    def test_toggling_a_layer_that_does_not_exist(self):
        with pytest.raises(CollectionError):
            SmartCollection(name="X").with_layer_toggled(0, False)

    def test_moving_a_layer_reorders_the_stack(self):
        collection = SmartCollection(name="X")
        for value in ("techno", "minimal", "house"):
            collection = collection.with_layer(_layer(tag("genre", value)))
        movida = collection.with_layer_moved(2, 0)
        assert [l.predicate.value for l in movida.ordered_layers()] == [
            "house", "techno", "minimal"
        ]

    def test_moving_outside_the_stack_is_rejected(self):
        collection = SmartCollection(name="X").with_layer(_layer(tag("genre", "techno")))
        with pytest.raises(CollectionError, match="fuera de rango"):
            collection.with_layer_moved(0, 5)

    def test_describe_shows_the_whole_stack(self):
        collection = SmartCollection(
            name="Peak time",
            layers=(_layer(tag("genre", "techno"), position=0),
                    _layer(tag("context", "already-played"), LayerMode.EXCLUDE, 1)),
            sort=SortSpec("bpm"),
            limit=30,
        )
        texto = collection.describe()
        assert "base: librería completa" in texto
        assert "filtrar: genre:techno" in texto
        assert "excluir: context:already-played" in texto
        assert "límite: 30" in texto


class TestCrateModel:
    def test_needs_a_name(self):
        with pytest.raises(CollectionError):
            Crate(name="")

    def test_rejects_duplicates_at_construction(self):
        with pytest.raises(CollectionError, match="dos veces"):
            Crate(name="X", track_ids=("a", "a"))

    def test_with_track_appends(self):
        crate = Crate(name="X").with_track("a").with_track("b")
        assert crate.track_ids == ("a", "b")
        assert len(crate) == 2

    def test_adding_the_same_track_twice_is_a_noop(self):
        crate = Crate(name="X").with_track("a").with_track("a")
        assert crate.track_ids == ("a",)

    def test_with_track_at_a_position(self):
        crate = Crate(name="X", track_ids=("a", "b")).with_track("c", position=0)
        assert crate.track_ids == ("c", "a", "b")

    def test_without_track(self):
        crate = Crate(name="X", track_ids=("a", "b")).without_track("a")
        assert crate.track_ids == ("b",)

    def test_removing_something_that_is_not_there_is_a_noop(self):
        crate = Crate(name="X", track_ids=("a",))
        assert crate.without_track("z") is crate

    def test_moved_reorders(self):
        crate = Crate(name="X", track_ids=("a", "b", "c")).moved(2, 0)
        assert crate.track_ids == ("c", "a", "b")

    def test_moved_outside_the_crate_is_rejected(self):
        with pytest.raises(CollectionError):
            Crate(name="X", track_ids=("a",)).moved(0, 9)


# =============================================================================
# Evaluación contra SQLite
# =============================================================================

@pytest.fixture
def library(tmp_path):
    """Diez tracks con distribución conocida, para poder contar a mano."""
    db = DatabaseManager(db_path=tmp_path / "collections.db")
    repo = SqliteTagRepository(db=db)

    catalogo = [
        # título,   artista, dur,  bpm,   clave, energía, plataforma, géneros manuales
        ("T01", "Ana", 300, 124.0, "8A", 8.0, "local", ["techno"]),
        ("T02", "Ana", 310, 126.0, "8A", 9.0, "local", ["techno"]),
        ("T03", "Beto", 320, 128.0, "6A", 7.0, "youtube", ["minimal"]),
        ("T04", "Beto", 330, 122.0, "6A", 5.0, "youtube", ["minimal"]),
        ("T05", "Cata", 340, 132.0, "9B", 10.0, "local", ["techno"]),
        ("T06", "Cata", 350, 140.0, "3B", 10.0, "local", ["hard-techno"]),
        ("T07", "Dario", 360, 118.0, "5A", 3.0, "youtube", ["house"]),
        ("T08", "Dario", 370, 100.0, "1A", 2.0, "local", ["ambient"]),
        ("T09", "Eva", 380, 125.0, "8A", 6.0, "local", ["techno"]),
        ("T10", "Eva", 390, None, None, None, "local", []),
    ]
    ids: dict[str, str] = {}
    with db.get_connection() as conn:
        for titulo, artista, dur, bpm, clave, energia, plataforma, _ in catalogo:
            track_id = str(uuid.uuid4())
            ids[titulo] = track_id
            conn.execute(
                "INSERT INTO tracks (id, title, artist, duration, created_at, updated_at,"
                " source_platform) VALUES (?,?,?,?,?,?,?)",
                (track_id, titulo, artista, dur, _now(), _now(), plataforma),
            )
            if bpm is not None:
                conn.execute(
                    "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level,"
                    " analyzed_at) VALUES (?,?,?,?,?)",
                    (track_id, bpm, clave, energia, _now()),
                )
        conn.commit()

    service = TaggingService(repo)
    service.backfill_derived()
    service.backfill_inherited()
    for entrada in catalogo:
        titulo, generos = entrada[0], entrada[7]
        for genero in generos:
            repo.assign(ids[titulo], Tag("genre", genero))
    # Un par de tracks marcados como ya tocados.
    repo.assign(ids["T02"], Tag("context", "already-played"))
    repo.assign(ids["T05"], Tag("context", "already-played"))
    return db, ids


@pytest.fixture
def evaluator(library):
    db, _ = library
    return CollectionEvaluator(db)


def _titulos(library, evaluator, collection, **kwargs) -> set:
    _db, ids = library
    por_id = {track_id: titulo for titulo, track_id in ids.items()}
    resultado = evaluator.evaluate(collection, **kwargs)
    return {por_id[track_id] for track_id in resultado.track_ids}


class TestEvaluationBasics:
    def test_a_collection_without_layers_is_the_whole_library(self, library, evaluator):
        collection = SmartCollection(name="Todo")
        assert evaluator.count(collection) == 10

    def test_one_filter_layer(self, library, evaluator):
        collection = SmartCollection(name="Techno", layers=(
            _layer(tag("genre", "techno"), position=0),
        ))
        assert _titulos(library, evaluator, collection) == {"T01", "T02", "T05", "T09"}

    def test_two_filter_layers_intersect(self, library, evaluator):
        collection = SmartCollection(name="Techno lento", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(range_("bpm", 120, 127), position=1),
        ))
        assert _titulos(library, evaluator, collection) == {"T01", "T02", "T09"}

    def test_exclude_layer_subtracts(self, library, evaluator):
        collection = SmartCollection(name="Techno sin tocar", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(tag("context", "already-played"), LayerMode.EXCLUDE, 1),
        ))
        assert _titulos(library, evaluator, collection) == {"T01", "T09"}

    def test_union_layer_adds_from_the_whole_library(self, library, evaluator):
        collection = SmartCollection(name="Techno + house", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(tag("genre", "house"), LayerMode.UNION, 1),
        ))
        assert _titulos(library, evaluator, collection) == {"T01", "T02", "T05", "T09", "T07"}

    def test_the_stack_from_the_architecture_doc(self, library, evaluator):
        collection = SmartCollection(name="Ejemplo", layers=(
            _layer(or_(tag("genre", "techno"), tag("genre", "minimal")), position=0),
            _layer(range_("bpm", 122, 128), position=1),
            _layer(tag("context", "already-played"), LayerMode.EXCLUDE, 2),
        ))
        assert _titulos(library, evaluator, collection) == {"T01", "T03", "T04", "T09"}

    def test_a_disabled_layer_does_not_participate(self, library, evaluator):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(range_("bpm", 200, 300), position=1, enabled=False),
        ))
        assert len(_titulos(library, evaluator, collection)) == 4

    def test_turning_a_layer_off_and_on_is_reversible(self, library, evaluator):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(range_("bpm", 125, 135), position=1),
        ))
        con = evaluator.count(collection)
        sin = evaluator.count(collection.with_layer_toggled(1, False))
        devuelta = evaluator.count(collection.with_layer_toggled(1, False).with_layer_toggled(1, True))
        assert (con, sin, devuelta) == (3, 4, 3)

    def test_the_unanalyzed_track_survives_a_collection_without_layers(self, library, evaluator):
        assert "T10" in _titulos(library, evaluator, SmartCollection(name="Todo"))


class TestOrderMatters:
    def test_reordering_changes_the_result_when_there_is_a_union(self, library, evaluator):
        capa_techno = _layer(tag("genre", "techno"), position=0)
        capa_lentos = _layer(range_("bpm", 100, 121), LayerMode.UNION, 1)
        capa_local = _layer(source("source_platform", "local"), position=2)

        # techno -> +lentos -> sólo local
        una = SmartCollection(name="A", layers=(capa_techno, capa_lentos, capa_local))
        # techno -> sólo local -> +lentos  (la unión entra después del filtro)
        otra = SmartCollection(name="B", layers=(
            capa_techno,
            QueryLayer(source("source_platform", "local"), LayerMode.FILTER, 1),
            QueryLayer(range_("bpm", 100, 121), LayerMode.UNION, 2),
        ))
        assert _titulos(library, evaluator, una) != _titulos(library, evaluator, otra)

    def test_a_union_in_the_first_position_adds_nothing(self, library, evaluator):
        # La base implícita ya es la librería completa. Es consecuencia del
        # modelo documentado, no un bug: el builder debería avisarlo.
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), LayerMode.UNION, 0),
        ))
        assert evaluator.count(collection) == 10


class TestSortAndLimit:
    def test_sort_ascending(self, library, evaluator):
        _db, ids = library
        por_id = {v: k for k, v in ids.items()}
        collection = SmartCollection(name="X", sort=SortSpec("bpm"), limit=3)
        resultado = evaluator.evaluate(collection)
        assert [por_id[i] for i in resultado.track_ids] == ["T08", "T07", "T04"]

    def test_sort_descending(self, library, evaluator):
        _db, ids = library
        por_id = {v: k for k, v in ids.items()}
        collection = SmartCollection(name="X", sort=SortSpec("bpm", SortDirection.DESC), limit=2)
        resultado = evaluator.evaluate(collection)
        assert [por_id[i] for i in resultado.track_ids] == ["T06", "T05"]

    def test_nulls_go_last_not_first(self, library, evaluator):
        # Un track sin analizar no debería encabezar un orden por BPM sólo por
        # no tener BPM.
        _db, ids = library
        por_id = {v: k for k, v in ids.items()}
        collection = SmartCollection(name="X", sort=SortSpec("bpm"))
        resultado = evaluator.evaluate(collection)
        assert por_id[resultado.track_ids[-1]] == "T10"

    def test_limit_truncates_and_says_so(self, library, evaluator):
        collection = SmartCollection(name="X", limit=4)
        resultado = evaluator.evaluate(collection)
        assert len(resultado) == 4
        assert resultado.truncated

    def test_count_ignores_the_limit(self, library, evaluator):
        collection = SmartCollection(name="X", limit=4)
        assert evaluator.count(collection) == 10

    def test_offset_pages_through_the_result(self, library, evaluator):
        collection = SmartCollection(name="X", sort=SortSpec("title"))
        primera = evaluator.evaluate(collection, limit=4)
        segunda = evaluator.evaluate(collection, limit=4, offset=4)
        assert not set(primera.track_ids) & set(segunda.track_ids)
        assert len(segunda) == 4

    def test_offset_without_limit_still_works(self, library, evaluator):
        collection = SmartCollection(name="X", sort=SortSpec("title"))
        assert len(evaluator.evaluate(collection, offset=7)) == 3

    def test_an_explicit_limit_overrides_the_saved_one(self, library, evaluator):
        collection = SmartCollection(name="X", limit=2)
        assert len(evaluator.evaluate(collection, limit=5)) == 5

    def test_sort_and_limit_apply_once_at_the_end_not_per_layer(self, library, evaluator):
        # Si el límite se aplicara por capa, la primera capa dejaría 2 tracks y
        # el resultado final sería a lo sumo 2. Se esperan 4.
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(compare("duration", "gt", 0), position=1),
        ), limit=100)
        assert len(evaluator.evaluate(collection)) == 4


class TestLayerCounts:
    def test_counts_step_by_step(self, library, evaluator):
        collection = SmartCollection(name="Ejemplo", layers=(
            _layer(or_(tag("genre", "techno"), tag("genre", "minimal")), position=0),
            _layer(range_("bpm", 122, 128), position=1),
            _layer(tag("context", "already-played"), LayerMode.EXCLUDE, 2),
        ))
        conteos = evaluator.layer_counts(collection)
        assert [c.after for c in conteos] == [10, 6, 5, 4]

    def test_the_first_entry_is_the_base(self, library, evaluator):
        conteos = evaluator.layer_counts(SmartCollection(name="X"))
        assert len(conteos) == 1
        assert conteos[0].position == -1
        assert conteos[0].after == 10

    def test_disabled_layers_are_not_counted(self, library, evaluator):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(range_("bpm", 999, 1000), position=1, enabled=False),
        ))
        conteos = evaluator.layer_counts(collection)
        assert [c.after for c in conteos] == [10, 4]

    def test_the_last_count_matches_the_total(self, library, evaluator):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(range_("bpm", 120, 127), position=1),
        ))
        assert evaluator.layer_counts(collection)[-1].after == evaluator.count(collection)

    def test_label_uses_an_ascii_arrow(self, library, evaluator):
        # La etiqueta puede terminar en un log, y la consola de Windows es
        # cp1252: un "→" ahí levanta UnicodeEncodeError.
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
        ))
        etiqueta = evaluator.layer_counts(collection)[1].label
        etiqueta.encode("cp1252")  # no debe levantar

    def test_label_is_readable(self, library, evaluator):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
        ))
        assert evaluator.layer_counts(collection)[1].label == "[0] filtrar: genre:techno -> 4"


class TestGeneratedSql:
    def test_every_value_travels_as_a_parameter(self):
        collection = SmartCollection(name="X", layers=(
            _layer(text("title", "'; DROP TABLE tracks; --"), position=0),
        ))
        fragmento = build_collection_query(collection)
        assert "DROP TABLE" not in fragmento.sql

    def test_the_chain_has_one_cte_per_active_layer(self):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(tag("mood", "dark"), position=1),
            _layer(tag_any("status"), position=2, enabled=False),
        ))
        sql = build_collection_query(collection).sql
        assert "layer_1 AS" in sql and "layer_2 AS" in sql
        assert "layer_3" not in sql

    def test_the_base_cte_is_elided_when_the_first_layer_filters(self):
        # Intersecar con la librería completa es no intersecar con nada, así
        # que materializar los ids de toda la librería es trabajo tirado.
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
        ))
        assert "layer_0" not in build_collection_query(collection).sql

    def test_the_base_cte_survives_when_the_first_layer_unions(self):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), LayerMode.UNION, 0),
        ))
        assert "layer_0 AS" in build_collection_query(collection).sql

    def test_a_collection_without_layers_is_just_the_base(self):
        sql = build_collection_query(SmartCollection(name="X")).sql
        assert "layer_0 AS" in sql and "layer_1" not in sql

    def test_a_tag_only_layer_does_not_join_track_analysis(self):
        # Arrastrar el LEFT JOIN en capas que sólo miran tags cuesta 2,3x sobre
        # 50.000 tracks.
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
        ))
        assert "track_analysis" not in build_collection_query(collection).sql

    def test_a_layer_that_needs_analysis_does_join_it(self):
        collection = SmartCollection(name="X", layers=(
            _layer(range_("bpm", 122, 128), position=0),
        ))
        assert "track_analysis" in build_collection_query(collection).sql

    def test_a_key_tag_is_a_tag_not_the_analysis_column(self):
        # `key:8a` es un tag; la columna musical_key no es consultable.
        collection = SmartCollection(name="X", layers=(
            _layer(tag("key", "8a"), position=0),
        ))
        assert "track_analysis" not in build_collection_query(collection).sql

    def test_without_a_sort_there_is_no_join_back_to_tracks(self):
        sql = build_collection_query(SmartCollection(name="X")).sql
        assert "JOIN tracks st" not in sql

    def test_count_query_has_no_limit(self):
        collection = SmartCollection(name="X", limit=5)
        assert "LIMIT" not in build_collection_count_query(collection).sql

    def test_layer_counts_query_selects_one_column_per_layer(self):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
            _layer(tag("mood", "dark"), position=1),
        ))
        assert build_layer_counts_query(collection).sql.count("SELECT COUNT(*)") == 3

    def test_explain_returns_a_plan(self, library, evaluator):
        collection = SmartCollection(name="X", layers=(
            _layer(tag("genre", "techno"), position=0),
        ))
        plan = evaluator.explain(collection)
        assert plan and all(isinstance(linea, str) for linea in plan)


class TestEvaluationResult:
    def test_reports_elapsed_time(self, library, evaluator):
        resultado = evaluator.evaluate(SmartCollection(name="X"))
        assert resultado.elapsed_ms >= 0

    def test_not_truncated_when_there_is_no_limit(self, library, evaluator):
        assert not evaluator.evaluate(SmartCollection(name="X")).truncated

    def test_total_matches_the_ids_returned(self, library, evaluator):
        resultado = evaluator.evaluate(SmartCollection(name="X"))
        assert resultado.total == len(resultado.track_ids) == 10
