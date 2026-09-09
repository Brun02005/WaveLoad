"""Tests del compilador de AST a SQL.

Se prueban dos cosas distintas: que el SQL generado tenga la forma correcta y
los parámetros bindeados, y que ejecutado contra una DB real devuelva los tracks
que corresponden. Lo segundo es lo que importa; lo primero es lo que hace que
cuando falle se entienda por qué.
"""

import uuid
from datetime import datetime, timezone

import pytest

from domain.query_ast import (
    and_,
    compare,
    not_,
    or_,
    range_,
    source,
    tag,
    tag_any,
    text,
)
from infrastructure.database import DatabaseManager
from services.query_compiler import (
    QueryCompilationError,
    SqlFragment,
    build_count_query,
    build_track_ids_query,
    compile_node,
    compile_predicate,
)
from services.tagging_service import TaggingService
from storage.tag_repository import SqliteTagRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Forma del SQL generado
# =============================================================================

class TestGeneratedSql:
    def test_tag_becomes_an_in_subquery(self):
        # `IN (subconsulta)` y no `EXISTS` correlacionado: se materializa una
        # vez en lugar de re-evaluarse por track. Ver el comentario en
        # services/query_compiler.py con los números medidos.
        fragment = compile_node(tag("genre", "techno"))
        assert "IN (SELECT" in fragment.sql
        assert "track_tags" in fragment.sql
        assert fragment.params == ("genre", "techno")

    def test_tag_any_does_not_bind_a_value(self):
        assert compile_node(tag_any("mood")).params == ("mood",)

    def test_range_with_both_bounds_uses_between(self):
        fragment = compile_node(range_("bpm", 122, 128))
        assert "BETWEEN" in fragment.sql
        assert fragment.params == (122, 128)

    def test_open_range_uses_a_single_comparison(self):
        assert compile_node(range_("bpm", minimum=140)).params == (140,)
        assert compile_node(range_("bpm", maximum=100)).params == (100,)

    def test_unary_comparators_bind_nothing(self):
        assert compile_node(compare("bpm", "is_null")).params == ()
        assert "IS NULL" in compile_node(compare("bpm", "is_null")).sql
        assert "IS NOT NULL" in compile_node(compare("bpm", "not_null")).sql

    def test_energy_maps_to_the_real_column_name(self):
        assert "energy_level" in compile_node(range_("energy", 7, 10)).sql

    def test_not_collapses_three_valued_logic(self):
        assert "COALESCE" in compile_node(not_(tag("genre", "techno"))).sql

    def test_the_top_level_predicate_is_not_wrapped_in_coalesce(self):
        # El WHERE ya descarta las filas que dan NULL; envolverlo de más le
        # impide a SQLite usar el índice de la columna.
        assert "COALESCE" not in compile_predicate(range_("bpm", 122, 128)).sql

    def test_params_come_out_in_the_order_they_appear(self):
        node = and_(tag("genre", "techno"), range_("bpm", 122, 128), tag_any("mood"))
        assert compile_predicate(node).params == ("genre", "techno", 122, 128, "mood")

    def test_no_user_value_is_interpolated_into_the_sql(self):
        # La inyección es el riesgo entero de compilar queries: el valor tiene
        # que estar en params y no aparecer en el string.
        evil = "'; DROP TABLE tracks; --"
        fragment = compile_predicate(text("title", evil))
        assert "DROP TABLE" not in fragment.sql
        assert any(evil in str(p) for p in fragment.params)

    def test_like_wildcards_typed_by_the_user_are_escaped(self):
        fragment = compile_node(text("title", "100% pure"))
        assert fragment.params == ("%100\\% pure%",)
        assert "ESCAPE" in fragment.sql

    def test_underscore_is_escaped_too(self):
        assert compile_node(text("title", "a_b")).params == ("%a\\_b%",)

    def test_starts_with_anchors_the_pattern(self):
        assert compile_node(text("artist", "Ric", "starts_with")).params == ("Ric%",)

    def test_equals_uses_a_case_insensitive_collation(self):
        assert "COLLATE NOCASE" in compile_node(text("title", "x", "equals")).sql

    def test_compiling_something_that_is_not_a_node_fails_loudly(self):
        with pytest.raises(QueryCompilationError):
            compile_node("genre:techno")

    def test_fragment_str_is_its_sql(self):
        fragment = SqlFragment("1 = 1")
        assert str(fragment) == "1 = 1"


# =============================================================================
# Ejecución real contra SQLite
# =============================================================================

