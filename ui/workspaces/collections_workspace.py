"""
ui/workspaces/collections_workspace.py
======================================
El workspace de Colecciones: la pila de capas y su resultado.

Es la única parte del motor de Collections que el usuario ve. Todo lo que
decide vive en ``CollectionService`` y está probado headless; acá hay dibujo,
señales y nada de lógica de negocio.

Dos cosas que el diseño de esta pantalla tiene incorporadas por medición, no por
prolijidad:

1. **La evaluación se pide a un worker.** El conteo por capa es la operación más
   cara del motor y hacerlo en el hilo de dibujo congelaría la ventana en la
   interacción que más tiene que fluir: prender y apagar capas.
2. **La grilla se llena por página.** Traer el resultado entero cuesta lo mismo
   que contarlo; una página no.

Una capa cuyo predicado no entra en el formulario plano del editor se muestra de
sólo lectura, con su descripción. No se recorta ni se rompe.
"""

import logging
from typing import Optional

from PySide6.QtCore import QCoreApplication, Qt, QThreadPool, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from domain.collections import LayerMode, SortDirection, SortSpec
from services.layer_form import LayerForm
from ui.components.buttons import (
    WLGhostButton,
    WLIconButton,
    WLSecondaryButton,
)
from ui.components.tables import WLTrackTable
from ui.dialogs.layer_editor_dialog import LayerEditorDialog, select_by_data
from ui.mappers.track_mapper import TrackPresentationMapper
from ui.components.empty_state import WLEmptyState
from ui.theme.colors import (
    ACCENT,
    ACCENT_SOFT,
    BORDER_SUBTLE,
    DANGER_SOFT,
    PRIMARY_ORANGE,
    PRIMARY_RED,
    STATUS_VALID,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from ui.theme.icons import Icons, icon
from ui.theme.typography import tabular
from ui.theme.spacing import SPACE_LG, SPACE_MD, SPACE_SM
from ui.workspaces.base_workspace import BaseWorkspace
from workers.collection_worker import CollectionEvaluationWorker

logger = logging.getLogger(__name__)

PAGE_SIZE = 200

# Alto de una fila de capa, para dimensionar la pila.
LAYER_ROW_HEIGHT = 44

MODE_LABELS = {
    LayerMode.FILTER: "filtrar",
    LayerMode.EXCLUDE: "excluir",
    LayerMode.UNION: "sumar",
}

# Texto, color y fondo de la etiqueta de modo. Cada modo tiene su color para
# que la pila se lea de un vistazo: qué recorta, qué saca, qué agrega.
MODE_STYLE = {
    LayerMode.FILTER: ("filtrar", ACCENT, ACCENT_SOFT),
    LayerMode.EXCLUDE: ("excluir", PRIMARY_RED, DANGER_SOFT),
    LayerMode.UNION: ("sumar", STATUS_VALID, "rgba(63, 185, 122, 0.12)"),
}

SORT_OPTIONS = [
    (None, "Sin orden"),
    (("bpm", SortDirection.ASC), "BPM ascendente"),
    (("bpm", SortDirection.DESC), "BPM descendente"),
    (("energy", SortDirection.ASC), "Energía ascendente"),
    (("energy", SortDirection.DESC), "Energía descendente"),
    (("title", SortDirection.ASC), "Título A-Z"),
    (("artist", SortDirection.ASC), "Artista A-Z"),
    (("created_at", SortDirection.DESC), "Más recientes primero"),
]


class LayerRow(QFrame):
    """Una capa dibujada: modo, descripción, conteo y sus acciones."""

    toggled = Signal(int, bool)
    edit_requested = Signal(int)
    remove_requested = Signal(int)
    move_requested = Signal(int, int)

    def __init__(self, layer, indice: int, total: int, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.setObjectName("wl_layerRow")
        self.setFixedHeight(LAYER_ROW_HEIGHT)
        fondo = SURFACE_3 if layer.enabled else SURFACE_2
        self.setStyleSheet(
            f"#wl_layerRow {{ background-color: {fondo}; border: 1px solid {BORDER_SUBTLE};"
            " border-radius: 8px; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        self.btn_enabled = WLIconButton(
            Icons.EYE if layer.enabled else Icons.EYE_OFF, size=28, icon_px=16,
            color=TEXT_SECONDARY if layer.enabled else TEXT_MUTED,
        )
        self.btn_enabled.setToolTip(
            "Apagar esta capa (no se borra)" if layer.enabled else "Prender esta capa"
        )
        self.btn_enabled.clicked.connect(
            lambda: self.toggled.emit(layer.position, not layer.enabled)
        )
        layout.addWidget(self.btn_enabled)

        numero = QLabel(str(indice + 1))
        numero.setFixedWidth(16)
        numero.setAlignment(Qt.AlignCenter)
        numero.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(numero)

        texto_modo, color_modo, fondo_modo = MODE_STYLE[layer.mode]
        lbl_modo = QLabel(texto_modo)
        lbl_modo.setAlignment(Qt.AlignCenter)
        lbl_modo.setFixedSize(64, 22)
        lbl_modo.setStyleSheet(
            f"color: {color_modo}; background-color: {fondo_modo}; border-radius: 6px;"
            " font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(lbl_modo)
        layout.addSpacing(4)

        color = TEXT_PRIMARY if layer.enabled else TEXT_MUTED
        self.lbl_desc = QLabel(layer.predicate.describe())
        self.lbl_desc.setStyleSheet(f"color: {color};")
        layout.addWidget(self.lbl_desc, 1)

        self.lbl_count = QLabel("…")
        self.lbl_count.setFixedWidth(64)
        self.lbl_count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_count.setFont(tabular(self.lbl_count.font()))
        self.lbl_count.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.lbl_count.setToolTip("Pistas que quedan después de esta capa")
        layout.addWidget(self.lbl_count)
        layout.addSpacing(6)

        btn_up = WLIconButton(Icons.MOVE_UP, size=28, icon_px=15,
                              tooltip="Subir. El orden importa cuando hay capas que suman.")
        btn_up.setEnabled(indice > 0)
        btn_up.clicked.connect(lambda: self.move_requested.emit(layer.position, indice - 1))
        layout.addWidget(btn_up)

        btn_down = WLIconButton(Icons.MOVE_DOWN, size=28, icon_px=15, tooltip="Bajar")
        btn_down.setEnabled(indice < total - 1)
        btn_down.clicked.connect(lambda: self.move_requested.emit(layer.position, indice + 1))
        layout.addWidget(btn_down)

        self.btn_edit = WLIconButton(Icons.EDIT, size=28, icon_px=15)
        editable = LayerForm.is_editable(layer.predicate)
        self.btn_edit.setEnabled(editable)
        self.btn_edit.setToolTip(
            "Editar esta capa" if editable else
            "Esta capa usa una condición que el editor visual no dibuja. "
            "Se puede apagar, mover o borrar, pero no editar acá."
        )
        if not editable:
            self.lbl_desc.setStyleSheet(f"color: {color}; font-style: italic;")
        self.btn_edit.clicked.connect(lambda: self.edit_requested.emit(layer.position))
        layout.addWidget(self.btn_edit)

        self.btn_remove = WLIconButton(Icons.CLEAR, size=28, icon_px=15, tooltip="Borrar esta capa")
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(layer.position))
        layout.addWidget(self.btn_remove)

    def set_count(self, valor: int):
        self.lbl_count.setText(f"{valor:,}".replace(",", "."))


class CollectionsWorkspace(BaseWorkspace):
    """Lista de colecciones, pila de capas y resultado."""

    track_selected = Signal(dict)

    def __init__(self, service=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.pool = QThreadPool()
        self.current = None          # SmartCollection abierta
        self.current_crate = None    # Crate abierto (excluyente con current)
        self._offset = 0
        # Número del último pedido de página y de conteos. Lo que llega con un
        # número viejo es de una pila que ya no está en pantalla.
        self._token = 0
        self._page_token = 0
        self._counts_token = 0
        self._layer_rows: list[LayerRow] = []
        # Referencias a los workers en vuelo. Sin esto el recolector se lleva el
        # objeto Python mientras el hilo todavía corre, y el worker muere al
        # emitir con "Signal source has been deleted".
        self._workers: list = []
        self._build_ui()
        # Al cerrar la app, esperar a los workers en vuelo: si el workspace se
        # destruye mientras uno emite, Qt avisa "Signal source has been deleted".
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def reload(self):
        """La librería cambió (se quitaron pistas): volver a evaluar lo que se
        está mostrando. No hay caché que invalidar, la evaluación siempre es
        contra la base."""
        if self.service is not None:
            self.refresh_collections()

    def shutdown(self):
        self._token += 1  # lo que llegue de acá en más se descarta
        self.pool.clear()
        self.pool.waitForDone(3000)

    # =====================================================================
    # Construcción
    # =====================================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900])
        layout.addWidget(splitter)

        self._show_empty_detail()

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("wl_collectionsList")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setStyleSheet(f"#wl_collectionsList {{ background-color: {SURFACE_1}; }}")
        panel.setMinimumWidth(220)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(6)

        cabecera = QHBoxLayout()
        cabecera.setContentsMargins(8, 0, 0, 0)
        titulo = QLabel("COLECCIONES")
        titulo.setObjectName("wl_navSection")
        titulo.setStyleSheet("padding: 0px;")
        cabecera.addWidget(titulo)
        cabecera.addStretch()
        self.btn_new = WLIconButton(Icons.PLUS, size=26, icon_px=15, tooltip="Nueva colección")
        self.btn_new.clicked.connect(self._on_new)
        cabecera.addWidget(self.btn_new)
        layout.addLayout(cabecera)

        self.list_collections = QListWidget()
        self.list_collections.currentItemChanged.connect(self._on_collection_selected)
        self.list_collections.setContextMenuPolicy(Qt.CustomContextMenu)
        # Nombres largos ("Peak time (congelada) 2"): "…" en el medio y no una
        # barra de desplazamiento horizontal.
        self.list_collections.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_collections.setTextElideMode(Qt.ElideMiddle)
        self.list_collections.customContextMenuRequested.connect(self._on_collections_menu)
        self.list_collections.itemDoubleClicked.connect(
            lambda item: self._rename_collection(item.data(Qt.UserRole))
        )
        self.list_collections.setToolTip("Clic derecho para renombrar, duplicar o borrar · F2 renombra · Supr borra")
        layout.addWidget(self.list_collections, 1)

        layout.addSpacing(12)
        cabecera_crates = QHBoxLayout()
        cabecera_crates.setContentsMargins(8, 0, 0, 0)
        lbl_crates = QLabel("CRATES")
        lbl_crates.setObjectName("wl_navSection")
        lbl_crates.setStyleSheet("padding: 0px;")
        lbl_crates.setToolTip(
            "Listas fijas que armás a mano: clic derecho en cualquier pista → "
            "Agregar a crate, o congelá una colección"
        )
        cabecera_crates.addWidget(lbl_crates)
        cabecera_crates.addStretch()
        self.btn_new_crate = WLIconButton(Icons.PLUS, size=26, icon_px=15, tooltip="Nuevo crate")
        self.btn_new_crate.clicked.connect(self._new_crate)
        cabecera_crates.addWidget(self.btn_new_crate)
        layout.addLayout(cabecera_crates)
        self.list_crates = QListWidget()
        self.list_crates.setMaximumHeight(220)
        self.list_crates.currentItemChanged.connect(self._on_crate_selected)
        self.list_crates.setContextMenuPolicy(Qt.CustomContextMenu)
        # Nombres largos ("Peak time (congelada) 2"): "…" en el medio y no una
        # barra de desplazamiento horizontal.
        self.list_crates.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_crates.setTextElideMode(Qt.ElideMiddle)
        self.list_crates.customContextMenuRequested.connect(self._on_crates_menu)
        self.list_crates.itemDoubleClicked.connect(
            lambda item: self._rename_crate(item.data(Qt.UserRole))
        )
        self.list_crates.setToolTip("Clic derecho para renombrar, duplicar o borrar · F2 renombra · Supr borra")
        layout.addWidget(self.list_crates)

        # Teclado sobre cada lista: Supr borra, F2 renombra, Ctrl+D duplica.
        for lista, borrar, renombrar, duplicar in (
            (self.list_collections, self._delete_collection, self._rename_collection,
             self._duplicate_collection),
            (self.list_crates, self._delete_crate, self._rename_crate, self._duplicate_crate),
        ):
            for tecla, accion in ((QKeySequence.Delete, borrar), (QKeySequence(Qt.Key_F2), renombrar),
                                  (QKeySequence("Ctrl+D"), duplicar)):
                atajo = QShortcut(tecla, lista)
                atajo.setContext(Qt.WidgetShortcut)
                atajo.activated.connect(
                    lambda lista=lista, accion=accion: lista.currentItem()
                    and accion(lista.currentItem().data(Qt.UserRole))
                )

        return panel

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 16, 24, 12)
        layout.setSpacing(SPACE_MD)

        # Encabezado
        encabezado = QHBoxLayout()
        encabezado.setSpacing(4)
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("wl_title")
        titulos.addWidget(self.lbl_title)
        self.lbl_subtitle = QLabel("")
        self.lbl_subtitle.setObjectName("wl_subtitle")
        titulos.addWidget(self.lbl_subtitle)
        encabezado.addLayout(titulos)
        encabezado.addStretch()

        self.btn_rename = WLIconButton(Icons.EDIT, tooltip="Renombrar")
        self.btn_rename.clicked.connect(self._on_rename)
        encabezado.addWidget(self.btn_rename)
        self.btn_duplicate = WLIconButton(Icons.DUPLICATE, tooltip="Duplicar, para probar una variante")
        self.btn_duplicate.clicked.connect(self._on_duplicate)
        encabezado.addWidget(self.btn_duplicate)
        self.btn_delete = WLIconButton(Icons.CLEAR, tooltip="Borrar la colección")
        self.btn_delete.clicked.connect(self._on_delete)
        encabezado.addWidget(self.btn_delete)
        encabezado.addSpacing(8)

        self.combo_sort = QComboBox()
        for dato, etiqueta in SORT_OPTIONS:
            self.combo_sort.addItem(etiqueta, dato)
        self.combo_sort.currentIndexChanged.connect(self._on_sort_changed)
        encabezado.addWidget(self.combo_sort)

        self.combo_sort.setMinimumWidth(190)
        self.btn_freeze = WLSecondaryButton("Congelar a crate", icon=Icons.CRATE)
        self.btn_freeze.setToolTip(
            "Materializa el resultado actual en un crate fijo, que después no cambia "
            "aunque la colección cambie."
        )
        self.btn_freeze.clicked.connect(self._on_freeze)
        encabezado.addWidget(self.btn_freeze)
        layout.addLayout(encabezado)

        # Pila de capas
        self.lbl_base = QLabel("Librería completa")
        self.lbl_base.setObjectName("wl_caption")
        layout.addWidget(self.lbl_base)

        self.scroll_layers = QScrollArea()
        self.scroll_layers.setWidgetResizable(True)
        self.scroll_layers.setFrameShape(QFrame.NoFrame)
        # La pila crece con las capas hasta un tope; más allá scrollea. Sin
        # una altura mínima, la grilla se come todo el alto y la pila queda en
        # una franja de una fila, que es justo lo que hay que poder mirar.
        contenedor = QWidget()
        self.layers_layout = QVBoxLayout(contenedor)
        self.layers_layout.setContentsMargins(0, 0, 0, 0)
        self.layers_layout.setSpacing(6)
        self.layers_layout.addStretch()
        self.scroll_layers.setWidget(contenedor)
        layout.addWidget(self.scroll_layers)

        self.btn_add_layer = WLGhostButton("Agregar capa", icon=Icons.PLUS)
        self.btn_add_layer.clicked.connect(self._on_add_layer)
        layout.addWidget(self.btn_add_layer, 0, Qt.AlignLeft)

        self.lbl_warnings = QLabel("")
        self.lbl_warnings.setWordWrap(True)
        self.lbl_warnings.setStyleSheet(
            f"color: {PRIMARY_ORANGE}; background-color: rgba(232, 161, 58, 0.08);"
            " border-radius: 8px; padding: 8px 12px;"
        )
        self.lbl_warnings.setVisible(False)
        layout.addWidget(self.lbl_warnings)

        # Qué se ve cuando no hay ninguna colección abierta.
        self.lbl_empty = WLEmptyState(
            Icons.COLLECTIONS,
            "Sin colecciones todavía",
            "Una colección es una pila de filtros sobre tu librería: cada capa la "
            "recorta, saca o suma pistas, y al costado ves cuántas quedan después "
            "de cada paso. Las capas se apagan y reordenan sin perderlas.",
            action_text="Crear la primera",
            action_icon=Icons.PLUS,
        )
        self.lbl_empty.action_btn.clicked.connect(self._on_new)
        layout.addWidget(self.lbl_empty, 1)

        # Resultado
        self.table = WLTrackTable()
        layout.addWidget(self.table, 1)

        pie = QHBoxLayout()
        pie.setSpacing(SPACE_SM)
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("wl_caption")
        # Con stretch, y no con un addStretch() al lado: si no, los botones de
        # paginado le comen el ancho y el mensaje sale cortado a la mitad.
        pie.addWidget(self.lbl_status, 1)
        self.lbl_status.setFont(tabular(self.lbl_status.font()))
        self.btn_prev = WLIconButton(Icons.ARROW_LEFT, tooltip="Página anterior")
        self.btn_prev.clicked.connect(lambda: self._change_page(-1))
        pie.addWidget(self.btn_prev)
        self.btn_next = WLIconButton(Icons.ARROW_RIGHT, tooltip="Página siguiente")
        self.btn_next.clicked.connect(lambda: self._change_page(1))
        pie.addWidget(self.btn_next)
        layout.addLayout(pie)

        self.detail_panel = panel
        return panel

    # =====================================================================
    # Ciclo de vida
    # =====================================================================

    def activate(self):
        """Se llama cada vez que el workspace se hace visible."""
        self.refresh_collections()

    def refresh_collections(self):
        if self.service is None:
            return
        seleccionada = self.current.id if self.current else None
        try:
            nombres = self.service.list_names()
        except Exception as exc:
            self._show_error("No se pudieron listar las colecciones", exc)
            return
        self.list_collections.blockSignals(True)
        self.list_collections.clear()
        for collection_id, nombre in nombres:
            item = QListWidgetItem(nombre)
            item.setData(Qt.UserRole, collection_id)
            self.list_collections.addItem(item)
            if collection_id == seleccionada:
                self.list_collections.setCurrentItem(item)
        self.list_collections.blockSignals(False)
        self._refresh_crates()

        if self.current_crate is not None:
            self._open_crate(self.current_crate.id)
        elif self.list_collections.count() == 0:
            self.current = None
            self._show_empty_detail()
        elif self.list_collections.currentItem() is None:
            self.list_collections.setCurrentRow(0)
        else:
            # setCurrentItem() corrió con las señales bloqueadas, así que nadie
            # redibujó: después de «Nueva» o «Duplicar» el panel seguía
            # mostrando la colección anterior mientras se editaba la nueva.
            self._render_current()

    def _refresh_crates(self):
        self.list_crates.blockSignals(True)
        self.list_crates.clear()
        abierto = self.current_crate.id if self.current_crate else None
        try:
            for crate in self.service.list_crates():
                item = QListWidgetItem(f"{crate.name}  ({len(crate)})")
                item.setData(Qt.UserRole, crate.id)
                self.list_crates.addItem(item)
                if crate.id == abierto:
                    self.list_crates.setCurrentItem(item)
        except Exception as exc:
            logger.error("No se pudieron listar los crates: %s", exc)
        self.list_crates.blockSignals(False)

    def _show_empty_detail(self):
        self.lbl_title.setText("")
        self.lbl_subtitle.setText("")
        self.lbl_status.setText("")
        self._clear_layers()
        self.table.set_tracks([])
        self._set_detail_enabled(False)

    def _set_detail_enabled(self, enabled: bool):
        """Con nada abierto no se muestran controles muertos: se esconden.

        Un botón deshabilitado que igual se ve invita a clickearlo. Si no hay
        colección abierta, lo único que corresponde es explicar qué es una
        colección y cómo se crea.
        """
        for widget in (self.btn_add_layer, self.btn_freeze, self.combo_sort,
                       self.btn_duplicate, self.btn_rename, self.btn_delete):
            widget.setEnabled(enabled)
        for widget in (self.lbl_base, self.scroll_layers, self.btn_add_layer,
                       self.combo_sort, self.btn_freeze, self.table,
                       self.btn_prev, self.btn_next, self.btn_duplicate,
                       self.btn_rename, self.btn_delete):
            widget.setVisible(enabled)
        self.lbl_empty.setVisible(not enabled)

    # =====================================================================
    # Selección
    # =====================================================================

    def _on_collection_selected(self, current, _previous):
        if current is None or self.service is None:
            return
        collection_id = current.data(Qt.UserRole)
        try:
            self.current = self.service.get(collection_id)
        except Exception as exc:
            self._show_error("No se pudo abrir la colección", exc)
            return
        self.list_crates.blockSignals(True)
        self.list_crates.setCurrentItem(None)
        self.list_crates.blockSignals(False)
        self.current_crate = None
        self.btn_rename.setToolTip("Renombrar")
        self.btn_duplicate.setToolTip("Duplicar, para probar una variante")
        self.btn_delete.setToolTip("Borrar la colección")
        self._offset = 0
        self._render_current()

    def _on_crate_selected(self, current, _previous):
        if current is None or self.service is None:
            return
        self._open_crate(current.data(Qt.UserRole))

    def _open_crate(self, crate_id: int):
        try:
            crate = self.service.get_crate(crate_id)
            tracks = self.service.crate_tracks(crate)
        except Exception as exc:
            self.current_crate = None
            self._show_error("No se pudo abrir el crate", exc)
            return
        self.current_crate = crate
        self.current = None
        self._token += 1  # lo que estuviera evaluándose ya no corresponde
        # setCurrentItem(None) y no clearSelection(): si el ítem actual no
        # cambia, volver a clickear esa colección no emite nada.
        self.list_collections.blockSignals(True)
        self.list_collections.setCurrentItem(None)
        self.list_collections.blockSignals(False)

        self.lbl_title.setText(crate.name)
        self.lbl_subtitle.setText(f"Crate · {len(crate)} pistas")
        self._clear_layers()
        self.lbl_base.setText(
            "Un crate es una lista fija. Sumale pistas con clic derecho → Agregar a crate; "
            "Supr las saca del crate (no de la librería)."
        )
        self.lbl_warnings.setVisible(False)
        self._set_detail_enabled(False)
        # Un crate no tiene pila ni orden, pero sí tiene tracks que mostrar.
        self.lbl_empty.setVisible(False)
        self.lbl_base.setVisible(True)
        self.table.setVisible(True)
        self.table.set_tracks(TrackPresentationMapper.to_presentation_list(list(tracks)))
        self.lbl_status.setText(f"{len(tracks)} pistas")
        # Renombrar, duplicar y borrar valen para un crate igual que para una colección.
        for boton in (self.btn_rename, self.btn_duplicate, self.btn_delete):
            boton.setVisible(True)
            boton.setEnabled(True)
        self.btn_rename.setToolTip("Renombrar el crate")
        self.btn_duplicate.setToolTip("Duplicar el crate")
        self.btn_delete.setToolTip("Borrar el crate (las pistas siguen en la librería)")

    # =====================================================================
    # Dibujo de la colección abierta
    # =====================================================================

    def _clear_layers(self):
        for fila in self._layer_rows:
            fila.setParent(None)
            fila.deleteLater()
        self._layer_rows = []

    def _render_current(self):
        if self.current is None:
            return
        self._set_detail_enabled(True)
        self.lbl_base.setText("Librería completa")
        self.lbl_title.setText(self.current.name)

        capas = self.current.ordered_layers()
        self.lbl_subtitle.setText(
            f"{len(capas)} capa{'s' if len(capas) != 1 else ''}"
            + (f" · límite {self.current.limit}" if self.current.limit else "")
        )

        self._clear_layers()
        for indice, capa in enumerate(capas):
            fila = LayerRow(capa, indice, len(capas))
            fila.toggled.connect(self._on_toggle_layer)
            fila.edit_requested.connect(self._on_edit_layer)
            fila.remove_requested.connect(self._on_remove_layer)
            fila.move_requested.connect(self._on_move_layer)
            self.layers_layout.insertWidget(self.layers_layout.count() - 1, fila)
            self._layer_rows.append(fila)

        # Sin capas no hay pila que mostrar: el botón de agregar alcanza. Con
        # capas, la pila crece hasta cinco filas y después scrollea.
        visibles = min(5, len(capas))
        self.scroll_layers.setVisible(bool(capas))
        if capas:
            self.scroll_layers.setFixedHeight(visibles * LAYER_ROW_HEIGHT + (visibles - 1) * 6 + 2)

        # El desplegable de orden refleja lo guardado sin disparar un guardado.
        # Se busca a mano y no con findData(): Qt no compara bien una tupla de
        # Python guardada como userData, y el combo quedaba siempre en "Sin
        # orden" aunque el resultado viniera ordenado.
        self.combo_sort.blockSignals(True)
        buscado = (
            (self.current.sort.field, self.current.sort.direction)
            if self.current.sort else None
        )
        select_by_data(self.combo_sort, buscado)
        self.combo_sort.blockSignals(False)

        avisos = self.service.warnings(self.current)
        self.lbl_warnings.setText("\n".join(avisos))
        self.lbl_warnings.setVisible(bool(avisos))

        self._evaluate()

    def _evaluate(self, with_counts: bool = True):
        """Pide la página y los conteos a un worker; la UI no se bloquea.

        Al paginar la pila no cambió, así que los conteos por capa —la consulta
        más cara del motor— no se vuelven a pedir.
        """
        if self.current is None or self.service is None:
            return
        self._token += 1
        self._page_token = self._token
        self.lbl_status.setText("Evaluando…")
        # Hasta que llegue la página no se sabe si hay otra: dos clics rápidos
        # en «Siguiente» se pasaban del final.
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        if with_counts:
            self._counts_token = self._token
            for fila in self._layer_rows:
                fila.lbl_count.setText("…")

        worker = CollectionEvaluationWorker(
            self.service, self.current, offset=self._offset, page_size=PAGE_SIZE,
            with_counts=with_counts, token=self._token,
        )
        worker.signals.page_ready.connect(self._on_page_ready)
        worker.signals.counts_ready.connect(self._on_counts_ready)
        worker.signals.failed.connect(self._on_evaluation_failed)
        worker.signals.finished.connect(lambda: self._forget_worker(worker))
        self._workers.append(worker)
        self.pool.start(worker)

    def _forget_worker(self, worker):
        """Suelta la referencia una vez que el worker terminó de emitir."""
        try:
            self._workers.remove(worker)
        except ValueError:
            pass

    def _on_page_ready(self, token: int, page):
        if self.current is None or token != self._page_token:
            return  # llegó tarde: la pila o la página ya cambiaron
        self.table.set_tracks(
            TrackPresentationMapper.to_presentation_list(list(page.tracks))
        )
        desde = page.offset + 1 if len(page) else 0
        hasta = page.offset + len(page)
        self.lbl_status.setText(
            f"{desde}–{hasta} de {page.total} pistas"
        )
        self.btn_prev.setEnabled(page.offset > 0)
        self.btn_next.setEnabled(page.has_more)

    def _on_counts_ready(self, token: int, counts):
        if self.current is None or token != self._counts_token:
            return
        self.lbl_base.setText(f"Librería completa · {counts[0].after} pistas")
        # counts[0] es la base; de ahí en más va una entrada por capa activa.
        por_posicion = {c.position: c.after for c in counts[1:]}
        for fila in self._layer_rows:
            if fila.layer.position in por_posicion:
                fila.set_count(por_posicion[fila.layer.position])
            else:
                fila.lbl_count.setText("")  # apagada: no participa

    def _on_evaluation_failed(self, token: int, mensaje: str):
        if token != self._page_token:
            return  # error de una pila que ya no está en pantalla
        self.lbl_status.setText(f"No se pudo evaluar: {mensaje}")
        self.btn_prev.setEnabled(self._offset > 0)

    def _change_page(self, direccion: int):
        nuevo = self._offset + direccion * PAGE_SIZE
        self._offset = max(0, nuevo)
        self._evaluate(with_counts=False)

    # =====================================================================
    # Acciones sobre la colección
    # =====================================================================

    def _on_new(self):
        try:
            creada = self.service.create_unique()
        except Exception as exc:
            self._show_error("No se pudo crear la colección", exc)
            return
        self.current = creada
        self.refresh_collections()

    # Los botones del encabezado actúan sobre lo que esté abierto.
    def _on_duplicate(self):
        if self.current_crate is not None:
            self._duplicate_crate(self.current_crate.id)
        elif self.current is not None:
            self._duplicate_collection(self.current.id)

    def _on_rename(self):
        if self.current_crate is not None:
            self._rename_crate(self.current_crate.id)
        elif self.current is not None:
            self._rename_collection(self.current.id)

    def _on_delete(self):
        if self.current_crate is not None:
            self._delete_crate(self.current_crate.id)
        elif self.current is not None:
            self._delete_collection(self.current.id)

    # --- colecciones, por id (encabezado, menú y teclado usan las mismas) -------

    def _duplicate_collection(self, collection_id: int):
        try:
            copia = self.service.duplicate(self.service.get(collection_id))
        except Exception as exc:
            self._show_error("No se pudo duplicar", exc)
            return
        self.current, self.current_crate = copia, None
        self.refresh_collections()

    def _rename_collection(self, collection_id: int):
        try:
            coleccion = self.service.get(collection_id)
        except Exception as exc:
            self._show_error("No se pudo abrir la colección", exc)
            return
        nombre, ok = QInputDialog.getText(
            self, "Renombrar colección", "Nuevo nombre:", text=coleccion.name
        )
        if not ok or not nombre.strip():
            return
        try:
            renombrada = self.service.rename(coleccion, nombre.strip())
        except Exception as exc:
            self._show_error("No se pudo renombrar", exc)
            return
        if self.current is not None and self.current.id == collection_id:
            self.current = renombrada
        self.refresh_collections()

    def _delete_collection(self, collection_id: int):
        try:
            coleccion = self.service.get(collection_id)
        except Exception as exc:
            self._show_error("No se pudo abrir la colección", exc)
            return
        respuesta = QMessageBox.question(
            self,
            "Borrar colección",
            f"¿Borrar «{coleccion.name}»?\n\n"
            "Se borra la colección y sus capas. Las pistas no se tocan.",
        )
        if respuesta != QMessageBox.Yes:
            return
        try:
            self.service.delete(collection_id)
        except Exception as exc:
            self._show_error("No se pudo borrar", exc)
            return
        if self.current is not None and self.current.id == collection_id:
            self.current = None
        self.refresh_collections()

    def _freeze_collection(self, collection_id: int):
        try:
            crate = self.service.freeze_to_crate(self.service.get(collection_id))
        except Exception as exc:
            self._show_error("No se pudo congelar", exc)
            return
        self._refresh_crates()
        self.lbl_status.setText(f"Congelada en el crate «{crate.name}» ({len(crate)} pistas)")

    # --- crates ---------------------------------------------------------------

    def _new_crate(self):
        nombre, ok = QInputDialog.getText(self, "Nuevo crate", "Nombre del crate:", text="Nuevo crate")
        if not ok:
            return
        try:
            crate = self.service.create_crate(nombre)
        except Exception as exc:
            self._show_error("No se pudo crear el crate", exc)
            return
        self.current_crate, self.current = crate, None
        self.refresh_collections()

    def _rename_crate(self, crate_id: int):
        try:
            crate = self.service.get_crate(crate_id)
        except Exception as exc:
            self._show_error("No se pudo abrir el crate", exc)
            return
        nombre, ok = QInputDialog.getText(self, "Renombrar crate", "Nuevo nombre:", text=crate.name)
        if not ok or not nombre.strip():
            return
        try:
            renombrado = self.service.rename_crate(crate_id, nombre)
        except Exception as exc:
            self._show_error("No se pudo renombrar", exc)
            return
        if self.current_crate is not None and self.current_crate.id == crate_id:
            self.current_crate = renombrado
        self.refresh_collections()

    def _duplicate_crate(self, crate_id: int):
        try:
            copia = self.service.duplicate_crate(crate_id)
        except Exception as exc:
            self._show_error("No se pudo duplicar", exc)
            return
        self.current_crate, self.current = copia, None
        self.refresh_collections()

    def _delete_crate(self, crate_id: int):
        try:
            crate = self.service.get_crate(crate_id)
        except Exception as exc:
            self._show_error("No se pudo abrir el crate", exc)
            return
        respuesta = QMessageBox.question(
            self,
            "Borrar crate",
            f"¿Borrar «{crate.name}»?\n\n"
            "Se borra la lista. Las pistas siguen en tu librería.",
        )
        if respuesta != QMessageBox.Yes:
            return
        try:
            self.service.delete_crate(crate_id)
        except Exception as exc:
            self._show_error("No se pudo borrar", exc)
            return
        if self.current_crate is not None and self.current_crate.id == crate_id:
            self.current_crate = None
        self.refresh_collections()

    def on_crate_changed(self, crate_id: int):
        """Se crearon crates o se les agregaron pistas desde otra pantalla."""
        self._refresh_crates()
        if self.current_crate is not None and self.current_crate.id == crate_id:
            self._open_crate(crate_id)

    def _remove_from_crate(self, tracks: list):
        if self.current_crate is None:
            return
        try:
            crate, quitadas = self.service.remove_from_crate(
                self.current_crate.id, [t["id"] for t in tracks]
            )
        except Exception as exc:
            self._show_error("No se pudieron quitar del crate", exc)
            return
        self._open_crate(crate.id)
        self._refresh_crates()
        self.lbl_status.setText(
            f"{len(crate)} pistas · se quitaron {quitadas} del crate (siguen en la librería)"
        )

    # --- menús de las listas ----------------------------------------------------

    def _on_collections_menu(self, pos):
        menu = QMenu(self)
        item = self.list_collections.itemAt(pos)
        if item is not None:
            cid = item.data(Qt.UserRole)
            menu.addAction(icon(Icons.EDIT, TEXT_SECONDARY, 16), "Renombrar\tF2",
                           lambda: self._rename_collection(cid))
            menu.addAction(icon(Icons.DUPLICATE, TEXT_SECONDARY, 16), "Duplicar\tCtrl+D",
                           lambda: self._duplicate_collection(cid))
            menu.addAction(icon(Icons.CRATE, TEXT_SECONDARY, 16), "Congelar a crate",
                           lambda: self._freeze_collection(cid))
            menu.addSeparator()
            menu.addAction(icon(Icons.CLEAR, PRIMARY_RED, 16), "Borrar\tSupr",
                           lambda: self._delete_collection(cid))
            menu.addSeparator()
        menu.addAction(icon(Icons.PLUS, TEXT_SECONDARY, 16), "Nueva colección", self._on_new)
        menu.exec(self.list_collections.viewport().mapToGlobal(pos))

    def _on_crates_menu(self, pos):
        menu = QMenu(self)
        item = self.list_crates.itemAt(pos)
        if item is not None:
            crate_id = item.data(Qt.UserRole)
            menu.addAction(icon(Icons.EDIT, TEXT_SECONDARY, 16), "Renombrar\tF2",
                           lambda: self._rename_crate(crate_id))
            menu.addAction(icon(Icons.DUPLICATE, TEXT_SECONDARY, 16), "Duplicar\tCtrl+D",
                           lambda: self._duplicate_crate(crate_id))
            menu.addSeparator()
            menu.addAction(icon(Icons.CLEAR, PRIMARY_RED, 16), "Borrar\tSupr",
                           lambda: self._delete_crate(crate_id))
            menu.addSeparator()
        menu.addAction(icon(Icons.PLUS, TEXT_SECONDARY, 16), "Nuevo crate", self._new_crate)
        menu.exec(self.list_crates.viewport().mapToGlobal(pos))

    # --- la tabla de resultados (la usa TrackActions) ----------------------------

    def table_extra_actions(self, tracks: list) -> list:
        """Acciones propias de esta pantalla, arriba del menú de pistas."""
        if self.current_crate is not None:
            n = len(tracks)
            texto = "Quitar del crate" if n == 1 else f"Quitar {n} pistas del crate"
            return [(Icons.CLOSE, f"{texto}\tSupr", lambda: self._remove_from_crate(tracks))]
        return []

    def table_delete(self, tracks: list, shift: bool):
        """Supr en la tabla de esta pantalla.

        En un crate, saca las pistas del crate: es lo que se espera de una
        lista. En una colección no hay nada que sacar a mano (se filtra sola),
        así que Supr no borra de la librería por accidente: se explica. Con
        Shift sigue el camino normal (con su confirmación).
        """
        if shift:
            return False
        if self.current_crate is not None:
            self._remove_from_crate(tracks)
            return True
        # Un globo junto a la tabla y no la barra de estado: la página que se
        # está evaluando la reescribiría un instante después.
        from PySide6.QtWidgets import QToolTip  # noqa: PLC0415
        QToolTip.showText(
            self.table.mapToGlobal(self.table.rect().center()),
            "Una colección se filtra sola: para sacar pistas, agregá una capa que las "
            "excluya, o congelala a un crate y sacalas de ahí.",
            self.table,
        )
        return True

    def _on_sort_changed(self):
        if self.current is None:
            return
        dato = self.combo_sort.currentData()
        sort = SortSpec(dato[0], dato[1]) if dato else None
        try:
            self.current = self.service.set_sort(self.current, sort)
        except Exception as exc:
            self._show_error("No se pudo cambiar el orden", exc)
            return
        self._offset = 0
        self._render_current()

    def _on_freeze(self):
        if self.current is None:
            return
        self._freeze_collection(self.current.id)

    # =====================================================================
    # Acciones sobre las capas
    # =====================================================================

    def _on_add_layer(self):
        if self.current is None:
            return
        dialogo = LayerEditorDialog(service=self.service, parent=self)
        # Desde la clase: en PySide6 6.11 el enum no se lee desde la instancia
        # y `dialogo.Accepted` lanzaba AttributeError.
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.current = self.service.add_layer(
                self.current, dialogo.result_predicate, dialogo.result_mode
            )
        except Exception as exc:
            self._show_error("No se pudo agregar la capa", exc)
            return
        self._offset = 0
        self._render_current()

    def _on_edit_layer(self, position: int):
        if self.current is None:
            return
        capa = next(
            (l for l in self.current.ordered_layers() if l.position == position), None
        )
        if capa is None:
            return
        try:
            dialogo = LayerEditorDialog(service=self.service, layer=capa, parent=self)
        except Exception as exc:
            self._show_error("No se pudo abrir la capa", exc)
            return
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.current = self.service.replace_layer(
                self.current, position, dialogo.result_predicate, dialogo.result_mode
            )
        except Exception as exc:
            self._show_error("No se pudo guardar la capa", exc)
            return
        self._offset = 0
        self._render_current()

    def _on_toggle_layer(self, position: int, enabled: bool):
        if self.current is None:
            return
        try:
            self.current = self.service.toggle_layer(self.current, position, enabled)
        except Exception as exc:
            self._show_error("No se pudo cambiar la capa", exc)
            return
        self._offset = 0
        self._render_current()

    def _on_remove_layer(self, position: int):
        if self.current is None:
            return
        try:
            self.current = self.service.remove_layer(self.current, position)
        except Exception as exc:
            self._show_error("No se pudo borrar la capa", exc)
            return
        self._offset = 0
        self._render_current()

    def _on_move_layer(self, position: int, destino: int):
        if self.current is None:
            return
        try:
            self.current = self.service.move_layer(self.current, position, destino)
        except Exception as exc:
            self._show_error("No se pudo mover la capa", exc)
            return
        self._offset = 0
        self._render_current()

    # =====================================================================

    def _show_error(self, titulo: str, exc: Exception):
        """Los errores se muestran como mensaje, nunca como traza."""
        logger.error("%s: %s", titulo, exc)
        QMessageBox.warning(self, titulo, str(exc))
