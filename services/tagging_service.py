"""Derivación y herencia de tags.

Lógica pura, sin Qt: traduce lo que ya sabe la librería —el análisis (BPM,
clave Camelot, energía) y el origen (plataforma, playlist)— a tags del
vocabulario definido en ``domain/tags.py``.

Dos garantías que valen para todo lo de acá:

1. **Nada automático pisa lo manual.** El recálculo reemplaza únicamente las
   asignaciones de su propia ``source``.
2. **Es idempotente.** Correr el backfill dos veces no duplica ni cambia nada:
   la segunda corrida reporta 0 agregados y 0 quitados.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from domain.tags import (
    NS_BPM,
    NS_ENERGY,
    NS_KEY,
    NS_PLAYLIST,
    NS_SOURCE,
    Tag,
    TagSource,
    normalize_value,
)

logger = logging.getLogger(__name__)

# Un código Camelot es 1..12 seguido de A o B. Cualquier otra cosa en
# track_analysis.musical_key es un dato viejo o corrupto y no genera tag.
_CAMELOT = re.compile(r"^(1[0-2]|[1-9])([AB])$", re.IGNORECASE)

# Buckets de tempo por década. Deliberadamente gruesos: el tag sirve para
# navegar y facetar, y la precisión la da el nodo `range` sobre la columna bpm.
_BPM_FLOOR = 100
_BPM_CEIL = 170

# Bandas de energía sobre la escala 1..10 que produce el AnalysisService.
_ENERGY_BANDS: tuple[tuple[int, int, str], ...] = (
    (1, 3, "low"),
    (4, 6, "mid"),
    (7, 8, "high"),
    (9, 10, "peak"),
)


def bpm_bucket(bpm: Optional[float]) -> Optional[str]:
    """Valor del tag ``bpm:`` para un tempo. ``None`` si no hay dato o es absurdo.

    >>> bpm_bucket(126.4)
    '120-129'
    >>> bpm_bucket(92.0)
    'under-100'
    >>> bpm_bucket(174.0)
    '170-plus'
    """
    if bpm is None:
        return None
    try:
        value = float(bpm)
    except (TypeError, ValueError):
        return None
    # Fuera de este rango no es tempo de un track: es un análisis fallado.
    if not (20.0 <= value <= 300.0):
        return None
    if value < _BPM_FLOOR:
        return "under-100"
    if value >= _BPM_CEIL:
        return "170-plus"
    decade = int(value // 10) * 10
    return f"{decade}-{decade + 9}"


def key_value(musical_key: Optional[str]) -> Optional[str]:
    """Valor del tag ``key:`` para una clave Camelot. ``None`` si no es válida.

    >>> key_value('8A')
    '8a'
    >>> key_value('Am')
    """
    if not musical_key:
        return None
    match = _CAMELOT.match(str(musical_key).strip())
    if match is None:
        return None
    return f"{match.group(1)}{match.group(2).lower()}"


def energy_band(energy: Optional[float]) -> Optional[str]:
    """Valor del tag ``energy:`` para una energía 1..10. ``None`` si no hay dato.

    >>> energy_band(7.0)
    'high'
    >>> energy_band(10)
    'peak'
    """
    if energy is None:
        return None
    try:
        # energy_level es REAL en la DB y int en el dominio; se redondea una
        # sola vez, acá, en vez de dejar la conversión implícita en cada lado.
        value = int(round(float(energy)))
    except (TypeError, ValueError):
        return None
    for low, high, name in _ENERGY_BANDS:
        if low <= value <= high:
            return name
    return None


def derived_tags(
    bpm: Optional[float] = None,
    musical_key: Optional[str] = None,
    energy: Optional[float] = None,
) -> tuple[Tag, ...]:
    """Los tags ``derived`` que corresponden a un análisis.

    Cada dimensión es independiente: un track con BPM pero sin clave válida
    recibe su tag de BPM igual. Un track sin nada analizado recibe la tupla
    vacía, que es exactamente lo que hace que el recálculo le borre los tags
    derivados viejos si se lo des-analiza.
    """
    tags: list[Tag] = []
    bucket = bpm_bucket(bpm)
    if bucket:
        tags.append(Tag(NS_BPM, bucket))
    key = key_value(musical_key)
    if key:
        tags.append(Tag(NS_KEY, key))
    band = energy_band(energy)
    if band:
        tags.append(Tag(NS_ENERGY, band))
    return tuple(tags)


def inherited_tags(
    source_platform: Optional[str] = None,
    source_playlist_name: Optional[str] = None,
) -> tuple[Tag, ...]:
    """Los tags ``inherited`` que corresponden al origen de un track."""
    tags: list[Tag] = []
    for namespace, raw in ((NS_SOURCE, source_platform), (NS_PLAYLIST, source_playlist_name)):
        if not raw or not str(raw).strip():
            continue
        try:
            tags.append(Tag(namespace, normalize_value(str(raw))))
        except ValueError:
            # Un nombre que se normaliza a vacío (p. ej. "---") no es un tag.
            logger.debug("Origen %r ignorado: no produce un valor de tag válido", raw)
    return tuple(tags)


@dataclass
class BackfillReport:
    """Qué pasó en una corrida de recálculo masivo."""
    tracks_seen: int = 0
    tracks_changed: int = 0
    tags_added: int = 0
    tags_removed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def unchanged(self) -> int:
        return self.tracks_seen - self.tracks_changed - self.skipped

    def __str__(self) -> str:
        return (
            f"{self.tracks_seen} tracks vistos, {self.tracks_changed} cambiados "
            f"(+{self.tags_added} / -{self.tags_removed}), "
            f"{self.unchanged} sin cambios, {self.skipped} salteados, "
            f"{len(self.errors)} errores"
        )


ProgressCallback = Callable[[int, int], None]


class TaggingService:
    """Aplica los tags automáticos sobre la librería.

    No conoce Qt ni SQL: recibe un repositorio de tags inyectado y le pide las
    lecturas y las escrituras.
    """

    def __init__(self, tag_repository):
        self.repo = tag_repository

    # --- por track --------------------------------------------------------

    def sync_derived(
        self,
        track_id: str,
        bpm: Optional[float],
        musical_key: Optional[str],
        energy: Optional[float],
        conn=None,
    ) -> tuple[int, int]:
        """Deja los tags ``derived`` de un track al día. Devuelve (agregados, quitados)."""
        return self.repo.set_tags_for_source(
            track_id, TagSource.DERIVED, derived_tags(bpm, musical_key, energy), conn=conn
        )

    def sync_inherited(
        self,
        track_id: str,
        source_platform: Optional[str],
        source_playlist_name: Optional[str],
        conn=None,
    ) -> tuple[int, int]:
        """Deja los tags ``inherited`` de un track al día."""
        return self.repo.set_tags_for_source(
            track_id,
            TagSource.INHERITED,
            inherited_tags(source_platform, source_playlist_name),
            conn=conn,
        )

    # --- masivo -----------------------------------------------------------

    def backfill_derived(self, on_progress: Optional[ProgressCallback] = None) -> BackfillReport:
        """Recalcula los tags ``derived`` de todos los tracks analizados.

        Corre todo dentro de una única transacción: o quedan todos los tracks
        con sus tags al día, o no cambia ninguno.
        """
        rows = list(self.repo.iter_analyzed_tracks())
        return self._backfill(
            rows,
            lambda row, conn: self.sync_derived(row[0], row[1], row[2], row[3], conn=conn),
            on_progress,
        )

    def backfill_inherited(self, on_progress: Optional[ProgressCallback] = None) -> BackfillReport:
        """Recalcula los tags ``inherited`` de todos los tracks de la librería."""
        rows = list(self.repo.iter_track_sources())
        return self._backfill(
            rows,
            lambda row, conn: self.sync_inherited(row[0], row[1], row[2], conn=conn),
            on_progress,
        )

    def _backfill(
        self,
        rows: Sequence[tuple],
        sync_one: Callable,
        on_progress: Optional[ProgressCallback],
    ) -> BackfillReport:
        report = BackfillReport(tracks_seen=len(rows))
        total = len(rows)

        conn = self.repo.db.get_connection()
        try:
            for index, row in enumerate(rows, start=1):
                try:
                    added, removed = sync_one(row, conn)
                except Exception as exc:  # una fila corrupta no aborta la corrida
                    report.skipped += 1
                    report.errors.append(f"{row[0]}: {exc}")
                    logger.warning("No se pudieron sincronizar los tags de %s: %s", row[0], exc)
                    continue
                if added or removed:
                    report.tracks_changed += 1
                    report.tags_added += added
                    report.tags_removed += removed
                if on_progress is not None:
                    on_progress(index, total)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        logger.info("Backfill de tags: %s", report)
        return report
