"""
ui/dialogs/layer_editor_dialog.py
=================================
Diálogo para armar o editar una capa de una SmartCollection.

Es dibujo y nada más: la traducción entre lo que se ve acá y el AST vive en
``services/layer_form.py``, probada headless. Este archivo se limita a poner
controles, leerlos y pasárselos.

Una capa es un modo (filtrar / excluir / sumar) más una lista de condiciones
unidas por AND o por OR, cada una negable. Es un subconjunto del AST a
propósito: ver la unidad 10 del log de `ESTADO.md`.
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain.collections import LayerMode
from domain.query_ast import (
    QueryASTError,
    compare,
    range_,
    source,
    tag,
    tag_any,
    text,
)
from domain.tags import MANUAL_NAMESPACES, NAMESPACES
from services.layer_form import JOIN_AND, JOIN_OR, Condition, LayerForm
from ui.components.buttons import WLGhostButton, WLIconButton, WLPrimaryButton, WLSecondaryButton
from ui.theme.colors import BORDER_SUBTLE, PRIMARY_ORANGE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from ui.theme.icons import Icons
from ui.theme.spacing import SPACE_MD, SPACE_SM

logger = logging.getLogger(__name__)


def select_by_data(combo: QComboBox, value) -> bool:
    """Selecciona la opción cuyo dato es ``value``. Devuelve si la encontró.

    No se usa ``findData()``: Qt no compara bien los datos que no son tipos
    primitivos suyos —un enum de Python, una tupla— y devuelve -1 aunque la
    opción esté ahí. El síntoma es un desplegable que siempre muestra la primera
    opción por más que lo guardado sea otra.

    Ojo con lo que sale de vuelta: Qt **normaliza** lo que se guarda como dato.
    Un ``LayerMode.EXCLUDE`` guardado vuelve de ``currentData()`` como el string
    ``"exclude"``, no como el miembro del enum. Compara igual (el enum hereda de
    ``str``) pero no es idéntico, así que hay que reconstruirlo al leerlo.
    """
    for indice in range(combo.count()):
        if combo.itemData(indice) == value:
            combo.setCurrentIndex(indice)
            return True
    return False

# Los tipos de condición que ofrece el desplegable, en el orden en que un DJ
# los usa: primero los tags, después lo numérico, al final el texto.
KIND_TAG = "tag"
KIND_TAG_ANY = "tag_any"
KIND_RANGE = "range"
KIND_COMPARE = "compare"
KIND_TEXT = "text"
KIND_SOURCE = "source"

KIND_LABELS = [
    (KIND_TAG, "Tiene el tag"),
    (KIND_TAG_ANY, "Tiene algún tag de"),
    (KIND_RANGE, "Valor entre"),
    (KIND_COMPARE, "Comparación"),
    (KIND_TEXT, "Texto"),
    (KIND_SOURCE, "Origen"),
]

RANGE_FIELDS = [("bpm", "BPM"), ("energy", "Energía"), ("duration", "Duración (s)")]
COMPARE_FIELDS = RANGE_FIELDS + [("created_at", "Agregado"), ("analyzed_at", "Analizado")]
COMPARATOR_LABELS = [
    ("gt", "mayor que"),
    ("gte", "mayor o igual que"),
    ("lt", "menor que"),
    ("lte", "menor o igual que"),
    ("eq", "igual a"),
    ("ne", "distinto de"),
    ("is_null", "sin dato"),
    ("not_null", "con dato"),
]
TEXT_FIELDS = [("title", "Título"), ("artist", "Artista"), ("album", "Álbum")]
TEXT_MODES = [("contains", "contiene"), ("starts_with", "empieza con"), ("equals", "es")]
SOURCE_FIELDS = [
    ("source_platform", "Plataforma"),
    ("source_playlist_name", "Playlist"),
]


class ConditionRow(QWidget):
    """Una fila del editor: negación, tipo, y los controles que ese tipo pide."""

    def __init__(self, service=None, parent=None):
        super().__init__(parent)
        self.service = service
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_SM)

        self.combo_negated = QComboBox()
        self.combo_negated.addItem("que", False)
        self.combo_negated.addItem("que NO", True)
        self.combo_negated.setFixedWidth(104)
        layout.addWidget(self.combo_negated)

        self.combo_kind = QComboBox()
        for key, label in KIND_LABELS:
            self.combo_kind.addItem(label, key)
        self.combo_kind.setFixedWidth(150)
        self.combo_kind.currentIndexChanged.connect(self._on_kind_changed)
        layout.addWidget(self.combo_kind)

        # Los controles que dependen del tipo viven acá y se reconstruyen.
        self.args = QWidget()
        self.args_layout = QHBoxLayout(self.args)
        self.args_layout.setContentsMargins(0, 0, 0, 0)
        self.args_layout.setSpacing(SPACE_SM)
        layout.addWidget(self.args, 1)

        self.btn_remove = WLIconButton(Icons.DELETE, size=28, icon_px=15, tooltip="Quitar esta condición")
        self.btn_remove.setToolTip("Quitar esta condición")
        layout.addWidget(self.btn_remove)

        self._on_kind_changed()

    # --- construcción de los controles por tipo ---------------------------

    def _clear_args(self):
        while self.args_layout.count():
            item = self.args_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_kind_changed(self):
        self._clear_args()
        kind = self.combo_kind.currentData()
        builder = {
            KIND_TAG: self._build_tag,
            KIND_TAG_ANY: self._build_tag_any,
            KIND_RANGE: self._build_range,
            KIND_COMPARE: self._build_compare,
            KIND_TEXT: self._build_text,
            KIND_SOURCE: self._build_source,
        }[kind]
        builder()

    def _namespace_combo(self, only_manual: bool = False) -> QComboBox:
        combo = QComboBox()
        opciones = sorted(MANUAL_NAMESPACES) if only_manual else list(NAMESPACES)
        for ns in opciones:
            combo.addItem(ns, ns)
        # Arranca en un namespace que esta librería tenga poblado. El primero de
        # la lista es `genre`, que en una librería recién etiquetada
        # automáticamente está vacío: abrir el diálogo sobre un desplegable de
        # valores vacío hace parecer que el builder no funciona.
        if self.service is not None:
            for ns in self.service.used_namespaces():
                if select_by_data(combo, ns):
                    break
        return combo

    def _build_tag(self):
        self.combo_namespace = self._namespace_combo()
        self.combo_namespace.currentIndexChanged.connect(self._reload_values)
        self.combo_value = QComboBox()
        self.combo_value.setEditable(True)  # se puede tipear un valor que no está
        self.args_layout.addWidget(self.combo_namespace)
        self.args_layout.addWidget(QLabel(":"))
        self.args_layout.addWidget(self.combo_value, 1)
        self._reload_values()

    def _reload_values(self):
        if not hasattr(self, "combo_value"):
            return
        self.combo_value.clear()
        if self.service is None:
            return
        namespace = self.combo_namespace.currentData()
        for valor, usos in self.service.namespace_values(namespace):
            # El conteo va en el texto pero el dato es el valor limpio.
            self.combo_value.addItem(f"{valor}  ({usos})", valor)

    def _build_tag_any(self):
        self.combo_namespace = self._namespace_combo()
        self.args_layout.addWidget(self.combo_namespace)
        self.args_layout.addStretch()

    def _spin(self, minimo: float, maximo: float, valor: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(minimo, maximo)
        spin.setValue(valor)
        return spin

    def _build_range(self):
        self.combo_field = QComboBox()
        for key, label in RANGE_FIELDS:
            self.combo_field.addItem(label, key)
        self.spin_min = self._spin(0, 100000, 122)
        self.spin_max = self._spin(0, 100000, 128)
        self.args_layout.addWidget(self.combo_field)
        self.args_layout.addWidget(QLabel("de"))
        self.args_layout.addWidget(self.spin_min)
        self.args_layout.addWidget(QLabel("a"))
        self.args_layout.addWidget(self.spin_max)
        self.args_layout.addStretch()

    def _build_compare(self):
        self.combo_field = QComboBox()
        for key, label in COMPARE_FIELDS:
            self.combo_field.addItem(label, key)
        self.combo_cmp = QComboBox()
        for key, label in COMPARATOR_LABELS:
            self.combo_cmp.addItem(label, key)
        self.combo_cmp.currentIndexChanged.connect(self._on_cmp_changed)
        self.edit_value = QLineEdit()
        self.edit_value.setPlaceholderText("valor")
        self.args_layout.addWidget(self.combo_field)
        self.args_layout.addWidget(self.combo_cmp)
        self.args_layout.addWidget(self.edit_value, 1)
        self._on_cmp_changed()

    def _on_cmp_changed(self):
        # `sin dato` / `con dato` no llevan valor: esconderlo es más claro que
        # dejar un campo que se ignora.
        if hasattr(self, "edit_value"):
            unario = self.combo_cmp.currentData() in ("is_null", "not_null")
            self.edit_value.setVisible(not unario)

    def _build_text(self):
        self.combo_field = QComboBox()
        for key, label in TEXT_FIELDS:
            self.combo_field.addItem(label, key)
        self.combo_mode = QComboBox()
        for key, label in TEXT_MODES:
            self.combo_mode.addItem(label, key)
        self.edit_value = QLineEdit()
        self.edit_value.setPlaceholderText("texto a buscar")
        self.args_layout.addWidget(self.combo_field)
        self.args_layout.addWidget(self.combo_mode)
        self.args_layout.addWidget(self.edit_value, 1)

    def _build_source(self):
        self.combo_field = QComboBox()
        for key, label in SOURCE_FIELDS:
            self.combo_field.addItem(label, key)
        self.edit_value = QLineEdit()
        self.edit_value.setPlaceholderText("youtube, local, ...")
        self.args_layout.addWidget(self.combo_field)
        self.args_layout.addWidget(self.edit_value, 1)

    # --- lectura / escritura ---------------------------------------------

    def to_condition(self) -> Condition:
        """Lee los controles y devuelve la condición. Levanta si está incompleta."""
        kind = self.combo_kind.currentData()
        negated = bool(self.combo_negated.currentData())

        if kind == KIND_TAG:
            # El combo es editable: si el texto no coincide con la opción
            # seleccionada, el usuario tipeó un valor nuevo y es ése el que
            # vale. Leer siempre `currentData()` devolvía el valor de la opción
            # vieja y lo tipeado se perdía en silencio.
            indice = self.combo_value.currentIndex()
            texto = self.combo_value.currentText().strip()
            if indice >= 0 and texto == self.combo_value.itemText(indice):
                valor = self.combo_value.itemData(indice)
            else:
                valor = texto
            if not valor:
                raise QueryASTError("Elegí o escribí un valor para el tag")
            return Condition(tag(self.combo_namespace.currentData(), valor), negated)

        if kind == KIND_TAG_ANY:
            return Condition(tag_any(self.combo_namespace.currentData()), negated)

        if kind == KIND_RANGE:
            minimo, maximo = self.spin_min.value(), self.spin_max.value()
            if minimo > maximo:
                minimo, maximo = maximo, minimo
            return Condition(range_(self.combo_field.currentData(), minimo, maximo), negated)

        if kind == KIND_COMPARE:
            comparador = self.combo_cmp.currentData()
            if comparador in ("is_null", "not_null"):
                return Condition(compare(self.combo_field.currentData(), comparador), negated)
            crudo = self.edit_value.text().strip()
            if not crudo:
                raise QueryASTError("La comparación necesita un valor")
            return Condition(
                compare(self.combo_field.currentData(), comparador, _as_number(crudo)),
                negated,
            )

        if kind == KIND_TEXT:
            crudo = self.edit_value.text().strip()
            if not crudo:
                raise QueryASTError("Escribí el texto a buscar")
            return Condition(
                text(self.combo_field.currentData(), crudo, self.combo_mode.currentData()),
                negated,
            )

        crudo = self.edit_value.text().strip()
        if not crudo:
            raise QueryASTError("Escribí el origen a buscar")
        return Condition(source(self.combo_field.currentData(), crudo), negated)

    def load(self, condition: Condition):
        """Deja los controles mostrando esta condición."""
        self.combo_negated.setCurrentIndex(1 if condition.negated else 0)
        nodo = condition.node
        kind = {
            "tag": KIND_TAG, "tag_any": KIND_TAG_ANY, "range": KIND_RANGE,
            "compare": KIND_COMPARE, "text": KIND_TEXT, "source": KIND_SOURCE,
        }[nodo.op]
        select_by_data(self.combo_kind, kind)

        if kind in (KIND_TAG, KIND_TAG_ANY):
            select_by_data(self.combo_namespace, nodo.namespace)
            if kind == KIND_TAG:
                self._reload_values()
                if not select_by_data(self.combo_value, nodo.value):
                    self.combo_value.setEditText(nodo.value)
            return

        select_by_data(self.combo_field, nodo.field)
        if kind == KIND_RANGE:
            self.spin_min.setValue(float(nodo.min if nodo.min is not None else 0))
            self.spin_max.setValue(float(nodo.max if nodo.max is not None else 0))
        elif kind == KIND_COMPARE:
            select_by_data(self.combo_cmp, nodo.cmp)
            self._on_cmp_changed()
            if nodo.value is not None:
                self.edit_value.setText(str(nodo.value))
        elif kind == KIND_TEXT:
            select_by_data(self.combo_mode, nodo.mode)
            self.edit_value.setText(nodo.value)
        else:
            self.edit_value.setText(nodo.value)


def _as_number(raw: str):
    """Convierte a número si se puede; si no, lo deja como texto.

    Es lo que permite comparar una fecha ISO (texto) y un BPM (número) con el
    mismo control sin preguntarle al usuario de qué tipo es su valor.
    """
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


class LayerEditorDialog(QDialog):
    """Arma o edita una capa. ``result_layer`` queda con lo elegido al aceptar."""

    def __init__(self, service=None, layer=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar capa" if layer else "Nueva capa")
        self.setMinimumWidth(720)
        self.service = service
        self.result_mode: LayerMode = LayerMode.FILTER
        self.result_predicate = None
        self._rows: list[ConditionRow] = []

        self._build()
        if layer is not None:
            self._load_layer(layer)
        elif not self._rows:
            self._add_row()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(SPACE_MD)

        # Modo de la capa
        fila_modo = QHBoxLayout()
        fila_modo.setSpacing(SPACE_SM)
        etiqueta_modo = QLabel("Esta capa")
        etiqueta_modo.setFixedWidth(72)
        fila_modo.addWidget(etiqueta_modo)
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("filtra (se queda con los que cumplen)", LayerMode.FILTER)
        self.combo_mode.addItem("excluye (saca a los que cumplen)", LayerMode.EXCLUDE)
        self.combo_mode.addItem("suma (agrega de la librería)", LayerMode.UNION)
        fila_modo.addWidget(self.combo_mode, 1)
        layout.addLayout(fila_modo)

        # Unión de las condiciones
        fila_join = QHBoxLayout()
        fila_join.setSpacing(SPACE_SM)
        etiqueta_join = QLabel("las pistas")
        etiqueta_join.setFixedWidth(72)
        fila_join.addWidget(etiqueta_join)
        self.combo_join = QComboBox()
        self.combo_join.addItem("cumplan TODAS estas condiciones", JOIN_AND)
        self.combo_join.addItem("cumplan ALGUNA de estas condiciones", JOIN_OR)
        fila_join.addWidget(self.combo_join, 1)
        layout.addLayout(fila_join)

        linea = QFrame()
        linea.setFrameShape(QFrame.HLine)
        linea.setStyleSheet(f"background-color: {BORDER_SUBTLE}; border: none; height: 1px;")
        layout.addWidget(linea)

        # Condiciones
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        contenedor = QWidget()
        self.rows_layout = QVBoxLayout(contenedor)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(SPACE_SM)
        self.rows_layout.addStretch()
        self.scroll.setWidget(contenedor)
        layout.addWidget(self.scroll, 1)

        self.btn_add = WLGhostButton("Agregar condición", icon=Icons.PLUS)
        self.btn_add.clicked.connect(self._add_row)
        layout.addWidget(self.btn_add)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color: {TEXT_MUTED};")
        self.lbl_error.setWordWrap(True)
        layout.addWidget(self.lbl_error)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        botones.button(QDialogButtonBox.Ok).setText("Guardar capa")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self._on_accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    # --- filas ------------------------------------------------------------

    def _add_row(self) -> ConditionRow:
        fila = ConditionRow(service=self.service)
        fila.btn_remove.clicked.connect(lambda: self._remove_row(fila))
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, fila)
        self._rows.append(fila)
        self._update_remove_buttons()
        return fila

    def _remove_row(self, fila: ConditionRow):
        if len(self._rows) <= 1:
            return  # una capa sin condiciones no es una capa
        self._rows.remove(fila)
        fila.setParent(None)
        fila.deleteLater()
        self._update_remove_buttons()

    def _update_remove_buttons(self):
        # Con una sola condición, quitarla dejaría la capa vacía.
        for fila in self._rows:
            fila.btn_remove.setEnabled(len(self._rows) > 1)

    def _load_layer(self, layer):
        select_by_data(self.combo_mode, layer.mode)
        form = LayerForm.from_ast(layer.predicate)
        if form is None:
            # No debería llegar acá: el workspace no ofrece editar una capa que
            # no entra en el formulario. Si pasa, se empieza de cero en vez de
            # mostrar algo que no es lo que está guardado.
            logger.warning("Capa no representable en el formulario; se abre vacía")
            self._add_row()
            return
        select_by_data(self.combo_join, form.join)
        for condicion in form.conditions:
            self._add_row().load(condicion)

    # --- aceptar ----------------------------------------------------------

    def selected_mode(self) -> LayerMode:
        """El modo elegido, reconstruido como enum.

        ``currentData()`` devuelve el string plano porque Qt normaliza los datos
        que guarda; el resto del código espera un ``LayerMode``.
        """
        return LayerMode(self.combo_mode.currentData())

    def _on_accept(self):
        form = LayerForm(join=self.combo_join.currentData())
        try:
            for fila in self._rows:
                condicion = fila.to_condition()
                form.conditions.append(condicion)
            self.result_predicate = form.to_ast()
        except Exception as exc:
            # Un error de armado se muestra en el diálogo; cerrar y perder lo
            # tipeado sería lo peor que puede hacer acá.
            self.lbl_error.setText(str(exc))
            self.lbl_error.setStyleSheet(f"color: {PRIMARY_ORANGE};")
            return

        self.result_mode = self.selected_mode()
        self.accept()
