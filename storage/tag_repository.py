"""Persistencia de tags y asignaciones sobre SQLite.

Es la contraparte de almacenamiento de ``domain/tags.py``: el dominio define
qué es un tag, este módulo sabe cómo guardarlo. La lógica de *qué* tag
corresponde a un track vive en ``services/tagging_service.py``, que no toca SQL.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional, Sequence

from domain.tags import Tag, TagAssignment, TagSource

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteTagRepository:
    """Lee y escribe ``tags`` y ``track_tags``.

    Recibe el ``DatabaseManager`` inyectado, igual que ``SqliteTrackRepository``,
    para que los tests corran sobre una DB temporal.
    """

    def __init__(self, db=None):
        if db is None:
            from infrastructure.database import get_db_manager
            db = get_db_manager()
        self.db = db

    # --- vocabulario ------------------------------------------------------

    def get_or_create_tag_id(self, tag: Tag, conn: sqlite3.Connection) -> int:
        """Devuelve el id del tag, creándolo si no existía.

        Recibe la conexión en lugar de abrir una propia: casi siempre se llama
        dentro de una transacción más grande, y abrir una segunda conexión sobre
        el mismo archivo es cómo se consigue un ``database is locked``.
        """
        row = conn.execute(
            "SELECT id FROM tags WHERE namespace = ? AND value = ?",
            (tag.namespace, tag.value),
        ).fetchone()
        if row is not None:
            return row[0]
        cur = conn.execute(
            "INSERT INTO tags (namespace, value, created_at) VALUES (?,?,?)",
            (tag.namespace, tag.value, _now()),
        )
        return cur.lastrowid

    def all_tags(self) -> list[Tag]:
        """El vocabulario completo, ordenado por namespace y valor."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, namespace, value FROM tags ORDER BY namespace, value"
            ).fetchall()
        return [Tag(namespace=r[1], value=r[2], id=r[0]) for r in rows]

    def count_by_namespace(self) -> dict[str, int]:
        """Cuántos *valores distintos* tiene cada namespace del vocabulario."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT namespace, COUNT(*) FROM tags GROUP BY namespace ORDER BY namespace"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def values_in_namespace(self, namespace: str) -> list[str]:
        """Los valores que existen en un namespace, ordenados.

        Es lo que llena el desplegable del builder: el usuario elige entre los
        valores que su librería tiene de verdad, en vez de tipear a ciegas y
        crear `techno` cuando ya existía `techno` con otro nombre.
        """
        with self.db.get_connection() as conn:
            return [
                fila[0]
                for fila in conn.execute(
                    "SELECT value FROM tags WHERE namespace = ? ORDER BY value",
                    (str(namespace).strip().lower(),),
                )
            ]

    def usage_by_namespace(self, namespace: str) -> list[tuple[str, int]]:
        """``(valor, cuántos tracks lo tienen)`` de un namespace, de mayor a menor.

        El builder los muestra en este orden: un valor que tienen 400 tracks es
        más probable que el que tiene 1.
        """
        with self.db.get_connection() as conn:
            return [
                (fila[0], fila[1])
                for fila in conn.execute(
                    "SELECT t.value, COUNT(DISTINCT tt.track_id) FROM tags t"
                    " LEFT JOIN track_tags tt ON tt.tag_id = t.id"
                    " WHERE t.namespace = ? GROUP BY t.value"
                    " ORDER BY COUNT(DISTINCT tt.track_id) DESC, t.value",
                    (str(namespace).strip().lower(),),
                )
            ]

    def delete_unused_tags(self) -> int:
        """Borra entradas del vocabulario que no tiene asignada ningún track.

        No se llama sola: limpiar el vocabulario es una acción explícita, porque
        un tag sin uso todavía puede ser un valor que el usuario quiere tipear
        de nuevo mañana.
        """
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM track_tags)"
            )
            conn.commit()
            return cur.rowcount

    # --- asignaciones -----------------------------------------------------

    def assign(
        self,
        track_id: str,
        tag: Tag,
        source: TagSource = TagSource.MANUAL,
        confidence: float = 1.0,
    ) -> None:
        """Asigna un tag a un track. Repetir la misma asignación no falla."""
        with self.db.get_connection() as conn:
            tag_id = self.get_or_create_tag_id(tag, conn)
            conn.execute(
                "INSERT OR IGNORE INTO track_tags"
                " (track_id, tag_id, source, confidence, created_at) VALUES (?,?,?,?,?)",
                (track_id, tag_id, source.value, confidence, _now()),
            )
            conn.commit()

    def unassign(self, track_id: str, tag: Tag, source: Optional[TagSource] = None) -> int:
        """Quita un tag de un track. Sin ``source``, lo quita de todas las fuentes."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM tags WHERE namespace = ? AND value = ?",
                (tag.namespace, tag.value),
            ).fetchone()
            if row is None:
                return 0
            if source is None:
                cur = conn.execute(
                    "DELETE FROM track_tags WHERE track_id = ? AND tag_id = ?",
                    (track_id, row[0]),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM track_tags WHERE track_id = ? AND tag_id = ? AND source = ?",
                    (track_id, row[0], source.value),
                )
            conn.commit()
            return cur.rowcount

    def tags_for_track(
        self, track_id: str, source: Optional[TagSource] = None
    ) -> list[TagAssignment]:
        """Las asignaciones de un track, opcionalmente filtradas por fuente."""
        sql = (
            "SELECT t.id, t.namespace, t.value, tt.source, tt.confidence, tt.created_at"
            " FROM track_tags tt JOIN tags t ON t.id = tt.tag_id"
            " WHERE tt.track_id = ?"
        )
        params: list = [track_id]
        if source is not None:
            sql += " AND tt.source = ?"
            params.append(source.value)
        sql += " ORDER BY t.namespace, t.value"

        with self.db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            TagAssignment(
                track_id=track_id,
                tag=Tag(namespace=r[1], value=r[2], id=r[0]),
                source=TagSource(r[3]),
                confidence=r[4],
                created_at=datetime.fromisoformat(r[5]),
            )
            for r in rows
        ]

    def tags_for_tracks(
        self,
        track_ids: Sequence[str],
        namespaces: Optional[Iterable[str]] = None,
    ) -> dict[str, list[Tag]]:
        """Los tags de varios tracks en una consulta, sin repetir los que llegan
        por más de una fuente. Para llenar una tabla entera sin una consulta
        por fila."""
        resultado: dict[str, list[Tag]] = {str(t): [] for t in track_ids}
        if not resultado:
            return resultado
        filtro_ns = ""
        extra: list = []
        if namespaces is not None:
            ns = list(namespaces)
            filtro_ns = f" AND t.namespace IN ({','.join('?' * len(ns))})"
            extra = ns
        ids = list(resultado)
        with self.db.get_connection() as conn:
            for i in range(0, len(ids), 500):
                lote = ids[i:i + 500]
                filas = conn.execute(
                    "SELECT DISTINCT tt.track_id, t.id, t.namespace, t.value"
                    " FROM track_tags tt JOIN tags t ON t.id = tt.tag_id"
                    f" WHERE tt.track_id IN ({','.join('?' * len(lote))}){filtro_ns}"
                    " ORDER BY t.namespace, t.value",
                    [*lote, *extra],
                ).fetchall()
                for track_id, tag_id, namespace, value in filas:
                    resultado[track_id].append(Tag(namespace=namespace, value=value, id=tag_id))
        return resultado

    def edit_tags(
        self,
        track_ids: Sequence[str],
        add: Iterable[Tag] = (),
        remove: Iterable[Tag] = (),
        source: TagSource = TagSource.MANUAL,
    ) -> tuple[int, int]:
        """Agrega y quita tags de una fuente en varios tracks, en una sola
        transacción. Devuelve (asignaciones agregadas, asignaciones quitadas).

        Quitar sólo toca la fuente pedida: sacar el ``genre:techno`` que puso el
        usuario no borra el que haya propuesto la IA.
        """
        add, remove = list(add), list(remove)
        agregados = quitados = 0
        ahora = _now()
        with self.db.get_connection() as conn:
            for tag in add:
                tag_id = self.get_or_create_tag_id(tag, conn)
                for track_id in track_ids:
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO track_tags"
                        " (track_id, tag_id, source, confidence, created_at) VALUES (?,?,?,?,?)",
                        (str(track_id), tag_id, source.value, 1.0, ahora),
                    )
                    agregados += cur.rowcount
            for tag in remove:
                row = conn.execute(
                    "SELECT id FROM tags WHERE namespace = ? AND value = ?",
                    (tag.namespace, tag.value),
                ).fetchone()
                if row is None:
                    continue
                for track_id in track_ids:
                    cur = conn.execute(
                        "DELETE FROM track_tags WHERE track_id = ? AND tag_id = ? AND source = ?",
                        (str(track_id), row[0], source.value),
                    )
                    quitados += cur.rowcount
        return agregados, quitados

    def track_ids_with_tag(self, tag: Tag) -> list[str]:
        """Qué tracks tienen este tag, sin importar de qué fuente vino."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT tt.track_id FROM track_tags tt"
                " JOIN tags t ON t.id = tt.tag_id"
                " WHERE t.namespace = ? AND t.value = ?",
                (tag.namespace, tag.value),
            ).fetchall()
        return [r[0] for r in rows]

    def count_assignments(self, source: Optional[TagSource] = None) -> int:
        sql = "SELECT COUNT(*) FROM track_tags"
        params: tuple = ()
        if source is not None:
            sql += " WHERE source = ?"
            params = (source.value,)
        with self.db.get_connection() as conn:
            return conn.execute(sql, params).fetchone()[0]

    # --- reemplazo por fuente --------------------------------------------

    def set_tags_for_source(
        self,
        track_id: str,
        source: TagSource,
        tags: Sequence[Tag],
        confidence: float = 1.0,
        conn: Optional[sqlite3.Connection] = None,
    ) -> tuple[int, int]:
        """Deja las asignaciones de ``source`` en exactamente ``tags``.

        Devuelve ``(agregadas, quitadas)``. Es la operación que hace idempotente
        el recálculo de tags automáticos: borra sólo filas de *esta* fuente, así
        que lo que puso el usuario a mano nunca se toca. Las asignaciones que ya
        estaban y siguen estando no se reescriben, de modo que conservan su
        ``created_at`` original.

        Si se pasa ``conn``, se usa esa conexión y **no** se hace commit: es
        responsabilidad de quien abrió la transacción.
        """
        owns_connection = conn is None
        if owns_connection:
            conn = self.db.get_connection()
        try:
            desired = {t.key: t for t in tags}

            current_rows = conn.execute(
                "SELECT tt.tag_id, t.namespace, t.value FROM track_tags tt"
                " JOIN tags t ON t.id = tt.tag_id"
                " WHERE tt.track_id = ? AND tt.source = ?",
                (track_id, source.value),
            ).fetchall()
            current = {f"{r[1]}:{r[2]}": r[0] for r in current_rows}

            to_remove = [tag_id for key, tag_id in current.items() if key not in desired]
            if to_remove:
                conn.executemany(
                    "DELETE FROM track_tags WHERE track_id = ? AND tag_id = ? AND source = ?",
                    [(track_id, tag_id, source.value) for tag_id in to_remove],
                )

            added = 0
            now = _now()
            for key, tag in desired.items():
                if key in current:
                    continue
                tag_id = self.get_or_create_tag_id(tag, conn)
                conn.execute(
                    "INSERT OR IGNORE INTO track_tags"
                    " (track_id, tag_id, source, confidence, created_at) VALUES (?,?,?,?,?)",
                    (track_id, tag_id, source.value, confidence, now),
                )
                added += 1

            if owns_connection:
                conn.commit()
            return added, len(to_remove)
        finally:
            if owns_connection:
                conn.close()

    # --- lectura de la librería para el backfill --------------------------

    def iter_analyzed_tracks(self) -> Iterator[tuple[str, Optional[float], Optional[str], Optional[float]]]:
        """``(track_id, bpm, musical_key, energy_level)`` de cada track analizado."""
        with self.db.get_connection() as conn:
            for row in conn.execute(
                "SELECT track_id, bpm, musical_key, energy_level FROM track_analysis"
            ):
                yield (row[0], row[1], row[2], row[3])

    def iter_track_sources(self) -> Iterator[tuple[str, Optional[str], Optional[str]]]:
        """``(track_id, source_platform, source_playlist_name)`` de cada track."""
        with self.db.get_connection() as conn:
            for row in conn.execute(
                "SELECT id, source_platform, source_playlist_name FROM tracks"
            ):
                yield (row[0], row[1], row[2])