@pytest.fixture
def library(tmp_path):
    """Una librería chica pero con todos los casos borde que importan.

    Devuelve ``(repo, ids)`` donde ``ids`` mapea el nombre del track a su id.
    """
    db = DatabaseManager(db_path=tmp_path / "queries.db")
    repo = SqliteTagRepository(db=db)
    service = TaggingService(repo)

    catalogo = [
        # nombre,        artista,      dur,  bpm,   clave, energía, plataforma
        ("Peak Techno", "Ana", 400, 126.0, "8A", 9.0, "youtube"),
        ("Minimal Ride", "Beto", 380, 124.0, "8A", 5.0, "local"),
        ("Fast Hard", "Ana", 300, 145.0, "3B", 10.0, "youtube"),
        ("Slow Deep", "Cata", 500, 118.0, "5A", 3.0, "local"),
        ("Sin Analizar", "Dario", 250, None, None, None, "local"),
    ]
    ids: dict[str, str] = {}
    with db.get_connection() as conn:
        for title, artist, duration, bpm, key, energy, platform in catalogo:
            track_id = str(uuid.uuid4())
            ids[title] = track_id
            conn.execute(
                "INSERT INTO tracks (id, title, artist, duration, created_at, updated_at,"
                " source_platform) VALUES (?,?,?,?,?,?,?)",
                (track_id, title, artist, duration, _now(), _now(), platform),
            )
            if bpm is not None or key is not None or energy is not None:
                conn.execute(
                    "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level,"
                    " analyzed_at) VALUES (?,?,?,?,?)",
                    (track_id, bpm, key, energy, _now()),
                )
        conn.commit()

    service.backfill_derived()
    service.backfill_inherited()
    # Un par de tags manuales para probar que el motor no distingue la fuente.
    repo.assign(ids["Peak Techno"], _tag_obj("genre", "techno"))
    repo.assign(ids["Minimal Ride"], _tag_obj("genre", "minimal"))
    repo.assign(ids["Peak Techno"], _tag_obj("context", "peak-time"))
    return repo, ids


def _tag_obj(namespace, value):
    from domain.tags import Tag
    return Tag(namespace, value)


def _titles(repo, node) -> set:
    """Ejecuta el predicado y devuelve los títulos que matchean."""
    fragment = build_track_ids_query(node)
    with repo.db.get_connection() as conn:
        rows = conn.execute(fragment.sql, fragment.params).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        titles = conn.execute(
            f"SELECT title FROM tracks WHERE id IN ({placeholders})", ids
        ).fetchall()
    return {r[0] for r in titles}


class TestTagQueries:
    def test_derived_tag(self, library):
        repo, _ = library
        assert _titles(repo, tag("bpm", "120-129")) == {"Peak Techno", "Minimal Ride"}

    def test_manual_tag(self, library):
        repo, _ = library
        assert _titles(repo, tag("genre", "techno")) == {"Peak Techno"}

    def test_tag_that_nobody_has(self, library):
        repo, _ = library
        assert _titles(repo, tag("genre", "gabber")) == set()

    def test_tag_any(self, library):
        repo, _ = library
        # Todos los analizados tienen algún key:*; el sin analizar no.
        assert _titles(repo, tag_any("key")) == {
            "Peak Techno", "Minimal Ride", "Fast Hard", "Slow Deep"
        }

    def test_tag_any_on_an_empty_namespace(self, library):
        repo, _ = library
        assert _titles(repo, tag_any("mood")) == set()

    def test_the_engine_does_not_care_which_source_the_tag_came_from(self, library):
        repo, _ = library
        # key:8a es derived, genre:techno es manual; la misma query los cruza.
        assert _titles(repo, and_(tag("key", "8a"), tag("genre", "techno"))) == {
            "Peak Techno"
        }


class TestRangeAndCompare:
    def test_bpm_range(self, library):
        repo, _ = library
        assert _titles(repo, range_("bpm", 120, 130)) == {"Peak Techno", "Minimal Ride"}

    def test_open_range(self, library):
        repo, _ = library
        assert _titles(repo, range_("bpm", minimum=140)) == {"Fast Hard"}

    def test_duration_lives_on_tracks_not_analysis(self, library):
        repo, _ = library
        assert _titles(repo, compare("duration", "gt", 450)) == {"Slow Deep"}

    def test_energy_range(self, library):
        repo, _ = library
        assert _titles(repo, range_("energy", 9, 10)) == {"Peak Techno", "Fast Hard"}

    def test_is_null_finds_the_unanalyzed(self, library):
        repo, _ = library
        assert _titles(repo, compare("bpm", "is_null")) == {"Sin Analizar"}

    def test_not_null_finds_the_analyzed(self, library):
        repo, _ = library
        assert len(_titles(repo, compare("bpm", "not_null"))) == 4

    def test_an_unanalyzed_track_does_not_match_a_range(self, library):
        repo, _ = library
        assert "Sin Analizar" not in _titles(repo, range_("bpm", 0, 999))

    def test_an_unanalyzed_track_does_match_the_negated_range(self, library):
        # Es la consecuencia de colapsar la lógica de tres valores, y es la
        # que se quiere: si no se sabe que está en el rango, queda afuera del
        # rango.
        repo, _ = library
        assert "Sin Analizar" in _titles(repo, not_(range_("bpm", 0, 999)))


