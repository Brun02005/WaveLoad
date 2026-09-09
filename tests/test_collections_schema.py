"""Tests de la migración del motor de Collections.

Headless y sobre una DB temporal: importar ``infrastructure.database`` ya no
construye nada contra la librería real (la instancia global es perezosa).
"""

import sqlite3
import uuid
from datetime import datetime, timezone

import pytest

from infrastructure.database import DatabaseManager

COLLECTION_TABLES = {
    "tags",
    "track_tags",
    "collections",
    "collection_layers",
    "crates",
    "crate_entries",
}

COLLECTION_INDEXES = {
    "idx_track_tags_tag",
    "idx_track_tags_track",
    "idx_track_tags_source",
    "idx_tags_namespace",
    "idx_collection_layers_position",
    "idx_crate_entries_crate",
    "idx_track_analysis_bpm",
    "idx_track_analysis_energy",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tables(conn) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _indexes(conn) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}


@pytest.fixture
def db(tmp_path):
    """Un DatabaseManager sobre una DB temporal, ya migrada."""
    return DatabaseManager(db_path=tmp_path / "test_library.db")


@pytest.fixture
def seeded(db):
    """La misma DB con un track y su análisis, para probar las FK."""
    track_id = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO tracks (id, title, artist, created_at, updated_at) VALUES (?,?,?,?,?)",
            (track_id, "Test Track", "Test Artist", _now(), _now()),
        )
        conn.execute(
            "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level, analyzed_at)"
            " VALUES (?,?,?,?,?)",
            (track_id, 126.0, "8A", 7.0, _now()),
        )
        conn.commit()
    return db, track_id


class TestSchemaCreation:
    def test_creates_all_six_collection_tables(self, db):
        with db.get_connection() as conn:
            assert COLLECTION_TABLES <= _tables(conn)

    def test_creates_the_query_engine_indexes(self, db):
        with db.get_connection() as conn:
            assert COLLECTION_INDEXES <= _indexes(conn)

    def test_leaves_the_pre_existing_tables_alone(self, db):
        with db.get_connection() as conn:
            assert {"tracks", "track_assets", "track_analysis"} <= _tables(conn)

    def test_new_tables_start_empty(self, db):
        with db.get_connection() as conn:
            for table in COLLECTION_TABLES:
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


class TestIdempotence:
    def test_running_the_migration_twice_is_a_noop(self, tmp_path):
        path = tmp_path / "twice.db"
        first = DatabaseManager(db_path=path)
        with first.get_connection() as conn:
            tables_once, indexes_once = _tables(conn), _indexes(conn)

        second = DatabaseManager(db_path=path)  # corre las migraciones de nuevo
        with second.get_connection() as conn:
            assert _tables(conn) == tables_once
            assert _indexes(conn) == indexes_once
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    def test_migration_preserves_existing_rows(self, tmp_path):
        path = tmp_path / "preserve.db"
        db = DatabaseManager(db_path=path)
        track_id = str(uuid.uuid4())
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO tracks (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                (track_id, "Keep Me", _now(), _now()),
            )
            conn.commit()

        DatabaseManager(db_path=path)  # segunda corrida sobre datos existentes

        with db.get_connection() as conn:
            rows = conn.execute("SELECT id, title FROM tracks").fetchall()
        assert [(r[0], r[1]) for r in rows] == [(track_id, "Keep Me")]


class TestTagsTable:
    def test_namespace_value_pair_is_unique(self, db):
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO tags (namespace, value, created_at) VALUES (?,?,?)",
                ("genre", "techno", _now()),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO tags (namespace, value, created_at) VALUES (?,?,?)",
                    ("genre", "techno", _now()),
                )

    def test_same_value_in_two_namespaces_is_allowed(self, db):
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO tags (namespace, value, created_at) VALUES (?,?,?)",
                ("genre", "dark", _now()),
            )
            conn.execute(
                "INSERT INTO tags (namespace, value, created_at) VALUES (?,?,?)",
                ("mood", "dark", _now()),
            )
            assert conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 2


