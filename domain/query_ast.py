"""El AST de los predicados de una capa de query.

Una capa de una `SmartCollection` guarda su predicado como AST en JSON, nunca
como texto: el texto —si algún día hay un DSL— es una vista sobre el AST, igual
que el builder visual. Las dos interfaces editan esta misma estructura.

Módulo puro: sin Qt, sin SQL, sin sqlite. Define la *forma* del predicado y qué
es válido; traducirlo a SQL es trabajo de ``services/query_compiler.py``.

La lista de operadores y campos es **cerrada** (sección 4.4 de `ARQUITECTURA.md`).
Un operador desconocido o un campo no consultable es un error explícito, no algo
que se ignore en silencio: una collection guardada que no se puede evaluar tiene
que decirlo, no devolver resultados incompletos.

Ejemplo::

    node = and_(
        or_(tag("genre", "techno"), tag("genre", "minimal")),
        range_("bpm", 122, 128),
        not_(tag("context", "already-played")),
    )
    json.dumps(node.to_dict())
"""

from dataclasses import dataclass
from typing import Any, Iterator, Optional, Sequence

from domain.tags import UnknownNamespaceError, normalize_value, validate_namespace

# Versión de la forma del JSON. Se guarda en `collections.ast_version` para
# poder migrar la estructura sin romper colecciones ya guardadas.
AST_VERSION = 1


class QueryASTError(ValueError):
    """El AST recibido no es válido: operador, campo o forma incorrectos."""


# --- Campos consultables ----------------------------------------------------
# Todos existen hoy como columna. Nada del compilador depende de datos que
# todavía no están.

NUMERIC_FIELDS: frozenset[str] = frozenset({"bpm", "energy", "duration"})
TEXT_FIELDS: frozenset[str] = frozenset({"title", "artist", "album"})
DATE_FIELDS: frozenset[str] = frozenset({"created_at", "analyzed_at"})
SOURCE_FIELDS: frozenset[str] = frozenset({"source_platform", "source_playlist_name"})

# Sobre qué campos tiene sentido un `range` o un `compare`: los ordenables.
ORDERED_FIELDS: frozenset[str] = NUMERIC_FIELDS | DATE_FIELDS
ALL_FIELDS: frozenset[str] = NUMERIC_FIELDS | TEXT_FIELDS | DATE_FIELDS | SOURCE_FIELDS

COMPARATORS: frozenset[str] = frozenset(
    {"eq", "ne", "lt", "lte", "gt", "gte", "is_null", "not_null"}
)
# Comparadores que no llevan valor a la derecha.
UNARY_COMPARATORS: frozenset[str] = frozenset({"is_null", "not_null"})

TEXT_MODES: frozenset[str] = frozenset({"contains", "equals", "starts_with"})

BOOL_OPS: frozenset[str] = frozenset({"and", "or", "not"})

OPERATORS: frozenset[str] = BOOL_OPS | {
    "tag", "tag_any", "range", "compare", "text", "source"
}


# --- Nodos ------------------------------------------------------------------

class Node:
    """Base de todos los nodos. Cada subclase sabe serializarse y describirse."""

    op: str

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - contrato
        raise NotImplementedError

    def children(self) -> tuple["Node", ...]:
        """Los hijos directos. Las hojas devuelven la tupla vacía."""
        return ()

    def walk(self) -> Iterator["Node"]:
        """Recorre el árbol en preorden, incluyéndose a sí mismo."""
        yield self
        for child in self.children():
            yield from child.walk()

    def describe(self) -> str:  # pragma: no cover - contrato
        """Una línea legible del predicado, para logs y para la UI."""
        raise NotImplementedError

    def __str__(self) -> str:
        return self.describe()


@dataclass(frozen=True)
class BoolNode(Node):
    """`and` / `or` / `not`. `not` lleva exactamente un hijo."""
    bool_op: str
    nodes: tuple[Node, ...]

    def __post_init__(self):
        op = str(self.bool_op).strip().lower()
        if op not in BOOL_OPS:
            raise QueryASTError(
                f"Operador booleano desconocido: {self.bool_op!r}. "
                f"Válidos: {', '.join(sorted(BOOL_OPS))}"
            )
        object.__setattr__(self, "bool_op", op)
        object.__setattr__(self, "nodes", tuple(self.nodes))

        if not self.nodes:
            raise QueryASTError(f"Un nodo {op!r} necesita al menos un hijo")
        if op == "not" and len(self.nodes) != 1:
            raise QueryASTError(
                f"Un nodo 'not' lleva exactamente un hijo, se recibieron {len(self.nodes)}"
            )
        for child in self.nodes:
            if not isinstance(child, Node):
                raise QueryASTError(f"Hijo inválido en un nodo {op!r}: {child!r}")

    @property
    def op(self) -> str:  # type: ignore[override]
        return self.bool_op

    def children(self) -> tuple[Node, ...]:
        return self.nodes

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.bool_op, "children": [n.to_dict() for n in self.nodes]}

    def describe(self) -> str:
        if self.bool_op == "not":
            return f"NOT ({self.nodes[0].describe()})"
        joiner = f" {self.bool_op.upper()} "
        return "(" + joiner.join(n.describe() for n in self.nodes) + ")"