class TestTextAndSource:
    def test_contains_is_case_insensitive(self, library):
        repo, _ = library
        assert _titles(repo, text("title", "TECHNO")) == {"Peak Techno"}

    def test_starts_with(self, library):
        repo, _ = library
        assert _titles(repo, text("title", "Slow", "starts_with")) == {"Slow Deep"}

    def test_equals_is_exact_but_case_insensitive(self, library):
        repo, _ = library
        assert _titles(repo, text("artist", "ana", "equals")) == {"Peak Techno", "Fast Hard"}
        assert _titles(repo, text("artist", "An", "equals")) == set()

    def test_a_percent_in_the_search_is_a_literal_not_a_wildcard(self, library):
        repo, _ = library
        assert _titles(repo, text("title", "%")) == set()

    def test_source_platform(self, library):
        repo, _ = library
        assert _titles(repo, source("source_platform", "youtube")) == {
            "Peak Techno", "Fast Hard"
        }

    def test_source_is_case_insensitive(self, library):
        repo, _ = library
        assert len(_titles(repo, source("source_platform", "YouTube"))) == 2

    def test_a_null_column_does_not_match_a_source(self, library):
        repo, _ = library
        assert _titles(repo, source("source_playlist_name", "cualquiera")) == set()


class TestBooleans:
    def test_and(self, library):
        repo, _ = library
        node = and_(tag("bpm", "120-129"), range_("energy", 8, 10))
        assert _titles(repo, node) == {"Peak Techno"}

    def test_or(self, library):
        repo, _ = library
        node = or_(tag("genre", "techno"), tag("genre", "minimal"))
        assert _titles(repo, node) == {"Peak Techno", "Minimal Ride"}

    def test_not_over_a_tag_includes_everything_else(self, library):
        repo, _ = library
        assert _titles(repo, not_(tag("genre", "techno"))) == {
            "Minimal Ride", "Fast Hard", "Slow Deep", "Sin Analizar"
        }

    def test_the_example_from_the_architecture_doc(self, library):
        repo, _ = library
        node = and_(
            or_(tag("genre", "techno"), tag("genre", "minimal")),
            range_("bpm", 122, 128),
            not_(tag("context", "already-played")),
        )
        assert _titles(repo, node) == {"Peak Techno", "Minimal Ride"}

    def test_deep_nesting_executes(self, library):
        repo, _ = library
        node = and_(
            or_(
                and_(tag("key", "8a"), range_("energy", 8, 10)),
                and_(tag("key", "3b"), range_("bpm", 140, 160)),
            ),
            not_(source("source_platform", "local")),
        )
        assert _titles(repo, node) == {"Peak Techno", "Fast Hard"}


class TestCountQuery:
    def test_count_matches_the_id_query(self, library):
        repo, _ = library
        node = or_(tag("genre", "techno"), tag("genre", "minimal"))
        fragment = build_count_query(node)
        with repo.db.get_connection() as conn:
            count = conn.execute(fragment.sql, fragment.params).fetchone()[0]
        assert count == len(_titles(repo, node))

    def test_count_of_the_whole_library(self, library):
        repo, _ = library
        fragment = build_count_query(compare("duration", "gte", 0))
        with repo.db.get_connection() as conn:
            assert conn.execute(fragment.sql, fragment.params).fetchone()[0] == 5

    def test_an_unanalyzed_track_is_still_a_track(self, library):
        # El LEFT JOIN es lo que garantiza esto: sin él, los 3 tracks sin
        # analizar de la librería real desaparecerían de toda query.
        repo, _ = library
        fragment = build_count_query(compare("bpm", "is_null"))
        with repo.db.get_connection() as conn:
            assert conn.execute(fragment.sql, fragment.params).fetchone()[0] == 1
