from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
from PySide6.QtCore import Qt, Signal

from ui.theme.colors import SURFACE_2, SURFACE_4, BORDER_DEFAULT, BORDER_STRONG, TEXT_SECONDARY

class CollapsibleDetails(QWidget):
    def __init__(self, title="Mostrar detalles técnicos", parent=None):
        super().__init__(parent)
        self.expanded = False
        self.title_text = title

        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Botón de cabecera (Header button)
        self.header_btn = QPushButton()
        self.header_btn.setCheckable(True)
        self.header_btn.setCursor(Qt.PointingHandCursor)
        self.header_btn.setObjectName("collapsibleHeader")
        self.header_btn.setFixedHeight(36)

        header_layout = QHBoxLayout(self.header_btn)
        header_layout.setContentsMargins(10, 0, 10, 0)
        header_layout.setSpacing(6)

        self.arrow_label = QLabel("▶")
        self.arrow_label.setObjectName("arrowLabel")
        self.arrow_label.setFixedWidth(12)

        self.text_label = QLabel(self.title_text)
        self.text_label.setObjectName("headerText")

        header_layout.addWidget(self.arrow_label)
        header_layout.addWidget(self.text_label)
        header_layout.addStretch()

        self.header_btn.clicked.connect(self.toggle_collapse)

        # Contenedor del contenido (Content drawer)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 8, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_widget.setVisible(False)

        self.main_layout.addWidget(self.header_btn)
        self.main_layout.addWidget(self.content_widget)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QPushButton#collapsibleHeader {{
                background-color: {SURFACE_2};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
                text-align: left;
            }}
            QPushButton#collapsibleHeader:hover {{
                background-color: {SURFACE_4};
                border-color: {BORDER_STRONG};
            }}
            QLabel#arrowLabel {{
                color: {TEXT_SECONDARY};
                font-size: 10px;
                font-weight: bold;
            }}
            QLabel#headerText {{
                color: {TEXT_SECONDARY};
                font-size: 12px;
                font-weight: 600;
            }}
        """)

    def add_content(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def toggle_collapse(self):
        self.expanded = not self.expanded
        self.content_widget.setVisible(self.expanded)
        
        if self.expanded:
            self.arrow_label.setText("▼")
            self.text_label.setText("Ocultar detalles técnicos")
        else:
            self.arrow_label.setText("▶")
            self.text_label.setText(self.title_text)
            
        self.header_btn.setChecked(self.expanded)
