"""
ui/shell/bottom_workspace.py
============================
Bottom workspace for WaveLoad 5.
Architectural slot for the future Set Workspace.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from ui.theme.spacing import BOTTOM_WORKSPACE_COLLAPSED_HEIGHT


class BottomWorkspace(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_bottomWorkspace")
        # Collapsed by default
        self.setFixedHeight(BOTTOM_WORKSPACE_COLLAPSED_HEIGHT)
        self.setVisible(False)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        label = QLabel("Set Workspace — Coming Soon")
        label.setObjectName("wl_contextSubtitle")
        layout.addWidget(label)

    def expand(self):
        self.setVisible(True)
        self.setMinimumHeight(200)

    def collapse(self):
        self.setVisible(False)
        self.setFixedHeight(BOTTOM_WORKSPACE_COLLAPSED_HEIGHT)