class TestTrackTagsTable:
    def _tag(self, conn, namespace="genre", value="techno") -> int:
        cur = conn.execute(
            "INSERT INTO tags (namespace, value, created_at) VALUES (?,?,?)",
            (namespace, value, _now()),
        )
        return cur.lastrowid

    def test_same_tag_from_two_sources_coexists(self, seeded):
        db, track_id = seeded
        with db.get_connection() as conn:
            tag_id = self._tag(conn)
            conn.execute(
                "INSERT INTO track_tags (track_id, tag_id, source, confidence, created_at)"
                " VALUES (?,?,?,?,?)",
                (track_id, tag_id, "manual", 1.0, _now()),
            )
            conn.execute(
                "INSERT INTO track_tags (track_id, tag_id, source, confidence, created_at)"
                " VALUES (?,?,?,?,?)",
                (track_id, tag_id, "ai", 0.72, _now()),
            )
            assert conn.execute("SELECT COUNT(*) FROM track_tags").fetchone()[0] == 2

    def test_same_tag_same_source_twice_is_rejected(self, seeded):
        db, track_id = seeded
        with db.get_connection() as conn:
            tag_id = self._tag(conn)
            conn.execute(
                "INSERT INTO track_tags (track_id, tag_id, source, confidence, created_at)"
                " VALUES (?,?,?,?,?)",
                (track_id, tag_id, "manual", 1.0, _now()),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO track_tags (track_id, tag_id, source, confidence, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (track_id, tag_id, "manual", 1.0, _now()),
                )

    def test_deleting_a_track_cascades_to_its_tags(self, seeded):
        db, track_id = seeded
        with db.get_connection() as conn:
            tag_id = self._tag(conn)
            conn.execute(
                "INSERT INTO track_tags (track_id, tag_id, source, confidence, created_at)"
                " VALUES (?,?,?,?,?)",
                (track_id, tag_id, "manual", 1.0, _now()),
            )
            conn.commit()
            conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
            assert conn.execute("SELECT COUNT(*) FROM track_tags").fetchone()[0] == 0
            # El vocabulario sobrevive: borrar un track no borra el tag.
            assert conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 1

    def test_deleting_a_tag_cascades_to_its_assignments(self, seeded):
        db, track_id = seeded
        with db.get_connection() as conn:
            tag_id = self._tag(conn)
            conn.execute(
                "INSERT INTO track_tags (track_id, tag_id, source, confidence, created_at)"
                " VALUES (?,?,?,?,?)",
                (track_id, tag_id, "manual", 1.0, _now()),
            )
            conn.commit()
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            assert conn.execute("SELECT COUNT(*) FROM track_tags").fetchone()[0] == 0

    def test_tag_on_a_nonexistent_track_is_rejected(self, db):
        with db.get_connection() as conn:
            tag_id = self._tag(conn)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO track_tags (track_id, tag_id, source, confidence, created_at)"
                    " VALUES (?,?,?,?,?)",
                    ("no-such-track", tag_id, "manual", 1.0, _now()),
                )


class TestCollectionsAndLayers:
    def _collection(self, conn, name="Peak time techno") -> int:
        cur = conn.execute(
            "INSERT INTO collections (name, sort_json, limit_n, ast_version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (name, None, None, 1, _now(), _now()),
        )
        return cur.lastrowid

    def test_collection_name_is_unique(self, db):
        with db.get_connection() as conn:
            self._collection(conn)
            with pytest.raises(sqlite3.IntegrityError):
                self._collection(conn)

    def test_ast_version_defaults_to_one(self, db):
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO collections (name, created_at, updated_at) VALUES (?,?,?)",
                ("Sin version", _now(), _now()),
            )
            assert conn.execute("SELECT ast_version FROM collections").fetchone()[0] == 1

    def test_two_layers_cannot_share_a_position(self, db):
        with db.get_connection() as conn:
            cid = self._collection(conn)
            conn.execute(
                "INSERT INTO collection_layers (collection_id, position, enabled, mode, ast_json)"
                " VALUES (?,?,?,?,?)",
                (cid, 0, 1, "filter", "{}"),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO collection_layers (collection_id, position, enabled, mode, ast_json)"
                    " VALUES (?,?,?,?,?)",
                    (cid, 0, 1, "exclude", "{}"),
                )

    def test_same_position_in_two_collections_is_fine(self, db):
        with db.get_connection() as conn:
            a = self._collection(conn, "A")
            b = self._collection(conn, "B")
            for cid in (a, b):
                conn.execute(
                    "INSERT INTO collection_layers (collection_id, position, enabled, mode, ast_json)"
                    " VALUES (?,?,?,?,?)",
                    (cid, 0, 1, "filter", "{}"),
                )
            assert conn.execute("SELECT COUNT(*) FROM collection_layers").fetchone()[0] == 2

    def test_deleting_a_collection_cascades_to_its_layers(self, db):
        with db.get_connection() as conn:
            cid = self._collection(conn)
            conn.execute(
                "INSERT INTO collection_layers (collection_id, position, enabled, mode, ast_json)"
                " VALUES (?,?,?,?,?)",
                (cid, 0, 1, "filter", "{}"),
            )
            conn.commit()
            conn.execute("DELETE FROM collections WHERE id = ?", (cid,))
            assert conn.execute("SELECT COUNT(*) FROM collection_layers").fetchone()[0] == 0


class TestCrates:
    def test_crate_name_is_unique(self, db):
        with db.get_connection() as conn:
            conn.execute("INSERT INTO crates (name, created_at, updated_at) VALUES (?,?,?)",
                         ("Set viernes", _now(), _now()))
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO crates (name, created_at, updated_at) VALUES (?,?,?)",
                             ("Set viernes", _now(), _now()))

    def test_a_track_appears_at_most_once_per_crate(self, seeded):
        db, track_id = seeded
        with db.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO crates (name, created_at, updated_at) VALUES (?,?,?)",
                ("Set viernes", _now(), _now()),
            )
            crate_id = cur.lastrowid
            conn.execute(
                "INSERT INTO crate_entries (crate_id, track_id, position) VALUES (?,?,?)",
                (crate_id, track_id, 0),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO crate_entries (crate_id, track_id, position) VALUES (?,?,?)",
                    (crate_id, track_id, 1),
                )

    def test_deleting_a_crate_cascades_to_its_entries(self, seeded):
        db, track_id = seeded
        with db.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO crates (name, created_at, updated_at) VALUES (?,?,?)",
                ("Temporal", _now(), _now()),
            )
            crate_id = cur.lastrowid
            conn.execute(
                "INSERT INTO crate_entries (crate_id, track_id, position) VALUES (?,?,?)",
                (crate_id, track_id, 0),
            )
            conn.commit()
            conn.execute("DELETE FROM crates WHERE id = ?", (crate_id,))
            assert conn.execute("SELECT COUNT(*) FROM crate_entries").fetchone()[0] == 0
