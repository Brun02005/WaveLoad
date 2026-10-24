"""
ui/dialogs/tag_editor_dialog.py
===============================
Editar las etiquetas de una o varias pistas: género, mood, momento del set y
estado.

Con varias pistas, cada etiqueta muestra en cuántas está ("2/5"): un clic la
completa en todas, la cruz la saca de todas. Nada se escribe hasta "Guardar":
el diálogo arma la diferencia (qué agregar, qué quitar) y quien lo abrió la
aplica en una sola transacción.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCompleter, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from domain.tags import Tag
from ui.components.buttons import WLGhostButton, WLPrimaryButton
from ui.components.flow_layout import FlowLayout
from ui.mappers.tag_labels import (
    EDITABLE_NAMESPACES, NAMESPACE_HINTS, NAMESPACE_TITLES, SUGGESTIONS, tag_label,
)
from ui.theme.colors import (
    ACCENT, ACCENT_SOFT, BORDER_DEFAULT, BORDER_SUBTLE, SURFACE_2, SURFACE_3,
    SURFACE_4, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.theme.icons import Icons, icon

MAX_SUGGESTIONS = 10


def _button_text(text: str) -> str:
    """En un botón de Qt, ``&`` marca un atajo y desaparece: "Drum & Bass" se
    veía "Drum _Bass". Doblado se muestra literal."""
    return text.replace("&", "&&")


class _Chip(QPushButton):
    """Una etiqueta asignada. Clic: completarla en todas; cruz: sacarla."""

    removed = Signal(str)
    completed = Signal(str)

    def __init__(self, value: str, label: str, count: int, total: int):
        super().__init__()
        self.value = value
        parcial = count < total
        self.setCursor(Qt.PointingHandCursor)
        self.setText(_button_text(f"{label}  ·  {count}/{total}" if parcial else label))
        self.setIcon(icon(Icons.CLOSE, TEXT_SECONDARY, 12))
        self.setLayoutDirection(Qt.RightToLeft)  # la cruz a la derecha
        self.setToolTip(
            f"Está en {count} de {total} pistas. Clic para ponerla en todas; "
            "la cruz la saca de todas." if parcial else "Clic en la cruz para quitarla"
        )
        fondo = SURFACE_3 if parcial else ACCENT_SOFT
        borde = BORDER_DEFAULT if parcial else "rgba(22, 190, 198, 0.35)"
        self.setStyleSheet(
            f"QPushButton {{ background-color: {fondo}; border: 1px solid {borde};"
            f" border-radius: 13px; padding: 4px 10px; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; }}"
        )
        self.setFixedHeight(28)

    def mouseReleaseEvent(self, event):
        # Primero se termina de procesar el clic y después se avisa: quien
        # escucha redibuja la sección y este chip deja de existir.
        en_la_cruz = event.position().x() >= self.width() - 26
        super().mouseReleaseEvent(event)
        if en_la_cruz:
            self.removed.emit(self.value)
        else:
            self.completed.emit(self.value)


class _Suggestion(QPushButton):
    """Un valor que todavía no está: clic para ponerlo en todas."""

    def __init__(self, label: str):
        super().__init__(_button_text(f"+ {label}"))
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(28)
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px dashed {BORDER_DEFAULT};"
            f" border-radius: 13px; padding: 4px 10px; color: {TEXT_SECONDARY}; }}"
            f"QPushButton:hover {{ border-color: {TEXT_MUTED}; color: {TEXT_PRIMARY}; }}"
        )


class _NamespaceSection(QWidget):
    """Un eje (género, mood…): lo asignado, sugerencias y un campo para escribir."""

    changed = Signal()

    def __init__(self, namespace: str, counts: dict, total: int, vocabulary: list):
        super().__init__()
        self.namespace = namespace
        self.total = total
        self.counts = dict(counts)          # valor -> en cuántas pistas está
        self.vocabulary = vocabulary        # valores conocidos, por uso

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        cabecera = QHBoxLayout()
        titulo = QLabel(NAMESPACE_TITLES[namespace])
        titulo.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 600;")
        pista = QLabel(NAMESPACE_HINTS[namespace])
        pista.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        cabecera.addWidget(titulo)
        cabecera.addSpacing(8)
        cabecera.addWidget(pista)
        cabecera.addStretch()
        v.addLayout(cabecera)

        self.chips_box = QWidget()
        self.chips = FlowLayout(self.chips_box)
        v.addWidget(self.chips_box)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Escribí una nueva y Enter")
        self.input.setFixedHeight(32)
        etiquetas = [tag_label(namespace, x) for x in self._known_values()]
        completer = QCompleter(etiquetas, self.input)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.input.setCompleter(completer)
        self.input.returnPressed.connect(self._on_typed)
        v.addWidget(self.input)

        self._render()

    def _known_values(self) -> list:
        vistos = []
        for x in [*self.vocabulary, *SUGGESTIONS.get(self.namespace, [])]:
            if x not in vistos:
                vistos.append(x)
        return vistos

    def _render(self):
        self.chips.clear()
        presentes = [x for x, n in self.counts.items() if n > 0]
        for valor in sorted(presentes, key=lambda x: (-self.counts[x], x)):
            chip = _Chip(valor, tag_label(self.namespace, valor), self.counts[valor], self.total)
            chip.removed.connect(self._remove)
            chip.completed.connect(self._add)
            self.chips.addWidget(chip)
        sugeridas = [x for x in self._known_values() if self.counts.get(x, 0) == 0]
        for valor in sugeridas[:MAX_SUGGESTIONS]:
            boton = _Suggestion(tag_label(self.namespace, valor))
            boton.clicked.connect(lambda _=False, x=valor: self._add(x))
            self.chips.addWidget(boton)
        self.chips_box.updateGeometry()

    def _add(self, valor: str):
        self.counts[valor] = self.total
        self._render()
        self.changed.emit()

    def _remove(self, valor: str):
        self.counts[valor] = 0
        self._render()
        self.changed.emit()

    def _on_typed(self):
        texto = self.input.text().strip()
        if not texto:
            return
        # Si coincide con una etiqueta conocida ("Peak time"), se usa su valor.
        por_etiqueta = {tag_label(self.namespace, x).lower(): x for x in self._known_values()}
        valor = por_etiqueta.get(texto.lower())
        if valor is None:
            try:
                valor = Tag(self.namespace, texto).value
            except ValueError:
                return
        self.input.clear()
        self._add(valor)


class TagEditorDialog(QDialog):
    """Devuelve en ``result_add`` y ``result_remove`` los ``Tag`` a aplicar."""

    def __init__(self, tracks: list, current: dict, vocabulary: dict, parent=None):
        """
        tracks: dicts de presentación de las pistas seleccionadas.
        current: {track_id: [Tag]} con los tags manuales actuales.
        vocabulary: {namespace: [valores conocidos en la librería, por uso]}.
        """
        super().__init__(parent)
        self.setWindowTitle("Etiquetas")
        self.setMinimumWidth(620)
        self.result_add: list = []
        self.result_remove: list = []

        total = len(tracks)
        self._original: dict = {}
        for ns in EDITABLE_NAMESPACES:
            conteo: dict = {}
            for track in tracks:
                for tag in current.get(track["id"], []):
                    if tag.namespace == ns:
                        conteo[tag.value] = conteo.get(tag.value, 0) + 1
            self._original[ns] = conteo

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 20, 24, 16)
        raiz.setSpacing(4)
        titulo = QLabel("Etiquetas")
        titulo.setObjectName("wl_title")
        if total == 1:
            sub = tracks[0].get("title", "")
        else:
            sub = f"{total} pistas seleccionadas · los cambios se aplican a todas"
        subtitulo = QLabel(sub)
        subtitulo.setStyleSheet(f"color: {TEXT_SECONDARY};")
        raiz.addWidget(titulo)
        raiz.addWidget(subtitulo)
        raiz.addSpacing(14)

        contenido = QWidget()
        cv = QVBoxLayout(contenido)
        cv.setContentsMargins(0, 0, 8, 0)
        cv.setSpacing(18)
        self.sections = {}
        for i, ns in enumerate(EDITABLE_NAMESPACES):
            if i:
                linea = QFrame()
                linea.setFixedHeight(1)
                linea.setStyleSheet(f"background-color: {BORDER_SUBTLE}; border: none;")
                cv.addWidget(linea)
            seccion = _NamespaceSection(ns, self._original[ns], total, vocabulary.get(ns, []))
            self.sections[ns] = seccion
            cv.addWidget(seccion)
        cv.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenido)
        scroll.setMinimumHeight(460)
        raiz.addWidget(scroll, 1)

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = WLGhostButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        guardar = WLPrimaryButton("Guardar", height=34)
        guardar.clicked.connect(self._on_save)
        botones.addWidget(cancelar)
        botones.addWidget(guardar)
        raiz.addSpacing(10)
        raiz.addLayout(botones)
        self.setStyleSheet(f"QDialog {{ background-color: {SURFACE_2}; }}")

    def _on_save(self):
        add, remove = [], []
        for ns, seccion in self.sections.items():
            antes = self._original[ns]
            for valor, ahora in seccion.counts.items():
                previo = antes.get(valor, 0)
                if ahora == seccion.total and previo < seccion.total:
                    add.append(Tag(ns, valor))
                elif ahora == 0 and previo > 0:
                    remove.append(Tag(ns, valor))
        self.result_add, self.result_remove = add, remove
        self.accept()
