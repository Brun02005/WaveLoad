"""
ui/dialogs/journey_dialog.py
============================
Journey Designer — draw your own energy curve for the set. A small editor with
draggable control points (X = time through the set, Y = energy). The resulting
curve (list of 0..1 values) feeds SetBuilderService as a custom target.
"""

from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont

from ui.theme.colors import ACCENT, SURFACE_BASE, BORDER_DEFAULT, TEXT_MUTED
from ui.components.buttons import WLSecondaryButton
from services.set_builder_service import EVENT_PRESETS, energy_target

_DEFAULT_CURVE = [0.30, 0.45, 0.60, 0.78, 0.90, 0.92, 0.80, 0.55]
_MARGIN = 22


class CurveEditor(QWidget):
    changed = Signal()

    def __init__(self, points: Optional[List[float]] = None, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 180)
        self._points = list(points) if points else list(_DEFAULT_CURVE)
        self._drag = None

    def get_curve(self) -> List[float]:
        return list(self._points)

    def set_curve(self, points: List[float]):
        self._points = list(points)
        self.update()
        self.changed.emit()

    # -- geometry helpers ---------------------------------------------------
    def _x(self, i: int) -> float:
        w = self.width() - 2 * _MARGIN
        return _MARGIN + w * i / (len(self._points) - 1)

    def _y(self, v: float) -> float:
        h = self.height() - 2 * _MARGIN
        return _MARGIN + h * (1.0 - v)

    def _v_from_y(self, py: float) -> float:
        h = self.height() - 2 * _MARGIN
        return max(0.0, min(1.0, 1.0 - (py - _MARGIN) / h))

    # -- painting -----------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        p.fillRect(rect, QColor(SURFACE_BASE))
        # grid
        p.setPen(QPen(QColor(BORDER_DEFAULT), 0.5))
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = self._y(f)
            p.drawLine(int(_MARGIN), int(y), int(self.width() - _MARGIN), int(y))
        p.setPen(QColor(TEXT_MUTED))
        f = QFont(); f.setPixelSize(9); p.setFont(f)
        p.drawText(QRectF(2, self._y(1.0) - 7, _MARGIN - 2, 14), Qt.AlignRight | Qt.AlignVCenter, "alta")
        p.drawText(QRectF(2, self._y(0.0) - 7, _MARGIN - 2, 14), Qt.AlignRight | Qt.AlignVCenter, "baja")

        pts = [QPointF(self._x(i), self._y(v)) for i, v in enumerate(self._points)]
        # filled area under the curve
        area = QPolygonF([QPointF(pts[0].x(), self._y(0.0))] + pts +
                         [QPointF(pts[-1].x(), self._y(0.0))])
        fill = QColor(ACCENT); fill.setAlphaF(0.14)
        p.setPen(Qt.NoPen); p.setBrush(fill)
        p.drawPolygon(area)
        # curve line
        p.setPen(QPen(QColor(ACCENT), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF(pts))
        # control points
        for pt in pts:
            p.setBrush(QColor(ACCENT)); p.setPen(QPen(QColor(SURFACE_BASE), 1.5))
            p.drawEllipse(pt, 5, 5)
        p.end()

    # -- interaction --------------------------------------------------------
    def _nearest(self, pos) -> Optional[int]:
        for i in range(len(self._points)):
            if abs(pos.x() - self._x(i)) < 16:
                return i
        return None

    def mousePressEvent(self, e):
        self._drag = self._nearest(e.position())
        if self._drag is not None:
            self._points[self._drag] = self._v_from_y(e.position().y())
            self.update(); self.changed.emit()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self._points[self._drag] = self._v_from_y(e.position().y())
            self.update(); self.changed.emit()

    def mouseReleaseEvent(self, e):
        self._drag = None


class JourneyDialog(QDialog):
    def __init__(self, initial: Optional[List[float]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Journey Designer")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Dibujá la curva de energía de tu set — arrastrá los puntos"))
        self.editor = CurveEditor(initial)
        lay.addWidget(self.editor)

        row = QLabel("Empezar desde un preset:")
        row.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        lay.addWidget(row)
        presets = QHBoxLayout()
        for key, label in EVENT_PRESETS.items():
            b = WLSecondaryButton(label)
            b.clicked.connect(lambda _=False, k=key: self._load_preset(k))
            presets.addWidget(b)
        lay.addLayout(presets)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _load_preset(self, key: str):
        n = len(self.editor.get_curve())
        self.editor.set_curve([energy_target(key, i / (n - 1)) for i in range(n)])

    def get_curve(self) -> List[float]:
        return self.editor.get_curve()
