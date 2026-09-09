"""Persistencia de smart collections y crates sobre SQLite.

Guarda y lee las entidades de ``domain/collections.py``. El predicado de cada
capa viaja como JSON en ``collection_layers.ast_json``; nunca se guarda texto de
una query, porque el texto sería una vista sobre el AST y no al revés.

Guardar una collection **reemplaza su pila entera** en una transacción: borra
las capas viejas y escribe las nuevas. Es más simple y más seguro que
diferenciar capa por capa, y el costo es despreciable — una pila tiene unidades
de capas, no miles.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from domain.collections import (
    CollectionError,
    Crate,
    QueryLayer,
    SmartCollection,
    SortSpec,
)
from domain.query_ast import AST_VERSION

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)


class CollectionNotFound(CollectionError):
    """Se pidió una collection o un crate que no existe."""


class UnsupportedAstVersion(CollectionError):
    """La collection fue guardada por una versión posterior del AST."""


class SqliteCollectionRepository:
    """Lee y escribe ``collections``, ``collection_layers``, ``crates`` y ``crate_entries``."""

    def __init__(self, db=None):
        if db is None:
            from infrastructure.database import get_db_manager
            db = get_db_manager()
        self.db = db

    # =====================================================================
    # Smart collections
    # =====================================================================

    def save(self, collection: SmartCollection) -> SmartCollection:
        """Inserta o actualiza la collection y reemplaza su pila de capas.

        Devuelve la collection con el ``id`` asignado. Todo pasa en una sola
        transacción: no existe el estado intermedio donde la cabecera se guardó
        y las capas no.
        """
        sort_json = json.dumps(collection.sort.to_dict()) if collection.sort else None
        ahora = _now()

        conn = self.db.get_connection()
        try:
            conn.execute("BEGIN")
            if collection.id is None:
                cur = conn.execute(
                    "INSERT INTO collections (name, sort_json, limit_n, ast_version,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (collection.name, sort_json, collection.limit,
                     collection.ast_version, ahora, ahora),
                )
                collection_id = cur.lastrowid
            else:
                collection_id = collection.id
                cur = conn.execute(
                    "UPDATE collections SET name = ?, sort_json = ?, limit_n = ?,"
                    " ast_version = ?, updated_at = ? WHERE id = ?",
                    (collection.name, sort_json, collection.limit,
                     collection.ast_version, ahora, collection_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise CollectionNotFound(
                        f"No existe la collection con id {collection_id}"
                    )
                conn.execute(
                    "DELETE FROM collection_layers WHERE collection_id = ?",
                    (collection_id,),
                )

            for layer in collection.ordered_layers():
                conn.execute(
                    "INSERT INTO collection_layers (collection_id, position, enabled,"
                    " mode, ast_json) VALUES (?,?,?,?,?)",
                    (
                        collection_id,
                        layer.position,
                        1 if layer.enabled else 0,
                        layer.mode.value,
                        json.dumps(layer.predicate.to_dict()),
                    ),
                )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            if "collections.name" in str(exc) or "UNIQUE" in str(exc).upper():
                raise CollectionError(
                    f"Ya existe una collection llamada {collection.name!r}"
                ) from exc
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        logger.info("Collection %r guardada (id=%s)", collection.name, collection_id)
        return self.get(collection_id)

    def get(self, collection_id: int) -> SmartCollection:
        with self.db.get_connection() as conn:
            fila = conn.execute(
                "SELECT id, name, sort_json, limit_n, ast_version, created_at, updated_at"
                " FROM collections WHERE id = ?",
                (collection_id,),
            ).fetchone()
            if fila is None:
                raise CollectionNotFound(f"No existe la collection con id {collection_id}")
            capas = self._load_layers(conn, collection_id)
        return self._build(fila, capas)

    def get_by_name(self, name: str) -> SmartCollection:
        with self.db.get_connection() as conn:
            fila = conn.execute(
                "SELECT id FROM collections WHERE name = ?", (str(name).strip(),)
            ).fetchone()
        if fila is None:
            raise CollectionNotFound(f"No existe ninguna collection llamada {name!r}")
        return self.get(fila[0])

    def list_all(self) -> list[SmartCollection]:
        """Todas las collections, por nombre. Carga sus capas."""
        with self.db.get_connection() as conn:
            filas = conn.execute(
                "SELECT id, name, sort_json, limit_n, ast_version, created_at, updated_at"
                " FROM collections ORDER BY name COLLATE NOCASE"
            ).fetchall()
            return [self._build(fila, self._load_layers(conn, fila[0])) for fila in filas]

    def list_names(self) -> list[tuple[int, str]]:
        """``(id, nombre)`` de cada collection, sin cargar las capas.

        Es lo que necesita el sidebar: mostrar la lista no debería costar
        parsear el AST de todas las pilas guardadas.
        """
        with self.db.get_connection() as conn:
            return [
                (fila[0], fila[1])
                for fila in conn.execute(
                    "SELECT id, name FROM collections ORDER BY name COLLATE NOCASE"
                )
            ]

    def delete(self, collection_id: int) -> bool:
        """Borra la collection y sus capas (cascada). Devuelve si existía."""
        with self.db.get_connection() as conn:
            cur = conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            conn.commit()
            return cur.rowcount > 0

    def exists(self, name: str) -> bool:
        with self.db.get_connection() as conn:
            return conn.execute(
                "SELECT 1 FROM collections WHERE name = ?", (str(name).strip(),)
            ).fetchone() is not None

    # --- interno ----------------------------------------------------------

    def _load_layers(self, conn: sqlite3.Connection, collection_id: int) -> list[QueryLayer]:
        filas = conn.execute(
            "SELECT id, position, enabled, mode, ast_json FROM collection_layers"
            " WHERE collection_id = ? ORDER BY position",
            (collection_id,),
        ).fetchall()
        capas = []
        for fila in filas:
            try:
                ast = json.loads(fila[4])
            except json.JSONDecodeError as exc:
                raise CollectionError(
                    f"La capa {fila[0]} de la collection {collection_id} tiene un "
                    f"ast_json ilegible: {exc}"
                ) from exc
            capas.append(
                QueryLayer.from_dict(
                    {
                        "id": fila[0],
                        "position": fila[1],
                        "enabled": bool(fila[2]),
                        "mode": fila[3],
                        "ast": ast,
                    }
                )
            )
        return capas

    def _build(self, fila, capas) -> SmartCollection:
        ast_version = fila[4]
        if ast_version > AST_VERSION:
            raise UnsupportedAstVersion(
                f"La collection {fila[1]!r} fue guardada con ast_version={ast_version} "
                f"y esta versión de WaveLoad entiende hasta {AST_VERSION}"
            )
        sort = SortSpec.from_dict(json.loads(fila[2])) if fila[2] else None
        return SmartCollection(
            id=fila[0],
            name=fila[1],
            layers=tuple(capas),
            sort=sort,
            limit=fila[3],
            ast_version=ast_version,
            created_at=_parse_dt(fila[5]),
            updated_at=_parse_dt(fila[6]),
        )

    # =====================================================================
    # Crates
    # =====================================================================

    def save_crate(self, crate: Crate) -> Crate:
        """Inserta o actualiza el crate y reemplaza su lista de tracks."""
        ahora = _now()
        conn = self.db.get_connection()
        try:
            conn.execute("BEGIN")
            if crate.id is None:
                cur = conn.execute(
                    "INSERT INTO crates (name, created_at, updated_at) VALUES (?,?,?)",
                    (crate.name, ahora, ahora),
                )
                crate_id = cur.lastrowid
            else:
                crate_id = crate.id
                cur = conn.execute(
                    "UPDATE crates SET name = ?, updated_at = ? WHERE id = ?",
                    (crate.name, ahora, crate_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise CollectionNotFound(f"No existe el crate con id {crate_id}")
                conn.execute("DELETE FROM crate_entries WHERE crate_id = ?", (crate_id,))

            conn.executemany(
                "INSERT INTO crate_entries (crate_id, track_id, position) VALUES (?,?,?)",
                [(crate_id, track_id, i) for i, track_id in enumerate(crate.track_ids)],
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            if "crates.name" in str(exc):
                raise CollectionError(f"Ya existe un crate llamado {crate.name!r}") from exc
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        logger.info("Crate %r guardado (id=%s, %d tracks)", crate.name, crate_id, len(crate))
        return self.get_crate(crate_id)

    def get_crate(self, crate_id: int) -> Crate:
        with self.db.get_connection() as conn:
            fila = conn.execute(
                "SELECT id, name, created_at, updated_at FROM crates WHERE id = ?",
                (crate_id,),
            ).fetchone()
            if fila is None:
                raise CollectionNotFound(f"No existe el crate con id {crate_id}")
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT track_id FROM crate_entries WHERE crate_id = ? ORDER BY position",
                    (crate_id,),
                )
            ]
        return Crate(
            id=fila[0],
            name=fila[1],
            track_ids=tuple(ids),
            created_at=_parse_dt(fila[2]),
            updated_at=_parse_dt(fila[3]),
        )

    def list_crates(self) -> list[Crate]:
        with self.db.get_connection() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM crates ORDER BY name COLLATE NOCASE"
            )]
        return [self.get_crate(crate_id) for crate_id in ids]

    def delete_crate(self, crate_id: int) -> bool:
        with self.db.get_connection() as conn:
            cur = conn.execute("DELETE FROM crates WHERE id = ?", (crate_id,))
            conn.commit()
            return cur.rowcount > 0
