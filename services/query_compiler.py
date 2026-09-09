"""Compilación del AST de predicados a SQL parametrizado.

Traduce un ``domain.query_ast.Node`` a un fragmento de SQL booleano más su
tupla de parámetros. El trabajo de filtrar lo hace SQLite, que es lo que
escala a decenas de miles de tracks; cargar la librería en memoria y filtrar
en Python no.

**Los valores viajan siempre bindeados, nunca interpolados en el string.** Lo
único que este módulo escribe literalmente en el SQL son nombres de columna que
salen de un diccionario cerrado, y ningún valor del usuario llega a ser parte
de la sentencia.

Semántica de tres valores: en SQL, una comparación contra NULL da NULL, no
falso. El predicado se colapsa a dos valores —es verdadero o falso para cada
track, nunca "desconocido"— pero **sólo donde hace falta**, que es adentro de un
``NOT``. En el nivel superior no se envuelve nada: un ``WHERE`` ya descarta las
filas que dan NULL, y envolverlo en ``COALESCE`` le impide a SQLite usar el
índice de la columna (medido: un rango de BPM sobre 50.000 tracks pasa de 270 ms
a 403 ms sólo por ese COALESCE de más).

Consecuencia concreta y deseada de las dos cosas: un track sin analizar **no**
cumple ``bpm entre 122 y 128``, y **sí** cumple ``NOT (bpm entre 122 y 128)``.
"""

from dataclasses import dataclass
from typing import Any

from domain.query_ast import (
    BoolNode,
    CompareNode,
    Node,
    QueryASTError,
    RangeNode,
    SourceNode,
    TagAnyNode,
    TagNode,
    TextNode,
)

# Alias de las tablas en la consulta base. `a` entra por LEFT JOIN: un track sin
# analizar sigue siendo un track de la librería, sólo que con bpm/clave/energía
# en NULL.
TRACKS = "t"
ANALYSIS = "a"

BASE_FROM = (
    f"FROM tracks {TRACKS} "
    f"LEFT JOIN track_analysis {ANALYSIS} ON {ANALYSIS}.track_id = {TRACKS}.id"
)

# Único lugar donde un campo del AST se convierte en una columna. Cerrado: si un
# campo no está acá, el AST ya lo rechazó antes de llegar.
COLUMNS: dict[str, str] = {
    "bpm": f"{ANALYSIS}.bpm",
    "energy": f"{ANALYSIS}.energy_level",
    "duration": f"{TRACKS}.duration",
    "title": f"{TRACKS}.title",
    "artist": f"{TRACKS}.artist",
    "album": f"{TRACKS}.album",
    "created_at": f"{TRACKS}.created_at",
    "analyzed_at": f"{ANALYSIS}.analyzed_at",
    "source_platform": f"{TRACKS}.source_platform",
    "source_playlist_name": f"{TRACKS}.source_playlist_name",
}

_COMPARATOR_SQL: dict[str, str] = {
    "eq": "=",
    "ne": "!=",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
}

# Carácter de escape de LIKE. Sin esto, un `%` tipeado por el usuario en una
# búsqueda de texto se comporta como comodín.
_LIKE_ESCAPE = "\\"


class QueryCompilationError(ValueError):
    """El AST es sintácticamente válido pero no se puede compilar."""


@dataclass(frozen=True)
class SqlFragment:
    """Un pedazo de SQL booleano con sus parámetros, en orden."""
    sql: str
    params: tuple[Any, ...] = ()

    def __str__(self) -> str:
        return self.sql


def _escape_like(value: str) -> str:
    """Neutraliza los comodines de LIKE en un texto tipeado por el usuario."""
    return (
        str(value)
        .replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )


def _column(field: str) -> str:
    try:
        return COLUMNS[field]
    except KeyError as exc:  # pragma: no cover - el AST ya validó el campo
        raise QueryCompilationError(f"Campo sin columna asociada: {field!r}") from exc


def compile_node(node: Node) -> SqlFragment:
    """Compila un nodo del AST a un fragmento booleano parametrizado."""
    if isinstance(node, BoolNode):
        return _compile_bool(node)
    if isinstance(node, TagNode):
        return _compile_tag(node)
    if isinstance(node, TagAnyNode):
        return _compile_tag_any(node)
    if isinstance(node, RangeNode):
        return _compile_range(node)
    if isinstance(node, CompareNode):
        return _compile_compare(node)
    if isinstance(node, TextNode):
        return _compile_text(node)
    if isinstance(node, SourceNode):
        return _compile_source(node)
    raise QueryCompilationError(f"Tipo de nodo no compilable: {type(node).__name__}")


