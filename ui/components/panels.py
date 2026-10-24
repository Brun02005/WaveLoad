"""
ui/components/panels.py
=======================
Panel and layout components for WaveLoad 5.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt

from ui.theme.colors import TEXT_SECONDARY
from ui.theme.icons import Icons, pixmap


class WLCollapsiblePanel(QWidget):
    """
    A generic collapsible panel with a header button and a content drawer.
    Replaces the legacy CollapsibleDetails.
    """
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.expanded = False
        self.title_text = title

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Header button
        self.header_btn = QPushButton()
        self.header_btn.setCheckable(True)
        self.header_btn.setCursor(Qt.PointingHandCursor)
        self.header_btn.setObjectName("wl_collapsibleHeader")
        self.header_btn.setFixedHeight(36)

        header_layout = QHBoxLayout(self.header_btn)
        header_layout.setContentsMargins(10, 0, 10, 0)
        header_layout.setSpacing(6)

        self.arrow_label = QLabel()
        self.arrow_label.setObjectName("wl_arrowLabel")
        self.arrow_label.setFixedWidth(14)
        self.arrow_label.setPixmap(pixmap(Icons.ARROW_RIGHT, 14, TEXT_SECONDARY))

        self.text_label = QLabel(self.title_text)
        self.text_label.setObjectName("wl_headerText")

        header_layout.addWidget(self.arrow_label)
        header_layout.addWidget(self.text_label)
        header_layout.addStretch()

        self.header_btn.clicked.connect(self.toggle_collapse)

        # Content drawer
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 8, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_widget.setVisible(False)

        self.main_layout.addWidget(self.header_btn)
        self.main_layout.addWidget(self.content_widget)

    def add_content(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def toggle_collapse(self):
        self.expanded = not self.expanded
        self.content_widget.setVisible(self.expanded)
        
        arrow = Icons.ARROW_DOWN if self.expanded else Icons.ARROW_RIGHT
        self.arrow_label.setPixmap(pixmap(arrow, 14, TEXT_SECONDARY))
            
        self.header_btn.setChecked(self.expanded)


class WLInfoRow(QWidget):
    """
    A horizontal row showing a Label: Value pair.
    Used in the context panel for metadata display.
    """
    def __init__(self, label: str, value: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label_widget = QLabel(label.rstrip(":"))
        self.label_widget.setObjectName("wl_infoLabel")
        self.label_widget.setFixedWidth(84)
        
        self.value_widget = QLabel(value)
        self.value_widget.setObjectName("wl_infoValue")
        self.value_widget.setWordWrap(True)

        # Label usually gets a fixed width or layout stretch to align properly
        # For a simple row, we just put them side by side.
        layout.addWidget(self.label_widget)
        layout.addWidget(self.value_widget, 1)

    def set_value(self, value: str):
        self.value_widget.setText(value)
