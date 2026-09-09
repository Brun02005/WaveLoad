"""Evaluación de una `SmartCollection`: el fold de la pila de capas.

La pila no se recorre en memoria: se compila a una cadena de CTEs y la ejecuta
SQLite. ``layer_0`` es la librería completa, y cada ``layer_n`` se define en
términos de ``layer_n-1`` según su modo:

- ``filter``  -> intersección con los tracks que cumplen el predicado
- ``exclude`` -> diferencia
- ``union``   -> unión con los tracks de la **librería** que cumplen el predicado

``sort`` y ``limit`` se aplican una sola vez, al final, sobre el resultado del
fold. Nunca por capa.

Consecuencia del modelo, no del código: como la base implícita es la librería
completa, una capa ``union`` en la **primera** posición no agrega nada — ya está
todo adentro. Es esperado y hay un test que lo fija; el builder debería avisarlo
en la UI en vez de dejar al usuario preguntándose por qué su capa no hace nada.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Sequence

from domain.collections import LayerMode, QueryLayer, SmartCollection, SortDirection
from services.query_compiler import SqlFragment, compile_predicate, from_clause

# Alias propios para el JOIN de ordenamiento: la cadena de CTEs ya usa `t` y `a`
# adentro de cada predicado, y reusarlos acá sería pedir una ambigüedad.
SORT_COLUMNS: dict[str, str] = {
    "title": "st.title",
    "artist": "st.artist",
    "album": "st.album",
    "duration": "st.duration",
    "created_at": "st.created_at",
    "bpm": "sa.bpm",
    "energy": "sa.energy_level",
    "analyzed_at": "sa.analyzed_at",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayerCount:
    """Cuántos tracks quedan después de aplicar una capa.

    Es lo que el builder muestra al costado de cada capa para que se vea qué
    aporta cada paso. ``position`` es la de la capa; ``after`` es el tamaño del
    conjunto una vez aplicada.
    """
    position: int
    mode: LayerMode
    enabled: bool
    after: int
    description: str

    @property
    def label(self) -> str:
        # Flecha ASCII a propósito: esta etiqueta termina en logs, y la consola
        # de Windows es cp1252 — un "→" ahí levanta UnicodeEncodeError. El
        # proyecto ya tuvo problemas de logging en builds sin consola.
        return f"[{self.position}] {self.description} -> {self.after}"


@dataclass(frozen=True)
class EvaluationResult:
    """El resultado de evaluar una collection, con lo que costó."""
    track_ids: tuple[str, ...]
    total: int
    elapsed_ms: float
    truncated: bool = False

    def __len__(self) -> int:
        return len(self.track_ids)


def _layer_cte(layer: QueryLayer, index: int, first: bool = False) -> SqlFragment:
    """El SQL de una capa, definido en términos de la anterior.

    ``first`` marca que esta capa es la primera activa. Una capa ``filter`` en
    esa posición se intersecta con la librería completa, o sea que no se
    intersecta con nada: se emite directo el predicado y la CTE de la base
    desaparece de la consulta.
    """
    predicate = compile_predicate(layer.predicate)
    previous = f"layer_{index - 1}"
    matching = f"SELECT t.id {from_clause(layer.predicate)} WHERE {predicate.sql}"

    if first and layer.mode is LayerMode.FILTER:
        sql = f"SELECT t.id AS track_id {from_clause(layer.predicate)} WHERE {predicate.sql}"
    elif layer.mode is LayerMode.FILTER:
        sql = f"SELECT track_id FROM {previous} WHERE track_id IN ({matching})"
    elif layer.mode is LayerMode.EXCLUDE:
        sql = f"SELECT track_id FROM {previous} WHERE track_id NOT IN ({matching})"
    else:  # UNION
        sql = f"SELECT track_id FROM {previous} UNION {matching}"
    return SqlFragment(sql, predicate.params)


def build_layer_chain(collection: SmartCollection) -> tuple[str, tuple, str]:
    """Construye la cadena de CTEs.

    Devuelve ``(cláusula WITH, parámetros, nombre de la última CTE)``. Si no hay
    capas activas la cláusula es la sola ``layer_0``, que es la librería entera.
    """
    activas = collection.active_layers()
    # La CTE de la base sólo se emite si alguien la va a referenciar. Con una
    # primera capa `filter` —el caso normal— no hace falta, y sacarla ahorra
    # materializar los ids de la librería entera.
    base_necesaria = not activas or activas[0].mode is not LayerMode.FILTER

    partes = ["layer_0 AS (SELECT id AS track_id FROM tracks)"] if base_necesaria else []
    params: list = []

    for index, layer in enumerate(activas, start=1):
        fragmento = _layer_cte(layer, index, first=(index == 1))
        partes.append(f"layer_{index} AS ({fragmento.sql})")
        params.extend(fragmento.params)

    ultima = f"layer_{len(activas)}"
    return "WITH " + ",\n     ".join(partes), tuple(params), ultima


def build_collection_query(
    collection: SmartCollection,
    limit: Optional[int] = None,
    offset: int = 0,
) -> SqlFragment:
    """La consulta que devuelve los ids de la collection, ya ordenados.

    ``limit`` pisa el de la collection: es lo que usa la UI para pedir una
    página sin tocar la definición guardada.
    """
    with_clause, params, ultima = build_layer_chain(collection)
    parametros = list(params)

    sql = f"{with_clause}\nSELECT final.track_id FROM {ultima} final"

    if collection.sort is not None:
        # El JOIN sólo entra si hay por qué ordenar: sin sort, la cadena de
        # CTEs no necesita tocar `tracks` de nuevo.
        columna = SORT_COLUMNS[collection.sort.field]
        sql += (
            " JOIN tracks st ON st.id = final.track_id"
            " LEFT JOIN track_analysis sa ON sa.track_id = final.track_id"
        )
        sentido = "ASC" if collection.sort.direction is SortDirection.ASC else "DESC"
        # NULLS LAST: un track sin analizar no debería encabezar un orden por
        # BPM sólo por no tener BPM.
        sql += f" ORDER BY {columna} {sentido} NULLS LAST"

    efectivo = limit if limit is not None else collection.limit
    if efectivo is not None:
        sql += " LIMIT ?"
        parametros.append(efectivo)
        if offset:
            sql += " OFFSET ?"
            parametros.append(offset)
    elif offset:
        # SQLite exige LIMIT para aceptar OFFSET; -1 significa "sin tope".
        sql += " LIMIT -1 OFFSET ?"
        parametros.append(offset)

    return SqlFragment(sql, tuple(parametros))


def build_collection_count_query(collection: SmartCollection) -> SqlFragment:
    """Cuántos tracks devuelve la collection. Ignora `limit`: cuenta el fold."""
    with_clause, params, ultima = build_layer_chain(collection)
    return SqlFragment(f"{with_clause}\nSELECT COUNT(*) FROM {ultima}", params)


def build_layer_counts_query(collection: SmartCollection) -> SqlFragment:
    """El conteo después de cada capa, en una sola consulta.

    Una sola ida a la base en lugar de una por capa: las CTEs ya están todas
    definidas, así que contar cada una es un `SELECT` más en la misma
    sentencia.
    """
    with_clause, params, _ = build_layer_chain(collection)
    activas = collection.active_layers()
    # El conteo de la base se hace contra `tracks` y no contra `layer_0`: es más
    # barato, y además `layer_0` puede no haberse emitido.
    columnas = ["(SELECT COUNT(*) FROM tracks)"]
    columnas += [f"(SELECT COUNT(*) FROM layer_{i})" for i in range(1, len(activas) + 1)]
    return SqlFragment(f"{with_clause}\nSELECT {', '.join(columnas)}", params)


class CollectionEvaluator:
    """Ejecuta las consultas de una collection contra la librería.

    Recibe el ``DatabaseManager`` inyectado, como el resto de los servicios.
    """

    def __init__(self, db):
        self.db = db

    def evaluate(
        self,
        collection: SmartCollection,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> EvaluationResult:
        """Los ids de la collection. ``limit`` pide una página sin tocar la definición."""
        fragmento = build_collection_query(collection, limit=limit, offset=offset)
        inicio = time.perf_counter()
        with self.db.get_connection() as conn:
            filas = conn.execute(fragmento.sql, fragmento.params).fetchall()
        transcurrido = (time.perf_counter() - inicio) * 1000

        ids = tuple(fila[0] for fila in filas)
        tope = limit if limit is not None else collection.limit
        logger.debug(
            "Collection %r evaluada: %d tracks en %.1f ms", collection.name, len(ids), transcurrido
        )
        return EvaluationResult(
            track_ids=ids,
            total=len(ids),
            elapsed_ms=transcurrido,
            truncated=tope is not None and len(ids) == tope,
        )

    def count(self, collection: SmartCollection) -> int:
        """Cuántos tracks devuelve el fold, sin aplicar `limit`."""
        fragmento = build_collection_count_query(collection)
        with self.db.get_connection() as conn:
            return conn.execute(fragmento.sql, fragmento.params).fetchone()[0]

    def layer_counts(self, collection: SmartCollection) -> list[LayerCount]:
        """El conteo paso a paso, para mostrarlo al costado de cada capa.

        La primera entrada es la base (la librería completa) y tiene
        ``position = -1``: no corresponde a ninguna capa editable.

        Ojo con el costo: un `COUNT` no puede cortar temprano, así que esto es
        la operación más cara del motor. Sobre 50.000 tracks está en el orden de
        las décimas de segundo — la UI debería pedirlo fuera del hilo de dibujo.
        """
        fragmento = build_layer_counts_query(collection)
        with self.db.get_connection() as conn:
            fila = conn.execute(fragmento.sql, fragmento.params).fetchone()

        activas = collection.active_layers()
        resultado = [
            LayerCount(
                position=-1,
                mode=LayerMode.UNION,
                enabled=True,
                after=fila[0],
                description="base: librería completa",
            )
        ]
        for index, layer in enumerate(activas, start=1):
            resultado.append(
                LayerCount(
                    position=layer.position,
                    mode=layer.mode,
                    enabled=layer.enabled,
                    after=fila[index],
                    description=layer.describe(),
                )
            )
        return resultado

    def explain(self, collection: SmartCollection) -> list[str]:
        """El plan de ejecución de SQLite, para diagnosticar una query lenta."""
        fragmento = build_collection_query(collection)
        with self.db.get_connection() as conn:
            filas = conn.execute(
                "EXPLAIN QUERY PLAN " + fragmento.sql, fragmento.params
            ).fetchall()
        return [fila[-1] for fila in filas]
