"""
ui/workspaces/graph_workspace.py
================================
The Music Knowledge Graph canvas as a *set-building* surface: you pick tracks
from the library list on the left and add them to the graph, which lays them out
by harmonic/tempo relationships. Force-directed layout, zoom / pan / drag,
community colouring, transition heat-map edges, node selection and a Path Finder
that routes between two tracks on the canvas.
"""

import logging
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsLineItem, QStackedWidget, QListWidget, QListWidgetItem,
    QLineEdit, QStyledItemDelegate, QStyle, QCheckBox, QComboBox, QScrollArea,
)
from PySide6.QtCore import Qt, QRectF, QRect, QPointF, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics

from ui.workspaces.base_workspace import BaseWorkspace
from ui.theme.colors import (
    ACCENT, ACCENT_MUTED, SURFACE_BASE, SURFACE_1, SURFACE_3, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, BORDER_DEFAULT,
)
from ui.theme.typography import FONT_FAMILY_MONO
from ui.theme.icons import Icons
from ui.components.buttons import WLSecondaryButton, WLIconButton
from ui.components.tables import camelot_qcolors
from services.graph_service import GraphService
from services.similarity_service import SimilarityEngine
from services.set_builder_service import SetBuilderService, EVENT_PRESETS
from services.export_service import build_m3u8, build_rekordbox_xml

_TRACK_ROLE = Qt.UserRole
_ONMAP_ROLE = Qt.UserRole + 1
_ID_ROLE = Qt.UserRole + 2


class _TrackItem(QListWidgetItem):
    """List item that sorts by a numeric key (compatibility-aware ordering)."""
    def __init__(self):
        super().__init__()
        self.default_key = 0.0  # alphabetical position
        self.sort_key = 0.0

    def __lt__(self, other):
        return self.sort_key < getattr(other, "sort_key", 0.0)


_STEP_ID = Qt.UserRole        # track id (string — survives drag serialization)
_STEP_WARN = Qt.UserRole + 1  # joined warning text ("" if none)


class StepDelegate(QStyledItemDelegate):
    """Horizontal step card for the generated-set timeline (number + Camelot
    chip + title + BPM·energy + warning). Resolves the track dict via a lookup
    so only the (serializable) id is stored on the item."""

    def __init__(self, parent, lookup):
        super().__init__(parent)
        self._lookup = lookup

    def sizeHint(self, option, index):
        return QSize(142, 58)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        t = self._lookup(index.data(_STEP_ID)) or {}
        warns = index.data(_STEP_WARN) or ""
        rect = option.rect.adjusted(3, 3, -3, -3)
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor(ACCENT), 1))
        else:
            painter.setPen(QPen(QColor(BORDER_DEFAULT), 0.5))
        painter.setBrush(QColor(SURFACE_BASE))
        painter.drawRoundedRect(rect, 6, 6)

        pad = 7
        nf = QFont(FONT_FAMILY_MONO); nf.setPixelSize(10)
        painter.setFont(nf); painter.setPen(QColor(TEXT_MUTED))
        painter.drawText(QRect(rect.left() + pad, rect.top() + 5, 18, 14),
                         Qt.AlignLeft | Qt.AlignVCenter, str(index.row() + 1))
        key = str(t.get("key", "—"))
        bg, fg = camelot_qcolors(key)
        chip = QRect(rect.left() + pad + 16, rect.top() + 5, 30, 16)
        painter.setPen(Qt.NoPen); painter.setBrush(bg)
        painter.drawRoundedRect(chip, 8, 8)
        cf = QFont(FONT_FAMILY_MONO); cf.setPixelSize(9); cf.setBold(True)
        painter.setFont(cf); painter.setPen(fg)
        painter.drawText(chip, Qt.AlignCenter, key)
        if warns:
            painter.setPen(QColor("#E0A83A"))
            wf = QFont(); wf.setPixelSize(11); painter.setFont(wf)
            painter.drawText(QRect(rect.right() - pad - 14, rect.top() + 4, 14, 14),
                             Qt.AlignCenter, "⚠")

        tw = rect.width() - 2 * pad
        tf = QFont(); tf.setPixelSize(11); painter.setFont(tf)
        painter.setPen(QColor(TEXT_PRIMARY))
        title = QFontMetrics(tf).elidedText(str(t.get("title", "—")), Qt.ElideRight, tw)
        painter.drawText(QRect(rect.left() + pad, rect.top() + 24, tw, 15),
                         Qt.AlignLeft | Qt.AlignVCenter, title)
        mf = QFont(FONT_FAMILY_MONO); mf.setPixelSize(10); painter.setFont(mf)
        painter.setPen(QColor(TEXT_MUTED))
        painter.drawText(QRect(rect.left() + pad, rect.bottom() - 16, tw, 14),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         f"{t.get('bpm', '—')} BPM · E{t.get('energy', '?')}")
        painter.restore()


