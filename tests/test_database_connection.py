"""Comportamiento de las conexiones que entrega `DatabaseManager`."""

import sqlite3

import pytest

from infrastructure.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    return DatabaseManager(tmp_path / "library.db")


def test_the_with_block_closes_the_connection(db):
    # El `with` de sqlite3 sólo commitea: la conexión quedaba viva hasta el GC
    # y en Windows impedía mover o respaldar la base.
    with db.get_connection() as conn:
        conn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_the_with_block_still_commits(db):
    with db.get_connection() as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1


def test_an_error_rolls_back_and_closes(db):
    with db.get_connection() as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
    with pytest.raises(RuntimeError):
        with db.get_connection() as conn:
            conn.execute("INSERT INTO t VALUES (1)")
            raise RuntimeError("boom")
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


def test_the_database_runs_in_wal_mode(db):
    # Los lectores no bloquean al escritor: la descarga, el auto-tagging y el
    # análisis escriben desde hilos distintos.
    with db.get_connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