@dataclass(frozen=True)
class TagNode(Node):
    """El track tiene el tag ``namespace:value``, de la fuente que sea."""
    namespace: str
    value: str
    op: str = "tag"

    def __post_init__(self):
        try:
            object.__setattr__(self, "namespace", validate_namespace(self.namespace))
            object.__setattr__(self, "value", normalize_value(self.value))
        except (UnknownNamespaceError, ValueError) as exc:
            raise QueryASTError(str(exc)) from exc

    def to_dict(self) -> dict[str, Any]:
        return {"op": "tag", "namespace": self.namespace, "value": self.value}

    def describe(self) -> str:
        return f"{self.namespace}:{self.value}"


@dataclass(frozen=True)
class TagAnyNode(Node):
    """El track tiene *algún* tag en ese namespace, cualquiera sea el valor."""
    namespace: str
    op: str = "tag_any"

    def __post_init__(self):
        try:
            object.__setattr__(self, "namespace", validate_namespace(self.namespace))
        except UnknownNamespaceError as exc:
            raise QueryASTError(str(exc)) from exc

    def to_dict(self) -> dict[str, Any]:
        return {"op": "tag_any", "namespace": self.namespace}

    def describe(self) -> str:
        return f"tiene algún {self.namespace}:*"


def _check_field(field: str, allowed: frozenset[str], op: str) -> str:
    name = str(field).strip().lower()
    if name not in allowed:
        raise QueryASTError(
            f"Campo no consultable con {op!r}: {field!r}. "
            f"Válidos: {', '.join(sorted(allowed))}"
        )
    return name


