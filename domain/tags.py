"""Vocabulario de tags y entidades del motor de Collections.

Módulo puro: no importa Qt, ni sqlite, ni nada de infraestructura. Define
*qué* es un tag y qué namespaces existen; el *cómo* se persiste vive en
``storage/`` y el cómo se derivan en ``services/tagging_service.py``.

Un tag es siempre ``namespace:value``. El namespace es vocabulario controlado
(lista cerrada, ver ``NAMESPACES``); el valor es libre dentro de su namespace.
Que el namespace sea obligatorio es lo que hace legibles y componibles las
capas de query: una capa opera sobre un eje, no sobre una nube de etiquetas.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import re
import unicodedata


class TagSource(str, Enum):
    """De dónde salió una asignación de tag.

    El valor de cada miembro es el string que se guarda en la columna
    ``track_tags.source``; hereda de ``str`` para poder bindearlo directo a
    SQLite sin conversión.
    """
    MANUAL = "manual"        # lo puso el usuario
    DERIVED = "derived"      # derivado del análisis (bpm / clave / energía)
    INHERITED = "inherited"  # heredado del origen (plataforma / playlist)
    AI = "ai"                # clasificación automática por modelo

    @property
    def is_automatic(self) -> bool:
        """Las fuentes automáticas se recalculan solas; ``manual`` nunca se toca."""
        return self is not TagSource.MANUAL


# --- Namespaces de v1 -------------------------------------------------------
# Lista cerrada. El usuario crea *valores* libremente dentro de cada namespace,
# pero no crea namespaces desde la UI en v1. Agregar uno es agregar una línea
# acá: no requiere migración, porque la columna es TEXT.

NS_GENRE = "genre"        # manual + ai
NS_MOOD = "mood"          # manual + ai
NS_CONTEXT = "context"    # manual: dónde entra el track en un set
NS_STATUS = "status"      # manual: estado de curaduría del track
NS_BPM = "bpm"            # derived: bucket de tempo
NS_KEY = "key"            # derived: código Camelot
NS_ENERGY = "energy"      # derived: banda de energía
NS_SOURCE = "source"      # inherited: plataforma de origen
NS_PLAYLIST = "playlist"  # inherited: playlist de origen

NAMESPACES: tuple[str, ...] = (
    NS_GENRE,
    NS_MOOD,
    NS_CONTEXT,
    NS_STATUS,
    NS_BPM,
    NS_KEY,
    NS_ENERGY,
    NS_SOURCE,
    NS_PLAYLIST,
)

# Qué fuente produce cada namespace. Un namespace derivado o heredado no se
# edita a mano: la UI de tagging manual sólo ofrece los de MANUAL_NAMESPACES.
DERIVED_NAMESPACES: frozenset[str] = frozenset({NS_BPM, NS_KEY, NS_ENERGY})
INHERITED_NAMESPACES: frozenset[str] = frozenset({NS_SOURCE, NS_PLAYLIST})
AI_NAMESPACES: frozenset[str] = frozenset({NS_GENRE, NS_MOOD})
MANUAL_NAMESPACES: frozenset[str] = frozenset(
    {NS_GENRE, NS_MOOD, NS_CONTEXT, NS_STATUS}
)


class UnknownNamespaceError(ValueError):
    """Se intentó usar un namespace fuera del vocabulario cerrado."""


# Los valores se normalizan a slug para que ``Peak Time``, ``peak-time`` y
# ``PEAK TIME`` sean el mismo tag. Se guarda siempre el slug; la UI puede
# mostrar una versión bonita, pero la identidad es el slug.
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def normalize_value(value: str) -> str:
    """Normaliza el valor de un tag a slug minúsculo con guiones.

    ``"Peak Time"`` -> ``"peak-time"``; ``"Drum & Bass"`` -> ``"drum-bass"``.
    Levanta ``ValueError`` si no queda nada después de normalizar.
    """
    # Sin acentos antes de slugificar: "Reggaetón" -> "reggaeton", no
    # "reggaet-n". Con géneros en castellano (cumbia, reggaetón, electrónica)
    # descartar la letra acentuada partía la palabra.
    sin_acentos = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", sin_acentos.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"El valor de tag {value!r} queda vacío al normalizar")
    return slug


def validate_namespace(namespace: str) -> str:
    """Devuelve el namespace si pertenece al vocabulario; si no, levanta."""
    ns = namespace.strip().lower()
    if ns not in NAMESPACES:
        raise UnknownNamespaceError(
            f"Namespace desconocido: {namespace!r}. Válidos: {', '.join(NAMESPACES)}"
        )
    return ns


@dataclass(frozen=True)
class Tag:
    """Una entrada del vocabulario. Único por (namespace, value)."""
    namespace: str
    value: str
    id: Optional[int] = None

    def __post_init__(self):
        # frozen=True: hay que escribir por object.__setattr__
        object.__setattr__(self, "namespace", validate_namespace(self.namespace))
        object.__setattr__(self, "value", normalize_value(self.value))

    @property
    def key(self) -> str:
        """Representación canónica ``namespace:value``."""
        return f"{self.namespace}:{self.value}"

    def __str__(self) -> str:
        return self.key

    @classmethod
    def parse(cls, text: str) -> "Tag":
        """Construye un Tag desde ``"genre:techno"``."""
        if ":" not in text:
            raise ValueError(
                f"Un tag tiene que ser 'namespace:value', se recibió {text!r}"
            )
        ns, _, value = text.partition(":")
        return cls(namespace=ns, value=value)


@dataclass(frozen=True)
class TagAssignment:
    """La asignación de un tag a un track, con su procedencia.

    La clave primaria en la DB es ``(track_id, tag_id, source)``: el mismo tag
    puede venir de dos fuentes a la vez (el usuario puso ``genre:techno`` y la
    IA también). Coexisten; nunca se pisan.
    """
    track_id: str
    tag: Tag
    source: TagSource = TagSource.MANUAL
    confidence: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
