"""
ui/components/cards.py
======================
Reusable card containers for WaveLoad 5.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from ui.theme.styles import component_styles


class WLCard(QWidget):
    """
    Base elevated card container.
    Used for panels, summaries, or grouping content.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_downloadCard")  # Reusing the card style base
        # To avoid duplicating too much in the global sheet, if it needs
        # exact download card styling, it gets that objectName.
        # Otherwise, we might define a generic wl_card in styles.py.
        # For now, we apply the component-specific style directly if needed,
        # or rely on the global sheet if defined there.
        self.setStyleSheet(component_styles.download_card())

        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(12, 12, 12, 12)
        self.card_layout.setSpacing(8)

    def add_widget(self, widget: QWidget):
        self.card_layout.addWidget(widget)

    def add_layout(self, layout):
        self.card_layout.addLayout(layout)


class WLMetricCard(QWidget):
    """
    A small card displaying a large number and a label.
    Used in the summary view.
    """
    def __init__(self, title: str, value: str, icon: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("wl_metricBox")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(4)

        if icon:
            self.icon_label = QLabel(icon)
            self.icon_label.setAlignment(Qt.AlignCenter)
            self.icon_label.setStyleSheet("font-size: 20px;")
            layout.addWidget(self.icon_label)

        self.value_label = QLabel(value)
        self.value_label.setAlignment(Qt.AlignCenter)
        # Note: styling for values usually depends on success/fail context.
        # We leave objectName blank and expect caller to set it or setStyleSheet.
        layout.addWidget(self.value_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("wl_metricLabel")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_value_object_name(self, name: str):
        """Allows setting the object name for the value label (e.g. wl_successValue)"""
        self.value_label.setObjectName(name)
        self.style().unpolish(self.value_label)
        self.style().polish(self.value_label)