class SetListWidget(QListWidget):
    """Horizontal, drag-to-reorder list for the generated set."""
    reordered = Signal()

    def __init__(self):
        super().__init__()
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListWidget.Adjust)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


class TrackListDelegate(QStyledItemDelegate):
    """Two-line list row: Camelot chip + title, with BPM · artist beneath."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 46)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        t = index.data(_TRACK_ROLE) or {}
        on_map = bool(index.data(_ONMAP_ROLE))
        rect = option.rect

        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, QColor(SURFACE_3))
        elif on_map:
            painter.fillRect(rect, QColor(ACCENT_MUTED))
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 0.5))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        pad = 10
        key = str(t.get("key", "—"))
        bg, fg = camelot_qcolors(key)
        chip = QRect(rect.left() + pad, rect.center().y() - 10, 34, 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(chip, 10, 10)
        cf = QFont(FONT_FAMILY_MONO); cf.setPixelSize(10); cf.setBold(True)
        painter.setFont(cf)
        painter.setPen(fg)
        painter.drawText(chip, Qt.AlignCenter, key)

        tx = chip.right() + 10
        tw = max(20, rect.right() - tx - pad - 14)
        tf = QFont(); tf.setPixelSize(12)
        painter.setFont(tf)
        painter.setPen(QColor(TEXT_PRIMARY))
        title = QFontMetrics(tf).elidedText(str(t.get("title", "—")), Qt.ElideRight, tw)
        painter.drawText(QRect(tx, rect.top() + 6, tw, 16), Qt.AlignLeft | Qt.AlignVCenter, title)

        sf = QFont(); sf.setPixelSize(10)
        painter.setFont(sf)
        painter.setPen(QColor(TEXT_MUTED))
        sub = f"{t.get('bpm', '—')} BPM · {t.get('artist', '—')}"
        sub = QFontMetrics(sf).elidedText(sub, Qt.ElideRight, tw)
        painter.drawText(QRect(tx, rect.bottom() - 20, tw, 14), Qt.AlignLeft | Qt.AlignVCenter, sub)

        if on_map:
            painter.setPen(QColor(ACCENT))
            painter.drawText(QRect(rect.right() - pad - 14, rect.top(), 14, rect.height()),
                             Qt.AlignCenter, "✓")
        painter.restore()

logger = logging.getLogger(__name__)

_COMMUNITY_COLORS = [
    "#16BEC6", "#7C6CF0", "#E2724A", "#4CAF6E", "#E0A83A", "#D4537E",
    "#5B8DEF", "#3FBFA0", "#B57BE0", "#E0574A", "#8FB03A", "#4A9DE0",
]

_NODE_RADIUS = 18.0


def _edge_color(score: int) -> str:
    if score >= 90:
        return ACCENT
    if score >= 80:
        return "#2b8f95"
    return "#4a5058"


def _edge_width(score: int) -> float:
    return 1.3 + (max(72, min(100, score)) - 72) / 28.0 * 2.6


class EdgeItem(QGraphicsLineItem):
    def __init__(self, src: "NodeItem", dst: "NodeItem", score: int):
        super().__init__()
        self.src = src
        self.dst = dst
        self.score = score
        self.setZValue(-1)
        self._state = "normal"
        self.adjust()
        self._apply_pen()

    def adjust(self):
        self.setLine(self.src.x(), self.src.y(), self.dst.x(), self.dst.y())

    def _apply_pen(self):
        if self._state == "path":
            color, width, op = ACCENT, 3.4, 1.0
        elif self._state == "active":
            color, width, op = _edge_color(self.score), _edge_width(self.score) + 0.6, 0.95
        elif self._state == "dim":
            color, width, op = "#2a2e34", 1.0, 0.25
        else:
            color, width, op = _edge_color(self.score), _edge_width(self.score), 0.55
        pen = QPen(QColor(color))
        pen.setWidthF(width)
        pen.setCapStyle(Qt.RoundCap)
        c = QColor(color)
        c.setAlphaF(op)
        pen.setColor(c)
        self.setPen(pen)

    def set_state(self, state: str):
        self._state = state
        self.setZValue(1 if state in ("path", "active") else -1)
        self._apply_pen()


class OrderLineItem(QGraphicsLineItem):
    """A segment of the generated-set route; follows its two nodes when moved."""
    def __init__(self, src: "NodeItem", dst: "NodeItem"):
        super().__init__()
        self.src = src
        self.dst = dst
        self.setZValue(1)
        pen = QPen(QColor(ACCENT))
        pen.setWidthF(2.5)
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)
        self.adjust()

    def adjust(self):
        self.setLine(self.src.x(), self.src.y(), self.dst.x(), self.dst.y())


class NodeItem(QGraphicsItem):
    def __init__(self, node_id: str, data: dict, color: str, on_click, on_context=None):
        super().__init__()
        self.node_id = node_id
        self.data = data
        self.base_color = color
        self._on_click = on_click
        self._on_context = on_context
        self.anchor_role: Optional[str] = None   # 'start' / 'end' / 'peak'
        self.order_number: Optional[int] = None  # position in the generated set
        self.edges: List[EdgeItem] = []
        self.order_edges: list = []              # route lines to keep in sync
        self._state = "normal"
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        self._cam_font = QFont(FONT_FAMILY_MONO)
        self._cam_font.setPixelSize(11)
        self._cam_font.setBold(True)
        self._title_font = QFont()
        self._title_font.setPixelSize(9)

    def boundingRect(self) -> QRectF:
        r = _NODE_RADIUS
        return QRectF(-r - 12, -r - 20, 2 * r + 24, 2 * r + 48)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = _NODE_RADIUS
        color = QColor(self.base_color)
        if self._state == "dim":
            color.setAlphaF(0.35)
        if self._state in ("selected", "path"):
            glow = QColor(ACCENT)
            glow.setAlphaF(0.30)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(0, 0), r + 6, r + 6)

        fill = QColor(color)
        fill.setAlphaF(0.22 if self._state != "dim" else 0.12)
        painter.setBrush(fill)
        ring = QColor(ACCENT) if self._state in ("selected", "path") else color
        pen = QPen(ring)
        pen.setWidthF(2.2 if self._state in ("selected", "path") else 1.8)
        painter.setPen(pen)
        painter.drawEllipse(QPointF(0, 0), r, r)

        txt = QColor(TEXT_PRIMARY)
        if self._state == "dim":
            txt.setAlphaF(0.4)
        painter.setPen(txt)
        painter.setFont(self._cam_font)
        painter.drawText(QRectF(-r, -r, 2 * r, 2 * r), Qt.AlignCenter, str(self.data.get("key", "")))

        painter.setFont(self._title_font)
        sub = QColor(TEXT_SECONDARY)
        if self._state == "dim":
            sub.setAlphaF(0.35)
        painter.setPen(sub)
        title = str(self.data.get("title", ""))
        if len(title) > 16:
            title = title[:15] + "…"
        painter.drawText(QRectF(-42, r + 2, 84, 14), Qt.AlignHCenter | Qt.AlignTop, title)

        if self.anchor_role:
            letter = {"start": "A", "end": "C", "peak": "P"}.get(self.anchor_role, "•")
            badge = QRectF(-r - 3, -r - 16, 16, 14)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ACCENT))
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QColor("#08130d"))
            bf = QFont(); bf.setPixelSize(9); bf.setBold(True)
            painter.setFont(bf)
            painter.drawText(badge, Qt.AlignCenter, letter)

        if self.order_number is not None:
            r2 = 9.0
            cx, cy = r + 1, -r - 4
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ACCENT))
            painter.drawEllipse(QPointF(cx, cy), r2, r2)
            painter.setPen(QColor("#08130d"))
            of = QFont(); of.setPixelSize(10); of.setBold(True)
            painter.setFont(of)
            painter.drawText(QRectF(cx - r2, cy - r2, 2 * r2, 2 * r2),
                             Qt.AlignCenter, str(self.order_number))

    def contextMenuEvent(self, event):
        if self._on_context:
            self._on_context(self.node_id, event.screenPos())
            event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for e in self.edges:
                e.adjust()
            for e in self.order_edges:
                e.adjust()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if self._on_click:
            self._on_click(self.node_id)
        super().mousePressEvent(event)

    def set_state(self, state: str):
        self._state = state
        self.update()


class GraphView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setBackgroundBrush(QColor(SURFACE_BASE))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._panning = False
        self._pan_start = QPointF()

    def wheelEvent(self, event):
        factor = 1.16 if event.angleDelta().y() > 0 else 1 / 1.16
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.itemAt(event.position().toPoint()) is None:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class GraphWorkspace(BaseWorkspace):
    track_selected = Signal(dict)
    toggle_panel_requested = Signal(bool)

    def __init__(self, library_service, parent=None):
        super().__init__(parent)
        self.library_service = library_service
        from ui.mappers.track_mapper import TrackPresentationMapper
        self._mapper = TrackPresentationMapper

        self._populated = False
        self._track_index: Dict[str, dict] = {}
        self._list_items: Dict[str, QListWidgetItem] = {}
        self._selected_ids: List[str] = []
        self._positions: Dict[str, tuple] = {}
        self._nodes: Dict[str, NodeItem] = {}
        self._edges: List[EdgeItem] = []
        self._graph = None
        self._service = GraphService()
        self._engine = SimilarityEngine()
        self._set_builder = SetBuilderService()
        self._order_items: list = []
        self._anchors: Dict[str, str] = {}   # role -> track id (start/end/peak)
        self._current_set = None
        self._set_active = False   # once a set is built, keep it live as the map changes
        self._custom_curve = None  # Journey Designer curve when event == 'custom'
        self._scale = 700.0
        self._compat_only = True
        self._sort_mode = "alpha"   # 'alpha' | 'bpm_asc' | 'bpm_desc'
        self._selected_track: Optional[dict] = None
        self._route_mode = False
        self._route_start: Optional[str] = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setStyleSheet(f"background-color: {SURFACE_1}; border-bottom: 1px solid {BORDER_DEFAULT};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 8, 14, 8)
        title = QLabel("Music Knowledge Graph")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        bl.addWidget(title)
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        bl.addWidget(self.lbl_stats)
        bl.addStretch()
        self.event_combo = QComboBox()
        for key, label in EVENT_PRESETS.items():
            self.event_combo.addItem(label, key)
        self.event_combo.addItem("Personalizada", "custom")
        self.event_combo.setCurrentIndex(1)  # club prime-time
        self.event_combo.setToolTip("Tipo de evento — define la curva de energía del set")
        self.event_combo.currentIndexChanged.connect(self._on_event_changed)
        bl.addWidget(self.event_combo)
        self.btn_edit_curve = WLSecondaryButton("Editar curva")
        self.btn_edit_curve.setToolTip("Journey Designer — dibujá tu curva de energía")
        self.btn_edit_curve.setVisible(False)
        self.btn_edit_curve.clicked.connect(self._open_journey)
        bl.addWidget(self.btn_edit_curve)
        self.btn_build = WLSecondaryButton("Armar set")
        self.btn_build.setToolTip("Genera un orden con curva de energía + flujo armónico")
        bl.addWidget(self.btn_build)
        from PySide6.QtWidgets import QSlider  # noqa: PLC0415
        lam_lbl = QLabel("Flujo")
        lam_lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        bl.addWidget(lam_lbl)
        self.lam_slider = QSlider(Qt.Horizontal)
        self.lam_slider.setFixedWidth(80)
        self.lam_slider.setRange(0, 100)
        self.lam_slider.setValue(60)
        self.lam_slider.setToolTip("Prioridad: flujo de mezcla ↔ curva de energía")
        bl.addWidget(self.lam_slider)
        lam_lbl2 = QLabel("Curva")
        lam_lbl2.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        bl.addWidget(lam_lbl2)
        self.btn_route = WLSecondaryButton("Buscar ruta")
        self.btn_route.setCheckable(True)
        self.btn_route.setToolTip("Elegí dos pistas del mapa para trazar el mejor recorrido")
        self.btn_clear_route = WLSecondaryButton("Limpiar")
        self.btn_clear_all = WLSecondaryButton("Vaciar mapa")
        bl.addWidget(self.btn_route)
        bl.addWidget(self.btn_clear_route)
        bl.addWidget(self.btn_clear_all)
        self.btn_info = WLIconButton(Icons.INFO)
        self.btn_info.setCheckable(True)
        self.btn_info.setChecked(True)
        self.btn_info.setToolTip("Mostrar/Ocultar panel de detalles")
        bl.addWidget(self.btn_info)
        root.addWidget(bar)

        # Body: track list | canvas
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        left = QWidget()
        left.setFixedWidth(320)
        left.setStyleSheet(f"background-color: {SURFACE_1}; border-right: 1px solid {BORDER_DEFAULT};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)
        hint = QLabel("Doble click para agregar / quitar del mapa")
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        hint.setWordWrap(True)
        ll.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar pista o artista…")
        self.search.setObjectName("wl_searchInput")
        ll.addWidget(self.search)
        self.chk_compat = QCheckBox("Solo compatibles con la selección")
        self.chk_compat.setChecked(True)
        self.chk_compat.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        ll.addWidget(self.chk_compat)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Ordenar: Título (A-Z)", "alpha")
        self.sort_combo.addItem("Ordenar: BPM ↑ (menor→mayor)", "bpm_asc")
        self.sort_combo.addItem("Ordenar: BPM ↓ (mayor→menor)", "bpm_desc")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        ll.addWidget(self.sort_combo)
        self.track_list = QListWidget()
        self.track_list.setItemDelegate(TrackListDelegate(self.track_list))
        self.track_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.track_list.setUniformItemSizes(True)
        self.track_list.setStyleSheet(
            f"QListWidget {{ background: {SURFACE_BASE}; border: 1px solid {BORDER_DEFAULT};"
            f" border-radius: 6px; outline: none; }}"
        )
        ll.addWidget(self.track_list, 1)
        body.addWidget(left)

        self.stack = QStackedWidget()
        self.empty_hint = QLabel("Agregá pistas desde la lista para empezar a armar tu set")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        self.stack.addWidget(self.empty_hint)
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QColor(SURFACE_BASE))
        self.view = GraphView(self.scene)
        self.stack.addWidget(self.view)
        self.stack.setCurrentWidget(self.empty_hint)
        body.addWidget(self.stack, 1)

        root.addLayout(body, 1)

        # Bottom "Set sugerido" timeline (hidden until a set is generated).
        self.set_panel = QWidget()
        self.set_panel.setFixedHeight(104)
        self.set_panel.setStyleSheet(f"background-color: {SURFACE_1}; border-top: 1px solid {BORDER_DEFAULT};")
        spv = QVBoxLayout(self.set_panel)
        spv.setContentsMargins(12, 6, 12, 8)
        spv.setSpacing(4)
        set_head = QHBoxLayout(); set_head.setContentsMargins(0, 0, 0, 0)
        self.lbl_set = QLabel("Set sugerido")
        self.lbl_set.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_PRIMARY};")
        set_head.addWidget(self.lbl_set)
        set_head.addStretch()
        hint2 = QLabel("Arrastrá para reordenar · click derecho en un nodo para anclar")
        hint2.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        set_head.addWidget(hint2)
        self.btn_export = WLSecondaryButton("Exportar")
        self.btn_export.setToolTip("Exportar el set a M3U8 o rekordbox XML")
        self.btn_export.clicked.connect(self._on_export)
        set_head.addWidget(self.btn_export)
        spv.addLayout(set_head)
        self.set_list = SetListWidget()
        self.set_list.setFixedHeight(64)
        self.set_list.setItemDelegate(StepDelegate(self.set_list, self._track_index.get))
        self.set_list.setStyleSheet("QListWidget { background: transparent; border: none; outline: none; }")
        self.set_list.reordered.connect(self._on_steps_reordered)
        spv.addWidget(self.set_list)
        self.set_panel.setVisible(False)
        root.addWidget(self.set_panel)

        self.btn_build.clicked.connect(self._on_build_set)
        self.lam_slider.sliderReleased.connect(self._on_lambda_changed)
        self.search.textChanged.connect(lambda _=None: self._apply_filters())
        self.chk_compat.toggled.connect(self._on_compat_toggle)
        self.track_list.itemDoubleClicked.connect(self._on_list_double_click)
        self.btn_route.toggled.connect(self._on_route_toggled)
        self.btn_clear_route.clicked.connect(self._clear_highlights)
        self.btn_clear_all.clicked.connect(self._clear_map)
        self.btn_info.toggled.connect(self.toggle_panel_requested.emit)

    # -- population ---------------------------------------------------------
    def ensure_built(self):
        """Populate the track list once (graph is built as tracks are added)."""
        if self._populated:
            return
        self._populated = True
        tracks = self._mapper.to_presentation_list(self.library_service.get_all_tracks())
        analyzable = GraphService.analyzable(tracks)
        analyzable.sort(key=lambda t: str(t.get("title", "")).lower())
        for idx, t in enumerate(analyzable):
            self._track_index[t["id"]] = t
            item = _TrackItem()
            item.default_key = float(idx)
            item.sort_key = float(idx)
            item.setData(_TRACK_ROLE, t)
            item.setData(_ONMAP_ROLE, False)
            item.setData(_ID_ROLE, t["id"])
            self.track_list.addItem(item)
            self._list_items[t["id"]] = item
        self.lbl_stats.setText(f"0 en el mapa · {len(analyzable)} disponibles")

    def _on_compat_toggle(self, on: bool):
        self._compat_only = on
        self._apply_filters()

    def _apply_filters(self):
        """Apply the search text and, when a track is selected and 'Solo
        compatibles' is on, hide tracks that don't mix with it (on-map tracks
        stay visible)."""
        q = self.search.text().strip().lower()
        sel = self._selected_track
        sel_id = sel.get("id") if sel else None
        for tid, item in self._list_items.items():
            t = self._track_index[tid]
            hidden = False
            if q and q not in f"{t.get('title','')} {t.get('artist','')}".lower():
                hidden = True
            if not hidden and self._compat_only and sel and tid != sel_id \
                    and tid not in self._selected_ids:
                if not self._engine.score(sel, t).compatible:
                    hidden = True
            item.setHidden(hidden)

    def _reorder_list_by(self, track: dict):
        """Reorder the track list by transition compatibility with `track`,
        so the best 'next track' candidates bubble to the top."""
        tid = track.get("id")
        for cid, item in self._list_items.items():
            if cid == tid:
                item.sort_key = -1e9  # the selected track itself, on top
                continue
            ts = self._engine.score(track, self._track_index[cid])
            if ts.compatible:
                item.sort_key = -float(ts.score)
            else:
                item.sort_key = 1000.0 + item.default_key
        self.track_list.sortItems(Qt.AscendingOrder)
        self.track_list.scrollToTop()

    def _restore_list_order(self):
        for item in self._list_items.values():
            item.sort_key = item.default_key
        self.track_list.sortItems(Qt.AscendingOrder)

    def _recompute_default_keys(self):
        """Set each item's base sort key from the current sort mode."""
        if self._sort_mode == "alpha":
            ordered = sorted(self._list_items.keys(),
                             key=lambda tid: str(self._track_index[tid].get("title", "")).lower())
            for idx, tid in enumerate(ordered):
                self._list_items[tid].default_key = float(idx)
        else:
            sign = 1.0 if self._sort_mode == "bpm_asc" else -1.0
            for tid, item in self._list_items.items():
                try:
                    bpm = float(self._track_index[tid].get("bpm"))
                except (ValueError, TypeError):
                    bpm = 0.0
                item.default_key = sign * bpm

    def _on_sort_changed(self, *_):
        self._sort_mode = self.sort_combo.currentData()
        self._recompute_default_keys()
        self._restore_list_order()   # honour the chosen sort as the base order
        self._apply_filters()

    # -- add / remove -------------------------------------------------------
    def _on_list_double_click(self, item: QListWidgetItem):
        self._toggle_track(item.data(_ID_ROLE))

    def _toggle_track(self, track_id: str):
        if track_id in self._selected_ids:
            self._selected_ids.remove(track_id)
        else:
            self._selected_ids.append(track_id)
        item = self._list_items.get(track_id)
        if item:
            item.setData(_ONMAP_ROLE, track_id in self._selected_ids)
        self._rebuild_graph()

    def _clear_map(self):
        self._selected_ids.clear()
        self._selected_track = None
        self._set_active = False
        for item in self._list_items.values():
            item.setData(_ONMAP_ROLE, False)
        self._restore_list_order()
        self._apply_filters()
        self._rebuild_graph()

    def _rebuild_graph(self):
        self._route_start = None
        selected = [self._track_index[i] for i in self._selected_ids if i in self._track_index]
        if not selected:
            self.scene.clear()
            self._nodes.clear()
            self._edges.clear()
            self._order_items.clear()
            self._graph = None
            self._reset_set_panel()
            self.stack.setCurrentWidget(self.empty_hint)
            self.lbl_stats.setText(f"0 en el mapa · {len(self._track_index)} disponibles")
            return

        G = self._service.build(selected)
        positions = GraphService.layout(G, self._positions)
        self._positions.update(positions)
        communities = GraphService.communities(G)
        self._graph = G

        # Scale positions so node *density* stays roughly constant regardless of
        # count: few tracks sit close together (not flung to opposite corners),
        # many tracks spread out. spring_layout spacing ~ 1/sqrt(n), so multiply.
        n = G.number_of_nodes()
        self._scale = 90.0 * (n ** 0.5)

        self.scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._order_items.clear()   # scene.clear() already removed them
        for node_id in G.nodes():
            data = G.nodes[node_id]
            color = _COMMUNITY_COLORS[communities.get(node_id, 0) % len(_COMMUNITY_COLORS)]
            node = NodeItem(node_id, data, color, self._on_node_clicked, self._on_node_context)
            node.anchor_role = {i: r for r, i in self._anchors.items()}.get(node_id)
            x, y = self._positions.get(node_id, (0.0, 0.0))
            node.setPos(x * self._scale, y * self._scale)
            self.scene.addItem(node)
            self._nodes[node_id] = node
        for a, b, attrs in G.edges(data=True):
            na, nb = self._nodes.get(a), self._nodes.get(b)
            if not na or not nb:
                continue
            edge = EdgeItem(na, nb, attrs.get("score", 72))
            edge.setToolTip(self._edge_tooltip(na.data, nb.data, attrs))
            na.edges.append(edge)
            nb.edges.append(edge)
            self.scene.addItem(edge)
            self._edges.append(edge)

        self.lbl_stats.setText(
            f"{G.number_of_nodes()} en el mapa · {G.number_of_edges()} transiciones · "
            f"{len(self._track_index)} disponibles"
        )
        self.stack.setCurrentWidget(self.view)
        self._fit_view()

        # Keep the set live: if one was already generated, re-order the new map
        # automatically so the user never has to press "Armar set" again.
        if self._set_active and len(self._selected_ids) >= 2:
            self._on_build_set()
        else:
            self._reset_set_panel()

    @staticmethod
    def _edge_tooltip(a: dict, b: dict, attrs: dict) -> str:
        score = int(attrs.get("score", 0))
        label = ("Excelente" if score >= 90 else "Buena" if score >= 75
                 else "Aceptable" if score >= 60 else "Débil")
        rel = attrs.get("relation") or "—"
        delta = attrs.get("bpm_delta", 0.0) or 0.0
        return (f"<b>{a.get('title','—')} &nbsp;⇄&nbsp; {b.get('title','—')}</b><br>"
                f"{label} · {score}%<br>"
                f"BPM {delta:+.0f} · Camelot {a.get('key','')}→{b.get('key','')} ({rel})")

    def _fit_view(self):
        """Fit the graph in view, but never zoom in past a sensible cap so a
        2-node map lands centred rather than at opposite corners."""
        rect = self.scene.itemsBoundingRect().adjusted(-60, -60, 60, 60)
        vp = self.view.viewport()
        vw = vp.width() if vp.width() > 10 else 900
        vh = vp.height() if vp.height() > 10 else 700
        if rect.width() < 1 or rect.height() < 1:
            zoom = 1.0
        else:
            fit = min(vw / rect.width(), vh / rect.height())
            zoom = min(1.4, max(0.12, fit))
        self.view.resetTransform()
        self.view.scale(zoom, zoom)
        self.view.centerOn(rect.center())

    # -- interaction --------------------------------------------------------
    def _on_node_clicked(self, node_id: str):
        if self._route_mode:
            self._handle_route_click(node_id)
            return
        self._highlight_selection(node_id)
        node = self._nodes.get(node_id)
        if node:
            self.track_selected.emit(dict(node.data))
            self._selected_track = node.data
            # In A-Z mode, bubble compatible tracks to the top; when the user has
            # chosen a BPM sort, keep that order (just filter to compatibles).
            if self._sort_mode == "alpha":
                self._reorder_list_by(node.data)
            self._apply_filters()

    def _highlight_selection(self, node_id: str):
        neighbors = set(self._graph.neighbors(node_id)) if self._graph else set()
        for e in self._edges:
            e.set_state("active" if node_id in (e.src.node_id, e.dst.node_id) else "dim")
        for nid, node in self._nodes.items():
            if nid == node_id:
                node.set_state("selected")
            elif nid in neighbors:
                node.set_state("normal")
            else:
                node.set_state("dim")

    def _clear_highlights(self):
        for e in self._edges:
            e.set_state("normal")
        for n in self._nodes.values():
            n.set_state("normal")
        self._route_start = None
        self._selected_track = None
        self._restore_list_order()
        self._apply_filters()

    def _on_route_toggled(self, on: bool):
        self._route_mode = on
        self._route_start = None
        if on:
            self._clear_highlights()

    def _handle_route_click(self, node_id: str):
        if self._route_start is None:
            self._clear_highlights()
            self._route_start = node_id
            self._nodes[node_id].set_state("selected")
            return
        path = GraphService.shortest_path(self._graph, self._route_start, node_id)
        self._route_start = None
        if not path:
            self._clear_highlights()
            return
        self._draw_route(path)

    def _draw_route(self, path: List[str]):
        path_set = set(path)
        path_pairs = set(zip(path, path[1:])) | set(zip(path[1:], path))
        for e in self._edges:
            e.set_state("path" if (e.src.node_id, e.dst.node_id) in path_pairs else "dim")
        for nid, node in self._nodes.items():
            node.set_state("path" if nid in path_set else "dim")

    # -- set builder --------------------------------------------------------
    def _current_curve_points(self):
        return self._custom_curve if self.event_combo.currentData() == "custom" else None

    def _on_event_changed(self, *_):
        is_custom = self.event_combo.currentData() == "custom"
        self.btn_edit_curve.setVisible(is_custom)
        if is_custom and self._custom_curve is None:
            self._open_journey()
            return
        if self._set_active and len(self._selected_ids) >= 2:
            self._on_build_set()

    def _open_journey(self):
        from ui.dialogs.journey_dialog import JourneyDialog  # noqa: PLC0415
        dlg = JourneyDialog(self._custom_curve, self)
        if dlg.exec():
            self._custom_curve = dlg.get_curve()
        elif self._custom_curve is None:
            from services.set_builder_service import energy_target  # noqa: PLC0415
            self._custom_curve = [energy_target("club", i / 7) for i in range(8)]
        if self._set_active and len(self._selected_ids) >= 2:
            self._on_build_set()

    def _on_build_set(self):
        if len(self._selected_ids) < 2:
            return
        self._set_active = True
        selected = [self._track_index[i] for i in self._selected_ids if i in self._track_index]
        event = self.event_combo.currentData()
        lam = self.lam_slider.value() / 100.0
        gs = self._set_builder.build_set(selected, event=event, lam=lam,
                                         anchors=self._anchors,
                                         curve_points=self._current_curve_points())
        self._current_set = gs
        self._draw_order_overlay(gs)
        self._populate_set_panel(gs)
        self._update_set_label(gs)
        self.set_panel.setVisible(True)

    def _on_lambda_changed(self):
        if self._current_set is not None and len(self._selected_ids) >= 2:
            self._on_build_set()

    def _on_export(self):
        from PySide6.QtWidgets import QMenu, QFileDialog, QMessageBox  # noqa: PLC0415
        if not self._current_set or not self._current_set.steps:
            QMessageBox.information(self, "WaveLoad", "Primero armá un set para exportar.")
            return
        menu = QMenu()
        a_m3u = menu.addAction("Exportar a M3U8")
        a_rb = menu.addAction("Exportar a rekordbox XML")
        act = menu.exec(self.btn_export.mapToGlobal(self.btn_export.rect().topLeft()))
        if act is None:
            return
        steps = self._current_set.steps
        if act == a_m3u:
            content = build_m3u8(steps)
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar set", "WaveLoad set.m3u8", "Playlist M3U8 (*.m3u8)")
        else:
            content = build_rekordbox_xml(steps, "WaveLoad Set")
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar set", "WaveLoad set.xml", "rekordbox XML (*.xml)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "WaveLoad", f"Set exportado ({len(steps)} pistas).")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "WaveLoad", f"No se pudo exportar:\n{e}")

    def _on_node_context(self, node_id: str, screen_pos):
        from PySide6.QtWidgets import QMenu  # noqa: PLC0415
        menu = QMenu()
        a_start = menu.addAction("Fijar como apertura")
        a_end = menu.addAction("Fijar como cierre")
        a_peak = menu.addAction("Fijar como pico")
        menu.addSeparator()
        a_clear = menu.addAction("Quitar ancla")
        act = menu.exec(screen_pos)
        if act == a_start:
            self._set_anchor("start", node_id)
        elif act == a_end:
            self._set_anchor("end", node_id)
        elif act == a_peak:
            self._set_anchor("peak", node_id)
        elif act == a_clear:
            self._clear_anchor(node_id)

    def _set_anchor(self, role: str, node_id: str):
        self._anchors = {r: i for r, i in self._anchors.items() if i != node_id}
        self._anchors[role] = node_id
        self._refresh_anchor_markers()
        if self._current_set is not None:
            self._on_build_set()

    def _clear_anchor(self, node_id: str):
        self._anchors = {r: i for r, i in self._anchors.items() if i != node_id}
        self._refresh_anchor_markers()
        if self._current_set is not None:
            self._on_build_set()

    def _refresh_anchor_markers(self):
        role_of = {i: r for r, i in self._anchors.items()}
        for nid, node in self._nodes.items():
            node.anchor_role = role_of.get(nid)
            node.update()

    def _reset_set_panel(self):
        self.set_list.clear()
        self.set_panel.setVisible(False)
        self._current_set = None

    def _clear_order_visuals(self):
        """Remove the route lines and clear per-node order numbers/badges."""
        for it in self._order_items:
            try:
                self.scene.removeItem(it)
            except Exception:
                pass
        self._order_items.clear()
        for n in self._nodes.values():
            n.order_number = None
            n.order_edges = []
            n.update()

    def _clear_order(self):
        self._clear_order_visuals()
        self._reset_set_panel()

    def _draw_order_overlay(self, gs):
        """(Re)draw the numbered route over the graph. Numbers are painted by the
        nodes and lines follow their nodes, so it all stays intact when dragged."""
        self._clear_order_visuals()
        nodes = [self._nodes.get(s.track["id"]) for s in gs.steps]
        nodes = [n for n in nodes if n]
        for pos, n in enumerate(nodes, start=1):
            n.order_number = pos
            n.update()
        for a, b in zip(nodes, nodes[1:]):
            line = OrderLineItem(a, b)
            self.scene.addItem(line)
            self._order_items.append(line)
            a.order_edges.append(line)
            b.order_edges.append(line)

    def _update_set_label(self, gs):
        self.lbl_set.setText(
            f"Set sugerido · {EVENT_PRESETS.get(gs.event, gs.event)} · "
            f"calidad {gs.avg_quality}% · curva {gs.curve_fit}%"
        )

    def _populate_set_panel(self, gs):
        self.set_list.clear()
        for step in gs.steps:
            it = QListWidgetItem()
            it.setData(_STEP_ID, step.track.get("id"))
            it.setData(_STEP_WARN, "\n".join(step.warnings))
            it.setToolTip("\n".join(step.warnings))
            self.set_list.addItem(it)

    def _on_steps_reordered(self):
        """User dragged a card: re-evaluate the manual order and refresh."""
        ids = [self.set_list.item(i).data(_STEP_ID) for i in range(self.set_list.count())]
        ordered = [self._track_index[i] for i in ids if i in self._track_index]
        if len(ordered) < 2:
            return
        gs = self._set_builder._evaluate(ordered, self.event_combo.currentData(),
                                         self._current_curve_points())
        self._current_set = gs
        for i, step in enumerate(gs.steps):
            it = self.set_list.item(i)
            if it:
                it.setData(_STEP_WARN, "\n".join(step.warnings))
                it.setToolTip("\n".join(step.warnings))
        self.set_list.viewport().update()
        self._draw_order_overlay(gs)
        self._update_set_label(gs)
