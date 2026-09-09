"""Entidades de Collections: la pila de capas, las smart collections y los crates.

`SmartCollection` y `Crate` son entidades **separadas**, no dos modos de una
misma cosa. Una smart collection es una pila de capas que se re-evalúa siempre;
un crate es una lista fija y ordenada de tracks. Una smart collection no admite
tracks fijados a mano ni exclusiones puntuales: si hace falta control manual
sobre el resultado, se materializa a un crate.

Módulo puro: sin Qt, sin SQL. La evaluación vive en
``services/collection_evaluator.py``.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence

from domain.query_ast import AST_VERSION, Node, QueryASTError, parse


class LayerMode(str, Enum):
    """Cómo transforma una capa el conjunto que le llega de la anterior.

    Hereda de ``str`` para bindearse directo a la columna ``mode``.
    """
    FILTER = "filter"    # se queda con los que cumplen (intersección)
    EXCLUDE = "exclude"  # saca a los que cumplen (diferencia)
    UNION = "union"      # agrega los de la librería que cumplen (unión)


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


# Campos por los que se puede ordenar el resultado. Es un conjunto distinto de
# los campos consultables: se puede ordenar por título, pero filtrar por título
# es un nodo `text`, no un `compare`.
SORTABLE_FIELDS: frozenset[str] = frozenset({
    "title", "artist", "album", "duration", "bpm", "energy",
    "created_at", "analyzed_at",
})


class CollectionError(ValueError):
    """La collection está mal formada."""


@dataclass(frozen=True)
class SortSpec:
    """Por qué campo y en qué sentido se ordena el resultado final."""
    field: str
    direction: SortDirection = SortDirection.ASC

    def __post_init__(self):
        name = str(self.field).strip().lower()
        if name not in SORTABLE_FIELDS:
            raise CollectionError(
                f"No se puede ordenar por {self.field!r}. "
                f"Campos ordenables: {', '.join(sorted(SORTABLE_FIELDS))}"
            )
        object.__setattr__(self, "field", name)
        object.__setattr__(self, "direction", SortDirection(self.direction))

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction.value}

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional["SortSpec"]:
        if not data:
            return None
        if "field" not in data:
            raise CollectionError("Un sort necesita 'field'")
        return cls(data["field"], SortDirection(data.get("direction", "asc")))

    def describe(self) -> str:
        sentido = "ascendente" if self.direction is SortDirection.ASC else "descendente"
        return f"por {self.field} {sentido}"


@dataclass(frozen=True)
class QueryLayer:
    """Una capa de la pila: un predicado más el modo con que se aplica."""
    predicate: Node
    mode: LayerMode = LayerMode.FILTER
    position: int = 0
    enabled: bool = True
    id: Optional[int] = None

    def __post_init__(self):
        object.__setattr__(self, "mode", LayerMode(self.mode))
        if not isinstance(self.predicate, Node):
            raise CollectionError(
                f"El predicado de una capa tiene que ser un nodo del AST, "
                f"se recibió {type(self.predicate).__name__}"
            )
        if self.position < 0:
            raise CollectionError(f"Posición de capa inválida: {self.position}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position,
            "enabled": self.enabled,
            "mode": self.mode.value,
            "ast": self.predicate.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueryLayer":
        try:
            predicate = parse(data["ast"])
        except KeyError as exc:
            raise CollectionError("A una capa le falta 'ast'") from exc
        except QueryASTError as exc:
            raise CollectionError(f"AST inválido en la capa: {exc}") from exc
        return cls(
            predicate=predicate,
            mode=LayerMode(data.get("mode", "filter")),
            position=int(data.get("position", 0)),
            enabled=bool(data.get("enabled", True)),
            id=data.get("id"),
        )

    def describe(self) -> str:
        etiqueta = {"filter": "filtrar", "exclude": "excluir", "union": "sumar"}
        estado = "" if self.enabled else " [apagada]"
        return f"{etiqueta[self.mode.value]}: {self.predicate.describe()}{estado}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SmartCollection:
    """Una pila ordenada de capas sobre la librería completa.

    La base implícita es la librería entera; cada capa recibe el conjunto que
    produjo la anterior. Reordenar cambia el resultado cuando hay capas `union`
    involucradas: el orden es semántico, no cosmético.

    ``sort`` y ``limit`` se aplican **una sola vez, al final**, sobre el
    resultado del fold — nunca por capa.
    """
    name: str
    layers: tuple[QueryLayer, ...] = ()
    sort: Optional[SortSpec] = None
    limit: Optional[int] = None
    ast_version: int = AST_VERSION
    id: Optional[int] = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self):
        if not str(self.name).strip():
            raise CollectionError("Una collection necesita un nombre")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "layers", tuple(self.layers))
        if self.limit is not None and self.limit <= 0:
            raise CollectionError(f"El límite tiene que ser positivo, se recibió {self.limit}")
        for layer in self.layers:
            if not isinstance(layer, QueryLayer):
                raise CollectionError(
                    f"Capa inválida: {type(layer).__name__}"
                )
        posiciones = [layer.position for layer in self.layers]
        if len(set(posiciones)) != len(posiciones):
            raise CollectionError(f"Hay capas con la misma posición: {sorted(posiciones)}")

    # --- lectura ----------------------------------------------------------

    def ordered_layers(self) -> tuple[QueryLayer, ...]:
        """Todas las capas por posición, incluidas las apagadas."""
        return tuple(sorted(self.layers, key=lambda layer: layer.position))

    def active_layers(self) -> tuple[QueryLayer, ...]:
        """Las capas que participan de la evaluación, en orden."""
        return tuple(layer for layer in self.ordered_layers() if layer.enabled)

    def describe(self) -> str:
        lineas = [f"{self.name}:", "  base: librería completa"]
        for index, layer in enumerate(self.ordered_layers(), start=1):
            lineas.append(f"  [{index}] {layer.describe()}")
        if self.sort:
            lineas.append(f"  orden: {self.sort.describe()}")
        if self.limit:
            lineas.append(f"  límite: {self.limit}")
        return "\n".join(lineas)

    # --- edición (devuelve copias; la entidad es inmutable) ---------------

    def with_layer(self, layer: QueryLayer) -> "SmartCollection":
        """Agrega una capa al final de la pila."""
        siguiente = max((l.position for l in self.layers), default=-1) + 1
        nueva = replace(layer, position=siguiente)
        return replace(self, layers=self.layers + (nueva,), updated_at=_now())

    def without_layer(self, position: int) -> "SmartCollection":
        """Saca la capa de esa posición y compacta las posiciones restantes."""
        quedan = [l for l in self.ordered_layers() if l.position != position]
        if len(quedan) == len(self.layers):
            raise CollectionError(f"No hay ninguna capa en la posición {position}")
        return replace(self, layers=_repositioned(quedan), updated_at=_now())

    def with_layer_toggled(self, position: int, enabled: bool) -> "SmartCollection":
        """Prende o apaga una capa sin borrarla."""
        encontrada = False
        nuevas = []
        for layer in self.ordered_layers():
            if layer.position == position:
                encontrada = True
                nuevas.append(replace(layer, enabled=enabled))
            else:
                nuevas.append(layer)
        if not encontrada:
            raise CollectionError(f"No hay ninguna capa en la posición {position}")
        return replace(self, layers=tuple(nuevas), updated_at=_now())

    def with_layer_moved(self, desde: int, hasta: int) -> "SmartCollection":
        """Mueve una capa de una posición a otra, corriendo las del medio."""
        capas = list(self.ordered_layers())
        indices = {layer.position: i for i, layer in enumerate(capas)}
        if desde not in indices:
            raise CollectionError(f"No hay ninguna capa en la posición {desde}")
        if not 0 <= hasta < len(capas):
            raise CollectionError(
                f"Posición destino fuera de rango: {hasta} (hay {len(capas)} capas)"
            )
        capa = capas.pop(indices[desde])
        capas.insert(hasta, capa)
        return replace(self, layers=_repositioned(capas), updated_at=_now())


def _repositioned(capas: Sequence[QueryLayer]) -> tuple[QueryLayer, ...]:
    """Renumera las posiciones a 0..n-1 conservando el orden dado."""
    return tuple(replace(layer, position=i) for i, layer in enumerate(capas))


@dataclass(frozen=True)
class Crate:
    """Colección manual: una lista fija y ordenada de tracks."""
    name: str
    track_ids: tuple[str, ...] = ()
    id: Optional[int] = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self):
        if not str(self.name).strip():
            raise CollectionError("Un crate necesita un nombre")
        object.__setattr__(self, "name", str(self.name).strip())
        ids = tuple(self.track_ids)
        if len(set(ids)) != len(ids):
            raise CollectionError("Un track no puede estar dos veces en el mismo crate")
        object.__setattr__(self, "track_ids", ids)

    def with_track(self, track_id: str, position: Optional[int] = None) -> "Crate":
        """Agrega un track. Sin posición, va al final. Repetirlo no hace nada."""
        if track_id in self.track_ids:
            return self
        ids = list(self.track_ids)
        ids.insert(len(ids) if position is None else position, track_id)
        return replace(self, track_ids=tuple(ids), updated_at=_now())

    def without_track(self, track_id: str) -> "Crate":
        if track_id not in self.track_ids:
            return self
        ids = [t for t in self.track_ids if t != track_id]
        return replace(self, track_ids=tuple(ids), updated_at=_now())

    def moved(self, desde: int, hasta: int) -> "Crate":
        """Cambia un track de posición dentro del crate."""
        ids = list(self.track_ids)
        if not 0 <= desde < len(ids):
            raise CollectionError(f"Posición de origen fuera de rango: {desde}")
        if not 0 <= hasta < len(ids):
            raise CollectionError(f"Posición destino fuera de rango: {hasta}")
        ids.insert(hasta, ids.pop(desde))
        return replace(self, track_ids=tuple(ids), updated_at=_now())

    def __len__(self) -> int:
        return len(self.track_ids)