def _compile_bool(node: BoolNode) -> SqlFragment:
    parts = [compile_node(child) for child in node.nodes]
    params: tuple[Any, ...] = tuple(p for part in parts for p in part.params)

    if node.bool_op == "not":
        # COALESCE colapsa la lógica de tres valores: sin esto, negar un
        # predicado sobre una columna NULL daría NULL y el track se perdería
        # de los dos lados de la negación.
        return SqlFragment(f"(NOT COALESCE({parts[0].sql}, 0))", params)

    joiner = " AND " if node.bool_op == "and" else " OR "
    return SqlFragment("(" + joiner.join(p.sql for p in parts) + ")", params)


# Los nodos de tag se compilan como `id IN (subconsulta)` y no como un
# `EXISTS` correlacionado. Las dos formas son equivalentes en semántica —
# `track_tags.track_id` es parte de la PK, así que nunca es NULL y el `IN` no
# puede dar NULL— pero el `EXISTS` se re-evalúa una vez por track, mientras que
# la subconsulta se materializa una sola vez y SQLite la cruza con un filtro de
# Bloom. Medido sobre 50.000 tracks: un predicado con ocho tags en OR baja de
# 1571 ms a 757 ms sólo por este cambio.
def _compile_tag(node: TagNode) -> SqlFragment:
    sql = (
        f"{TRACKS}.id IN (SELECT tt.track_id FROM track_tags tt"
        " JOIN tags tg ON tg.id = tt.tag_id WHERE tg.namespace = ? AND tg.value = ?)"
    )
    return SqlFragment(sql, (node.namespace, node.value))


def _compile_tag_any(node: TagAnyNode) -> SqlFragment:
    sql = (
        f"{TRACKS}.id IN (SELECT tt.track_id FROM track_tags tt"
        " JOIN tags tg ON tg.id = tt.tag_id WHERE tg.namespace = ?)"
    )
    return SqlFragment(sql, (node.namespace,))


def _compile_range(node: RangeNode) -> SqlFragment:
    column = _column(node.field)
    if node.min is not None and node.max is not None:
        return SqlFragment(f"({column} BETWEEN ? AND ?)", (node.min, node.max))
    if node.min is not None:
        return SqlFragment(f"({column} >= ?)", (node.min,))
    return SqlFragment(f"({column} <= ?)", (node.max,))


def _compile_compare(node: CompareNode) -> SqlFragment:
    column = _column(node.field)
    if node.cmp == "is_null":
        return SqlFragment(f"({column} IS NULL)")
    if node.cmp == "not_null":
        return SqlFragment(f"({column} IS NOT NULL)")
    return SqlFragment(f"({column} {_COMPARATOR_SQL[node.cmp]} ?)", (node.value,))


def _compile_text(node: TextNode) -> SqlFragment:
    column = _column(node.field)
    # LIKE en SQLite ya es insensible a mayúsculas para ASCII, así que no hace
    # falta LOWER() —que además sólo cubriría ASCII igual—. La igualdad usa
    # COLLATE NOCASE por la misma razón.
    if node.mode == "equals":
        return SqlFragment(f"({column} = ? COLLATE NOCASE)", (node.value,))
    pattern = _escape_like(node.value)
    if node.mode == "starts_with":
        pattern = f"{pattern}%"
    else:  # contains
        pattern = f"%{pattern}%"
    return SqlFragment(f"({column} LIKE ? ESCAPE '{_LIKE_ESCAPE}')", (pattern,))


def _compile_source(node: SourceNode) -> SqlFragment:
    column = _column(node.field)
    return SqlFragment(f"({column} = ? COLLATE NOCASE)", (node.value,))


def compile_predicate(node: Node) -> SqlFragment:
    """Compila un predicado completo, listo para poner en un ``WHERE``.

    No envuelve el resultado en ``COALESCE``: el ``WHERE`` ya descarta las filas
    que evalúan a NULL, así que sería redundante, y cuesta el uso del índice.
    Donde el colapso a dos valores sí importa —adentro de un ``NOT``— lo hace
    ``_compile_bool``.
    """
    return compile_node(node)


def build_track_ids_query(node: Node) -> SqlFragment:
    """La consulta que devuelve los ``tracks.id`` que cumplen el predicado."""
    predicate = compile_predicate(node)
    sql = f"SELECT {TRACKS}.id {BASE_FROM} WHERE {predicate.sql}"
    return SqlFragment(sql, predicate.params)


def build_count_query(node: Node) -> SqlFragment:
    """La consulta que cuenta los tracks que cumplen el predicado."""
    predicate = compile_predicate(node)
    sql = f"SELECT COUNT(*) {BASE_FROM} WHERE {predicate.sql}"
    return SqlFragment(sql, predicate.params)
