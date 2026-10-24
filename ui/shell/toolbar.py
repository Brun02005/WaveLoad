"""
ui/shell/toolbar.py
===================
Top toolbar for WaveLoad.

La marca vive en el sidebar; acá va el nombre de la sección abierta, la
búsqueda y la acción global de importar. Ajustes no se repite: ya está en la
navegación.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from ui.theme.spacing import TOOLBAR_HEIGHT
from ui.theme.icons import Icons
from ui.components.inputs import WLSearchInput
from ui.components.buttons import WLSecondaryButton


class Toolbar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_toolbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(TOOLBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 16, 0)
        layout.setSpacing(10)

        self.title_label = QLabel("")
        self.title_label.setObjectName("wl_toolbarTitle")

        self.search_input = WLSearchInput()
        self.search_input.setFixedWidth(320)

        self.import_btn = WLSecondaryButton("Importar música", icon=Icons.IMPORT)
        self.import_btn.setFixedHeight(34)

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.search_input)
        layout.addWidget(self.import_btn)

    def set_title(self, text: str):
        self.title_label.setText(text)
