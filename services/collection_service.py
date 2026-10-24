"""Fachada de Collections para la UI.

Compone las tres piezas del motor —el repositorio de collections, el evaluador y
el repositorio de tracks— y expone lo que un workspace necesita, ya resuelto:
listar, abrir, editar la pila, guardar, y pedir una página de resultados con sus
tracks completos.

Existe para que el `CollectionsWorkspace` sea delgado. Sin esta capa, el widget
terminaría orquestando tres objetos y traduciendo ids a tracks a mano, que es
justamente la lógica que no tiene que vivir en la UI.

Sin Qt: se testea headless.
"""

import logging
from dataclasses import dataclass, replace
from typing import Optional, Sequence

from domain.collections import (
    Crate,
    LayerMode,
    QueryLayer,
    SmartCollection,
    SortSpec,
)
from domain.query_ast import Node
from services.collection_evaluator import CollectionEvaluator, LayerCount

logger = logging.getLogger(__name__)

# Cuántos tracks trae una página. El motor puede devolver el resultado entero,
# pero una grilla no necesita más que esto de una: ver 4.5 de ARQUITECTURA.md.
DEFAULT_PAGE_SIZE = 200


@dataclass(frozen=True)
class CollectionPage:
    """Una página de resultados, con los tracks ya resueltos."""
    collection: SmartCollection
    tracks: tuple
    offset: int
    page_size: int
    total: int
    elapsed_ms: float

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.tracks) < self.total

    @property
    def page_number(self) -> int:
        """1-indexado, para mostrar."""
        return self.offset // self.page_size + 1 if self.page_size else 1

    def __len__(self) -> int:
        return len(self.tracks)


