"""
ui/shell/toolbar.py
===================
Top toolbar for WaveLoad 5.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from ui.theme.spacing import TOOLBAR_HEIGHT, MARGINS_TIGHT
from ui.theme.icons import Icons
from ui.components.inputs import WLSearchInput
from ui.components.buttons import WLIconButton, WLPrimaryButton


from ui.theme.colors import TEXT_SECONDARY

class Toolbar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_toolbar")
        self.setFixedHeight(TOOLBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(*MARGINS_TIGHT)
        layout.setSpacing(12)

        # Brand / Title (optional if Logo is in sidebar, but good for window drag area)
        self.brand_label = QLabel("WaveLoad")
        self.brand_label.setStyleSheet(f"font-weight: 700; color: {TEXT_SECONDARY}; padding-left: 8px;")

        # Search bar (stub)
        self.search_input = WLSearchInput()
        self.search_input.setFixedWidth(300)

        # Tools
        self.import_btn = WLPrimaryButton(f"{Icons.IMPORT} Importar")
        self.import_btn.setFixedHeight(32)  # smaller than default primary
        
        self.settings_btn = WLIconButton(Icons.SETTINGS)
        self.settings_btn.setToolTip("Ajustes")

        layout.addWidget(self.brand_label)
        layout.addStretch()
        layout.addWidget(self.search_input)
        layout.addStretch()
        layout.addWidget(self.import_btn)
        layout.addWidget(self.settings_btn)
