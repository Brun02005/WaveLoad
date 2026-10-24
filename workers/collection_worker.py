"""
workers/collection_worker.py
============================
Corre la evaluación de una collection fuera del hilo de dibujo.

Hace falta por una razón medida, no por precaución: el conteo por capa es la
operación más cara del motor —un `COUNT` no puede cortar temprano, y sobre
50.000 tracks está en el orden de las décimas de segundo (ver 4.5 de
`ARQUITECTURA.md`)—. Hacerlo en el hilo de la UI congela la ventana cada vez que
el usuario prende o apaga una capa, que es justamente la interacción que el
builder tiene que hacer sentir instantánea.

Como todos los workers del proyecto, no contiene lógica: envuelve a
``CollectionService`` y reemite lo que devuelve.
"""

import logging
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal

logger = logging.getLogger(__name__)


class CollectionEvaluationSignals(QObject):
    # Todas las señales llevan el ``token`` del pedido. Filtrar por id de
    # collection no alcanza: apagar dos capas seguidas sobre la misma collection
    # lanza dos workers, y el más lento llegaba último y pisaba al nuevo.
    # token, CollectionPage
    page_ready = Signal(int, object)
    # token, list[LayerCount]
    counts_ready = Signal(int, object)
    # token, mensaje de error entendible
    failed = Signal(int, str)
    # Se emite siempre al final, haya salido bien o mal. Quien lanzó el worker
    # lo usa para soltar la referencia que lo mantenía vivo.
    finished = Signal()


class CollectionEvaluationWorker(QRunnable):
    """Pide la página de resultados y el conteo por capa de una collection.

    Emite ``page_ready`` apenas tiene la página y ``counts_ready`` después: la
    grilla se llena primero y los conteos aparecen cuando están, en vez de que
    todo espere a lo más lento.
    """

    def __init__(self, service, collection, offset: int = 0, page_size: int = 200,
                 with_counts: bool = True, token: int = 0):
        super().__init__()
        self.token = token
        self.service = service
        self.collection = collection
        self.offset = offset
        self.page_size = page_size
        self.with_counts = with_counts
        self.signals = CollectionEvaluationSignals()

    def run(self):
        token = self.token
        try:
            page = self.service.page(
                self.collection, offset=self.offset, page_size=self.page_size
            )
            self.signals.page_ready.emit(token, page)
        except Exception as exc:
            logger.error("Falló la evaluación de %r: %s", self.collection.name, exc)
            logger.debug(traceback.format_exc())
            self.signals.failed.emit(token, str(exc))
            self.signals.finished.emit()
            return

        if self.with_counts:
            try:
                counts = self.service.layer_counts(self.collection)
                self.signals.counts_ready.emit(token, counts)
            except Exception as exc:
                # Que falle el conteo no invalida la página que ya se mostró.
                logger.error(
                    "Falló el conteo por capa de %r: %s", self.collection.name, exc
                )
                logger.debug(traceback.format_exc())

        self.signals.finished.emit()
