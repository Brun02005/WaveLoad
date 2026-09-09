"""Puente entre el formulario de una capa y el AST.

El AST admite anidamiento arbitrario; un formulario razonable, no. Este módulo
define la forma que **sí** edita el builder visual —una lista plana de
condiciones unidas por AND o por OR, cada una negable— y la traduce en las dos
direcciones.

Es deliberado que no cubra todo el AST. Un AST que no entra en el formulario no
se rompe ni se recorta: ``LayerForm.from_ast`` devuelve ``None`` y la UI muestra
esa capa como texto de sólo lectura con su ``describe()``. Es la respuesta
honesta a "esta pila fue armada con algo más expresivo que este formulario", y
deja la puerta abierta a un DSL de texto sin tener que rehacer el builder.

Vive en `services/` y no en la UI: es lógica, y se testea sin levantar Qt.
"""

from dataclasses import dataclass, field
from typing import Optional, Sequence

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
    and_,
    not_,
    or_,
)

# Los nodos que el formulario sabe dibujar. Cualquier otra cosa —un `and` dentro
# de un `or`, por ejemplo— cae fuera.
LEAF_TYPES = (TagNode, TagAnyNode, RangeNode, CompareNode, TextNode, SourceNode)

JOIN_AND = "and"
JOIN_OR = "or"


class LayerFormError(ValueError):
    """El formulario no se puede convertir a un AST válido."""


@dataclass(frozen=True)
class Condition:
    """Una condición del formulario: un nodo hoja, opcionalmente negado."""
    node: Node
    negated: bool = False

    def __post_init__(self):
        if not isinstance(self.node, LEAF_TYPES):
            raise LayerFormError(
                f"Una condición del formulario tiene que ser un nodo simple, "
                f"se recibió {type(self.node).__name__}"
            )

    def to_ast(self) -> Node:
        return not_(self.node) if self.negated else self.node

    def describe(self) -> str:
        return f"no {self.node.describe()}" if self.negated else self.node.describe()


@dataclass
class LayerForm:
    """Una lista plana de condiciones unidas por AND o por OR.

    Mutable a propósito: es el estado de un formulario que el usuario está
    editando, no una entidad de dominio.
    """
    join: str = JOIN_AND
    conditions: list[Condition] = field(default_factory=list)

    def __post_init__(self):
        join = str(self.join).strip().lower()
        if join not in (JOIN_AND, JOIN_OR):
            raise LayerFormError(
                f"La unión de un formulario es {JOIN_AND!r} o {JOIN_OR!r}, "
                f"se recibió {self.join!r}"
            )
        self.join = join

    # --- edición ----------------------------------------------------------

    def add(self, node: Node, negated: bool = False) -> "LayerForm":
        self.conditions.append(Condition(node, negated))
        return self

    def remove(self, index: int) -> "LayerForm":
        if not 0 <= index < len(self.conditions):
            raise LayerFormError(f"No hay ninguna condición en la posición {index}")
        del self.conditions[index]
        return self

    def __len__(self) -> int:
        return len(self.conditions)

    # --- traducción -------------------------------------------------------

    def to_ast(self) -> Node:
        """El AST equivalente. Levanta si el formulario está vacío."""
        if not self.conditions:
            raise LayerFormError("Una capa necesita al menos una condición")

        partes = [condicion.to_ast() for condicion in self.conditions]
        if len(partes) == 1:
            # Una sola condición no se envuelve: `genre:techno` y
            # `and(genre:techno)` evalúan igual, pero el primero es el que se
            # lee bien en la pila y el que vuelve idéntico del round-trip.
            return partes[0]
        return and_(*partes) if self.join == JOIN_AND else or_(*partes)

    @classmethod
    def from_ast(cls, node: Node) -> Optional["LayerForm"]:
        """El formulario equivalente, o ``None`` si el AST no entra.

        No es un error que devuelva ``None``: significa que esa capa se armó con
        algo más expresivo que este formulario y hay que mostrarla de sólo
        lectura, no recortarla.
        """
        condicion = _as_condition(node)
        if condicion is not None:
            return cls(join=JOIN_AND, conditions=[condicion])

        if isinstance(node, BoolNode) and node.bool_op in (JOIN_AND, JOIN_OR):
            condiciones = []
            for hijo in node.nodes:
                convertida = _as_condition(hijo)
                if convertida is None:
                    return None  # hay anidamiento: no entra en el formulario
                condiciones.append(convertida)
            return cls(join=node.bool_op, conditions=condiciones)

        return None

    @classmethod
    def is_editable(cls, node: Node) -> bool:
        """Si esta capa se puede abrir en el builder visual."""
        return cls.from_ast(node) is not None

    def describe(self) -> str:
        if not self.conditions:
            return "(sin condiciones)"
        separador = " y " if self.join == JOIN_AND else " o "
        return separador.join(c.describe() for c in self.conditions)


def _as_condition(node: Node) -> Optional[Condition]:
    """Convierte una hoja, o un `not` sobre una hoja, en una condición."""
    if isinstance(node, LEAF_TYPES):
        return Condition(node, negated=False)
    if (
        isinstance(node, BoolNode)
        and node.bool_op == "not"
        and isinstance(node.nodes[0], LEAF_TYPES)
    ):
        return Condition(node.nodes[0], negated=True)
    return None