class CollectionService:
    """Todo lo que la UI de Collections necesita, sin que toque el motor directo."""

    def __init__(self, collection_repository, track_repository, evaluator=None,
                 tag_repository=None):
        self.repo = collection_repository
        self.tracks = track_repository
        self.evaluator = evaluator or CollectionEvaluator(collection_repository.db)
        # Opcional: sólo hace falta para llenar los desplegables del builder.
        self.tags = tag_repository

    # --- vocabulario para el builder --------------------------------------

    def namespace_values(self, namespace: str) -> list[tuple[str, int]]:
        """``(valor, cuántos tracks lo tienen)`` de un namespace, de mayor a menor.

        El builder ofrece los valores que la librería tiene de verdad, ordenados
        por uso: tipear a ciegas es cómo se termina con `techno` y `Techno` como
        dos tags. Sin repositorio de tags inyectado devuelve vacío.
        """
        if self.tags is None:
            return []
        return self.tags.usage_by_namespace(namespace)

    def used_namespaces(self) -> list[str]:
        """Los namespaces que tienen al menos un valor en esta librería."""
        if self.tags is None:
            return []
        return sorted(self.tags.count_by_namespace())

    # --- listado y ciclo de vida -----------------------------------------

    def list_names(self) -> list[tuple[int, str]]:
        """``(id, nombre)`` para poblar el sidebar sin parsear ningún AST."""
        return self.repo.list_names()

    def get(self, collection_id: int) -> SmartCollection:
        return self.repo.get(collection_id)

    def create(self, name: str) -> SmartCollection:
        """Crea una collection vacía. Vacía significa 'toda la librería'."""
        return self.repo.save(SmartCollection(name=name))

    def create_unique(self, base_name: str = "Nueva colección") -> SmartCollection:
        """Crea una collection con un nombre libre, agregando un número si hace falta.

        Es lo que quiere el botón "nueva": no tiene sentido hacerle elegir un
        nombre al usuario antes de dejarlo ver qué está armando.
        """
        nombre = base_name
        indice = 2
        while self.repo.exists(nombre):
            nombre = f"{base_name} {indice}"
            indice += 1
        return self.create(nombre)

    def rename(self, collection: SmartCollection, name: str) -> SmartCollection:
        return self.repo.save(replace(collection, name=name))

    def delete(self, collection_id: int) -> bool:
        return self.repo.delete(collection_id)

    def duplicate(self, collection: SmartCollection) -> SmartCollection:
        """Copia una collection con otro nombre. Útil para probar una variante."""
        copia = replace(
            collection,
            id=None,
            name=self._free_name(f"{collection.name} (copia)"),
            layers=tuple(replace(layer, id=None) for layer in collection.ordered_layers()),
        )
        return self.repo.save(copia)

    def _free_name(self, base: str) -> str:
        nombre = base
        indice = 2
        while self.repo.exists(nombre):
            nombre = f"{base} {indice}"
            indice += 1
        return nombre

    # --- edición de la pila ----------------------------------------------
    # Todas devuelven la collection ya guardada y releída: la UI dibuja lo que
    # quedó en la base, no lo que cree que mandó.

    def add_layer(
        self,
        collection: SmartCollection,
        predicate: Node,
        mode: LayerMode = LayerMode.FILTER,
    ) -> SmartCollection:
        return self.repo.save(
            collection.with_layer(QueryLayer(predicate=predicate, mode=mode))
        )

    def replace_layer(
        self,
        collection: SmartCollection,
        position: int,
        predicate: Node,
        mode: LayerMode,
    ) -> SmartCollection:
        """Cambia predicado y modo de una capa sin moverla ni tocar ``enabled``.

        Editar una capa apagada no puede prenderla: el usuario la editó, no la
        activó.
        """
        capas = tuple(
            replace(capa, predicate=predicate, mode=mode)
            if capa.position == position else capa
            for capa in collection.ordered_layers()
        )
        if not any(capa.position == position for capa in collection.layers):
            raise ValueError(f"No hay una capa en la posición {position}")
        return self.repo.save(replace(collection, layers=capas))

    def remove_layer(self, collection: SmartCollection, position: int) -> SmartCollection:
        return self.repo.save(collection.without_layer(position))

    def toggle_layer(
        self, collection: SmartCollection, position: int, enabled: bool
    ) -> SmartCollection:
        return self.repo.save(collection.with_layer_toggled(position, enabled))

    def move_layer(
        self, collection: SmartCollection, desde: int, hasta: int
    ) -> SmartCollection:
        return self.repo.save(collection.with_layer_moved(desde, hasta))

    def set_sort(
        self, collection: SmartCollection, sort: Optional[SortSpec]
    ) -> SmartCollection:
        return self.repo.save(replace(collection, sort=sort))

    def set_limit(
        self, collection: SmartCollection, limit: Optional[int]
    ) -> SmartCollection:
        return self.repo.save(replace(collection, limit=limit))

    # --- resultados -------------------------------------------------------

    def page(
        self,
        collection: SmartCollection,
        offset: int = 0,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> CollectionPage:
        """Una página de resultados con los tracks completos, en orden."""
        total = self.evaluator.count(collection)
        tamano = page_size
        if collection.limit is not None:
            # El límite guardado acota el resultado; la paginación no puede
            # mostrar más allá de eso. Pedir la página con limit=page_size
            # pisaba el límite: con límite 10 devolvía 200 tracks.
            total = min(total, collection.limit)
            tamano = max(0, min(page_size, collection.limit - offset))
        if tamano == 0:
            return CollectionPage(
                collection=collection, tracks=(), offset=offset,
                page_size=page_size, total=total, elapsed_ms=0.0,
            )
        resultado = self.evaluator.evaluate(collection, limit=tamano, offset=offset)
        tracks = self.tracks.get_by_ids(list(resultado.track_ids))
        return CollectionPage(
            collection=collection,
            tracks=tuple(tracks),
            offset=offset,
            page_size=page_size,
            total=total,
            elapsed_ms=resultado.elapsed_ms,
        )

    def count(self, collection: SmartCollection) -> int:
        return self.evaluator.count(collection)

    def layer_counts(self, collection: SmartCollection) -> list[LayerCount]:
        """El conteo paso a paso.

        **Es la operación más cara del motor** —del orden de las décimas de
        segundo sobre 50.000 tracks— porque un `COUNT` no puede cortar temprano.
        La UI tiene que pedirla fuera del hilo de dibujo.
        """
        return self.evaluator.layer_counts(collection)

    def warnings(self, collection: SmartCollection) -> list[str]:
        """Avisos sobre la pila que la UI debería mostrar.

        No son errores: la collection es válida y se evalúa igual. Son cosas que
        el usuario probablemente no quiso.
        """
        avisos: list[str] = []
        activas = collection.active_layers()

        if activas and activas[0].mode is LayerMode.UNION:
            avisos.append(
                "La primera capa suma sobre la librería completa, así que no cambia "
                "nada: la base ya incluye todo. Movela más abajo o cambiala a filtrar."
            )
        if collection.layers and not activas:
            avisos.append(
                "Todas las capas están apagadas: el resultado es la librería completa."
            )
        if collection.limit is not None and collection.sort is None:
            avisos.append(
                f"Hay un límite de {collection.limit} pero no un orden, así que "
                "cuáles entran queda librado a SQLite. Elegí un orden."
            )
        return avisos

    # --- congelar a crate -------------------------------------------------

    def freeze_to_crate(
        self, collection: SmartCollection, name: Optional[str] = None
    ) -> Crate:
        """Materializa el resultado actual de una collection en un crate fijo.

        Es el puente entre las dos entidades: una smart collection no admite
        tracks fijados a mano, así que cuando hace falta control manual sobre el
        resultado, se congela. El crate resultante **no guarda referencia** a la
        collection de origen: a partir de acá son cosas independientes, y la
        collection puede cambiar sin que el crate se entere.
        """
        resultado = self.evaluator.evaluate(collection)
        crate = Crate(
            name=self._free_crate_name(name or f"{collection.name} (congelada)"),
            track_ids=resultado.track_ids,
        )
        guardado = self.repo.save_crate(crate)
        logger.info(
            "Collection %r congelada en el crate %r (%d tracks)",
            collection.name, guardado.name, len(guardado),
        )
        return guardado

    def _free_crate_name(self, base: str) -> str:
        existentes = {crate.name for crate in self.repo.list_crates()}
        nombre = base
        indice = 2
        while nombre in existentes:
            nombre = f"{base} {indice}"
            indice += 1
        return nombre

    # --- crates -----------------------------------------------------------

    def get_crate(self, crate_id: int) -> Crate:
        return self.repo.get_crate(crate_id)

    def list_crates(self) -> list[Crate]:
        return self.repo.list_crates()

    def create_crate(self, name: Optional[str] = None, track_ids=()) -> Crate:
        """Un crate nuevo, con un nombre libre si el pedido ya existe."""
        base = (name or "").strip() or "Nuevo crate"
        unicos = list(dict.fromkeys(str(t) for t in track_ids))
        return self.repo.save_crate(Crate(name=self._free_crate_name(base), track_ids=tuple(unicos)))

    def rename_crate(self, crate_id: int, name: str) -> Crate:
        crate = self.repo.get_crate(crate_id)
        nombre = name.strip()
        if nombre == crate.name:
            return crate
        if any(c.name == nombre for c in self.repo.list_crates()):
            raise ValueError(f"Ya hay un crate llamado «{nombre}»")
        return self.repo.save_crate(replace(crate, name=nombre))

    def duplicate_crate(self, crate_id: int) -> Crate:
        crate = self.repo.get_crate(crate_id)
        return self.repo.save_crate(
            Crate(name=self._free_crate_name(f"{crate.name} (copia)"), track_ids=crate.track_ids)
        )

    def delete_crate(self, crate_id: int) -> bool:
        """Borra el crate. Las pistas no se tocan: siguen en la librería."""
        return self.repo.delete_crate(crate_id)

    def add_to_crate(self, crate_id: int, track_ids) -> tuple[Crate, int]:
        """Agrega pistas al final del crate, en el orden dado. Las que ya
        estaban no se repiten ni cambian de lugar. Devuelve (crate, agregadas)."""
        crate = self.repo.get_crate(crate_id)
        agregadas = 0
        for track_id in track_ids:
            if str(track_id) not in crate.track_ids:
                crate = crate.with_track(str(track_id))
                agregadas += 1
        if agregadas:
            crate = self.repo.save_crate(crate)
        return crate, agregadas

    def remove_from_crate(self, crate_id: int, track_ids) -> tuple[Crate, int]:
        """Saca pistas del crate (no de la librería). Devuelve (crate, quitadas)."""
        crate = self.repo.get_crate(crate_id)
        quitadas = 0
        for track_id in track_ids:
            if str(track_id) in crate.track_ids:
                crate = crate.without_track(str(track_id))
                quitadas += 1
        if quitadas:
            crate = self.repo.save_crate(crate)
        return crate, quitadas

    def crate_tracks(self, crate: Crate) -> tuple:
        """Los tracks de un crate, en el orden en que el usuario los puso."""
        return tuple(self.tracks.get_by_ids(list(crate.track_ids)))
