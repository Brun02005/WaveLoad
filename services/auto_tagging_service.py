"""Etiquetado automático enganchado al pipeline.

Escucha el event bus y mantiene al día los tags que no pone el usuario:

- ``TrackCreatedEvent``  → tags ``inherited`` (plataforma y playlist de origen)
- ``TrackAnalyzedEvent`` → tags ``derived`` (bucket de BPM, clave, banda de energía)

Es lo que hace que un track nuevo **nazca etiquetado**, en vez de depender de
que alguien acuerde correr el backfill. Sin esto, la librería se degrada sola:
cada descarga y cada import agrega un track que no aparece en ninguna
collection basada en tags derivados.

Módulo puro, sin Qt. La descarga corre en un worker y el análisis en otro, pero
el bus es sincrónico y cada llamada a la DB abre su propia conexión, así que
cada hilo trabaja con la suya.

**Un fallo acá nunca rompe el pipeline.** Que no se haya podido escribir un tag
no puede impedir que un track entre a la librería: se loguea y se sigue. El
backfill (`tools/backfill_tags.py`) es la red de seguridad — es idempotente, así
que correrlo repara cualquier track que se haya perdido su etiqueta.
"""

import logging
from typing import Optional

from core.event_bus import TrackAnalyzedEvent, TrackCreatedEvent, event_bus

logger = logging.getLogger(__name__)


class AutoTaggingService:
    """Mantiene los tags automáticos al día a medida que la librería crece."""

    def __init__(self, tagging_service, bus=None):
        self.tagging = tagging_service
        # El bus es inyectable para poder testear sin tocar el global.
        self.bus = bus if bus is not None else event_bus
        self._subscribe()

    def _subscribe(self):
        self.bus.subscribe(TrackCreatedEvent, self.handle_track_created)
        self.bus.subscribe(TrackAnalyzedEvent, self.handle_track_analyzed)

    # --- handlers ---------------------------------------------------------

    def handle_track_created(self, event: TrackCreatedEvent) -> None:
        """Un track nuevo hereda los tags de su origen."""
        track = getattr(event, "track", None)
        if track is None:
            logger.warning("TrackCreatedEvent sin track; no hay nada que etiquetar")
            return

        track_id = str(getattr(track, "id", "") or "")
        if not track_id:
            logger.warning("TrackCreatedEvent con un track sin id; se saltea el etiquetado")
            return

        try:
            agregados, quitados = self.tagging.sync_inherited(
                track_id,
                getattr(track, "source_platform", None),
                getattr(track, "source_playlist_name", None),
            )
        except Exception as exc:
            # Un tag que no se pudo escribir no puede impedir que el track
            # entre a la librería. El backfill lo repara después.
            logger.error("No se pudieron heredar los tags de %s: %s", track_id, exc)
            return

        if agregados or quitados:
            logger.info(
                "Tags heredados de %s: +%d / -%d", track_id, agregados, quitados
            )

    def handle_track_analyzed(self, event: TrackAnalyzedEvent) -> None:
        """Un track recién analizado recalcula sus tags derivados.

        El recálculo borra sólo las asignaciones ``derived``: si el usuario había
        puesto tags a mano sobre ese track, no se tocan.
        """
        track_id = str(getattr(event, "track_id", "") or "")
        if not track_id:
            logger.warning("TrackAnalyzedEvent sin track_id; se saltea el etiquetado")
            return

        try:
            agregados, quitados = self.tagging.sync_derived(
                track_id, event.bpm, event.key_camelot, event.energy
            )
        except Exception as exc:
            logger.error("No se pudieron derivar los tags de %s: %s", track_id, exc)
            return

        if agregados or quitados:
            logger.info(
                "Tags derivados de %s: +%d / -%d", track_id, agregados, quitados
            )
