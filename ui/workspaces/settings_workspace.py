"""
ui/workspaces/settings_workspace.py
===================================
Settings workspace for WaveLoad 5.
Wraps the existing SettingsPage widget.
"""

from PySide6.QtWidgets import QVBoxLayout

from ui.workspaces.base_workspace import BaseWorkspace
from ui.settings_page import SettingsPage


class SettingsWorkspace(BaseWorkspace):
    def __init__(self, settings_page: SettingsPage, parent=None):
        super().__init__(parent)
        self.settings_page = settings_page
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.settings_page)
