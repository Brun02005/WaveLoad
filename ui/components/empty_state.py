"""
ui/components/empty_state.py
============================
El estado vacío de una pantalla: un icono contenido, un título, una línea de
explicación y, si corresponde, la acción que lo resuelve.

Es una sola pieza para que todas las pantallas vacías se vean iguales; antes
cada una armaba la suya con un emoji de 64 px.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.components.buttons import WLPrimaryButton
from ui.theme.colors import SURFACE_3, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from ui.theme.icons import pixmap


class WLEmptyState(QWidget):
    def __init__(self, icon: str, title: str, subtitle: str = "",
                 action_text: str = "", action_icon: str | None = None,
                 text_width: int = 400, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(0)
        layout.addStretch()

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(56, 56)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet(f"background-color: {SURFACE_3}; border-radius: 14px;")
        self.set_icon(icon)
        layout.addWidget(self.icon_label, 0, Qt.AlignHCenter)
        layout.addSpacing(18)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {TEXT_PRIMARY};")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setFixedWidth(text_width)
        self.subtitle_label.setStyleSheet(f"color: {TEXT_SECONDARY}; line-height: 140%;")
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addSpacing(6)
        layout.addWidget(self.subtitle_label, 0, Qt.AlignHCenter)

        self.action_btn = None
        if action_text:
            layout.addSpacing(20)
            self.action_btn = WLPrimaryButton(action_text, icon=action_icon, height=36)
            layout.addWidget(self.action_btn, 0, Qt.AlignHCenter)

        layout.addStretch()

    def set_icon(self, name: str, color: str = TEXT_MUTED):
        self.icon_label.setPixmap(pixmap(name, 24, color))

    def set_text(self, title: str, subtitle: str = ""):
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))