@dataclass(frozen=True)
class RangeNode(Node):
    """Intervalo **cerrado** sobre un campo ordenable. Al menos un extremo."""
    field: str
    min: Optional[Any] = None
    max: Optional[Any] = None
    op: str = "range"

    def __post_init__(self):
        object.__setattr__(self, "field", _check_field(self.field, ORDERED_FIELDS, "range"))
        if self.min is None and self.max is None:
            raise QueryASTError(
                f"Un 'range' sobre {self.field!r} necesita al menos un extremo (min o max)"
            )
        if self.min is not None and self.max is not None:
            try:
                inverted = self.min > self.max
            except TypeError as exc:
                raise QueryASTError(
                    f"Extremos incomparables en el 'range' sobre {self.field!r}: "
                    f"{self.min!r} y {self.max!r}"
                ) from exc
            if inverted:
                raise QueryASTError(
                    f"Rango invertido sobre {self.field!r}: min={self.min!r} > max={self.max!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"op": "range", "field": self.field}
        if self.min is not None:
            data["min"] = self.min
        if self.max is not None:
            data["max"] = self.max
        return data

    def describe(self) -> str:
        if self.min is not None and self.max is not None:
            return f"{self.field} entre {self.min} y {self.max}"
        if self.min is not None:
            return f"{self.field} >= {self.min}"
        return f"{self.field} <= {self.max}"


@dataclass(frozen=True)
class CompareNode(Node):
    """Comparación sobre un campo ordenable. `is_null`/`not_null` no llevan valor."""
    field: str
    cmp: str
    value: Optional[Any] = None
    op: str = "compare"

    def __post_init__(self):
        object.__setattr__(self, "field", _check_field(self.field, ORDERED_FIELDS, "compare"))
        comparator = str(self.cmp).strip().lower()
        if comparator not in COMPARATORS:
            raise QueryASTError(
                f"Comparador desconocido: {self.cmp!r}. "
                f"Válidos: {', '.join(sorted(COMPARATORS))}"
            )
        object.__setattr__(self, "cmp", comparator)

        if comparator in UNARY_COMPARATORS:
            if self.value is not None:
                raise QueryASTError(f"El comparador {comparator!r} no lleva valor")
        elif self.value is None:
            raise QueryASTError(f"El comparador {comparator!r} necesita un valor")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"op": "compare", "field": self.field, "cmp": self.cmp}
        if self.cmp not in UNARY_COMPARATORS:
            data["value"] = self.value
        return data

    def describe(self) -> str:
        symbols = {"eq": "=", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
        if self.cmp == "is_null":
            return f"{self.field} sin dato"
        if self.cmp == "not_null":
            return f"{self.field} con dato"
        return f"{self.field} {symbols[self.cmp]} {self.value}"


@dataclass(frozen=True)
class TextNode(Node):
    """Búsqueda de texto sobre `title` / `artist` / `album`. Case-insensitive."""
    field: str
    value: str
    mode: str = "contains"
    op: str = "text"

    def __post_init__(self):
        object.__setattr__(self, "field", _check_field(self.field, TEXT_FIELDS, "text"))
        mode = str(self.mode).strip().lower()
        if mode not in TEXT_MODES:
            raise QueryASTError(
                f"Modo de texto desconocido: {self.mode!r}. "
                f"Válidos: {', '.join(sorted(TEXT_MODES))}"
            )
        object.__setattr__(self, "mode", mode)
        if not str(self.value).strip():
            raise QueryASTError(f"Un 'text' sobre {self.field!r} necesita algo que buscar")
        object.__setattr__(self, "value", str(self.value))

    def to_dict(self) -> dict[str, Any]:
        return {"op": "text", "field": self.field, "value": self.value, "mode": self.mode}

    def describe(self) -> str:
        verbs = {"contains": "contiene", "equals": "es", "starts_with": "empieza con"}
        return f"{self.field} {verbs[self.mode]} {self.value!r}"


@dataclass(frozen=True)
class SourceNode(Node):
    """Procedencia del track. Igualdad exacta, insensible a mayúsculas."""
    field: str
    value: str
    op: str = "source"

    def __post_init__(self):
        object.__setattr__(self, "field", _check_field(self.field, SOURCE_FIELDS, "source"))
        if not str(self.value).strip():
            raise QueryASTError(f"Un 'source' sobre {self.field!r} necesita un valor")
        object.__setattr__(self, "value", str(self.value).strip())

    def to_dict(self) -> dict[str, Any]:
        return {"op": "source", "field": self.field, "value": self.value}

    def describe(self) -> str:
        return f"{self.field} = {self.value!r}"


# --- Constructores cómodos --------------------------------------------------

def and_(*nodes: Node) -> BoolNode:
    return BoolNode("and", tuple(nodes))


def or_(*nodes: Node) -> BoolNode:
    return BoolNode("or", tuple(nodes))


def not_(node: Node) -> BoolNode:
    return BoolNode("not", (node,))


def tag(namespace: str, value: str) -> TagNode:
    return TagNode(namespace, value)


def tag_any(namespace: str) -> TagAnyNode:
    return TagAnyNode(namespace)


def range_(field: str, minimum: Optional[Any] = None, maximum: Optional[Any] = None) -> RangeNode:
    return RangeNode(field, minimum, maximum)


def compare(field: str, cmp: str, value: Optional[Any] = None) -> CompareNode:
    return CompareNode(field, cmp, value)


def text(field: str, value: str, mode: str = "contains") -> TextNode:
    return TextNode(field, value, mode)


def source(field: str, value: str) -> SourceNode:
    return SourceNode(field, value)


# --- Parseo -----------------------------------------------------------------

def parse(data: Any) -> Node:
    """Construye un AST desde el dict que salió del JSON guardado.

    Levanta ``QueryASTError`` con un mensaje entendible ante cualquier cosa que
    no sea un AST válido — incluida una llave de más, que casi siempre es un
    typo o un AST de otra versión.
    """
    if not isinstance(data, dict):
        raise QueryASTError(f"Un nodo tiene que ser un objeto JSON, se recibió {type(data).__name__}")

    raw_op = data.get("op")
    if raw_op is None:
        raise QueryASTError(f"Nodo sin 'op': {sorted(data)}")
    op = str(raw_op).strip().lower()
    if op not in OPERATORS:
        raise QueryASTError(
            f"Operador desconocido: {raw_op!r}. Válidos: {', '.join(sorted(OPERATORS))}"
        )

    expected: dict[str, set[str]] = {
        "and": {"op", "children"},
        "or": {"op", "children"},
        "not": {"op", "children"},
        "tag": {"op", "namespace", "value"},
        "tag_any": {"op", "namespace"},
        "range": {"op", "field", "min", "max"},
        "compare": {"op", "field", "cmp", "value"},
        "text": {"op", "field", "value", "mode"},
        "source": {"op", "field", "value"},
    }
    unexpected = set(data) - expected[op]
    if unexpected:
        raise QueryASTError(
            f"Llaves inesperadas en un nodo {op!r}: {', '.join(sorted(unexpected))}"
        )

    def _required(key: str) -> Any:
        if key not in data:
            raise QueryASTError(f"A un nodo {op!r} le falta {key!r}")
        return data[key]

    if op in BOOL_OPS:
        children = _required("children")
        if not isinstance(children, list):
            raise QueryASTError(f"'children' de un nodo {op!r} tiene que ser una lista")
        return BoolNode(op, tuple(parse(child) for child in children))
    if op == "tag":
        return TagNode(_required("namespace"), _required("value"))
    if op == "tag_any":
        return TagAnyNode(_required("namespace"))
    if op == "range":
        return RangeNode(_required("field"), data.get("min"), data.get("max"))
    if op == "compare":
        return CompareNode(_required("field"), _required("cmp"), data.get("value"))
    if op == "text":
        return TextNode(_required("field"), _required("value"), data.get("mode", "contains"))
    return SourceNode(_required("field"), _required("value"))


def parse_many(items: Sequence[Any]) -> tuple[Node, ...]:
    return tuple(parse(item) for item in items)
