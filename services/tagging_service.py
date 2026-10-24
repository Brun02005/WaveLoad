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
from typing import Callable, Iterable, Optional, Sequence

from domain.tags import (
    MANUAL_NAMESPACES,
    NS_BPM,
    NS_ENERGY,
    NS_GENRE,
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


# --- Género leído del archivo ------------------------------------------------
# El campo Genre (TCON en ID3) lo completa quien vende o edita el archivo, y
# cada uno lo escribe distinto: "Techno (Peak Time / Driving)" en Beatport,
# "Electronica/Dance", "Drum n Bass", "(17)" en ID3v1. Esto lo lleva al mismo
# vocabulario de slugs que usa el resto del motor.

# Variantes frecuentes -> el slug canónico.
_GENRE_SYNONYMS = {
    "drum-and-bass": "drum-bass",
    "drum-n-bass": "drum-bass",
    "drum-bass": "drum-bass",
    "dnb": "drum-bass",
    "d-b": "drum-bass",
    "hiphop": "hip-hop",
    "hip-hop-rap": "hip-hop",
    "rap-hip-hop": "hip-hop",
    "techhouse": "tech-house",
    "afrohouse": "afro-house",
    "deephouse": "deep-house",
    "electronica": "electronic",
    "electronic-dance": "electronic",
    "dance-electronic": "electronic",
    "r-b": "r-b",
    "rnb": "r-b",
    "reggaetón": "reggaeton",
    "regueton": "reggaeton",
}

# Lo que no dice nada sobre el tema.
_GENRE_JUNK = {"other", "unknown", "misc", "none", "genre", "various", "default", "music"}

# Más de tres géneros en un archivo casi siempre es ruido de la tienda.
MAX_FILE_GENRES = 3


def genres_from_file_values(values: Iterable[str]) -> list[str]:
    """Los valores crudos del campo Genre -> slugs de ``genre``, sin repetir.

    - Lo que va entre paréntesis es el subgénero de Beatport ("Peak Time /
      Driving") o un código ID3v1 ("(17)"): se descarta, se queda el género.
    - ``;``, ``/``, ``,`` y ``|`` separan géneros.
    """
    resultado: list[str] = []
    for raw in values or ():
        sin_parentesis = re.sub(r"\([^)]*\)", " ", str(raw))
        for parte in re.split(r"[;/,|]", sin_parentesis):
            parte = parte.strip()
            if not parte:
                continue
            try:
                slug = normalize_value(parte)
            except ValueError:
                continue
            slug = _GENRE_SYNONYMS.get(slug, slug)
            if slug in _GENRE_JUNK or slug.isdigit() or slug in resultado:
                continue
            resultado.append(slug)
    return resultado[:MAX_FILE_GENRES]


def read_file_genres(path) -> list[str]:
    """El género que trae un archivo de audio (MP3, FLAC, M4A…), normalizado.

    Lee con mutagen en modo "easy", que unifica los nombres de campo entre
    formatos. Un archivo ilegible devuelve lista vacía: no tener género no es
    un error.
    """
    try:
        import mutagen  # noqa: PLC0415
        audio = mutagen.File(str(path), easy=True)
    except Exception as exc:  # noqa: BLE001 — archivo dañado, formato raro, permisos
        logger.debug("No se pudo leer el género de %s: %s", path, exc)
        return []
    if audio is None or not audio.tags:
        return []
    return genres_from_file_values(audio.tags.get("genre") or [])


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

    # --- etiquetado manual ---------------------------------------------------

    def manual_tags(self, track_ids) -> dict:
        """Los tags de los ejes que edita el usuario (género, mood, momento,
        estado), por track, en una consulta."""
        return self.repo.tags_for_tracks(track_ids, namespaces=sorted(MANUAL_NAMESPACES))

    def edit_manual(self, track_ids, add=(), remove=()) -> tuple[int, int]:
        """Agrega y quita tags manuales en varios tracks a la vez.

        Sólo acepta namespaces manuales: bpm, clave y energía se recalculan del
        análisis, y editarlos a mano sería pisarse con el próximo recálculo.
        """
        add, remove = list(add), list(remove)
        for tag in (*add, *remove):
            if tag.namespace not in MANUAL_NAMESPACES:
                raise ValueError(f"'{tag.namespace}' no se edita a mano: se calcula solo")
        return self.repo.edit_tags(list(track_ids), add=add, remove=remove,
                                   source=TagSource.MANUAL)

    def apply_file_genres(self, track_id: str, path) -> int:
        """Si el track todavía no tiene género, toma el que trae el archivo.

        Se guarda como ``manual``, igual que los tags que se leen del archivo al
        importar (ARQUITECTURA §4.7): desde ese momento son del usuario, que los
        corrige o borra, y nada automático los vuelve a escribir. Por eso sólo se
        aplica si no hay género manual: nunca pisa lo que el usuario eligió.
        """
        actuales = self.repo.tags_for_tracks([track_id], namespaces=[NS_GENRE])
        if actuales.get(str(track_id)):
            return 0
        generos = read_file_genres(path)
        if not generos:
            return 0
        agregados, _ = self.repo.edit_tags(
            [str(track_id)], add=[Tag(NS_GENRE, g) for g in generos], source=TagSource.MANUAL
        )
        return agregados

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
