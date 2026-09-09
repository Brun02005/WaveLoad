"""
ui/workspaces/base_workspace.py
===============================
Abstract base class for all module workspaces in WaveLoad 5.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal


class BaseWorkspace(QWidget):
    """
    Base class for a module workspace (Downloads, Library, Settings, etc.).
    """
    # Emitted when the workspace wants to update the context panel
    # The payload is a dictionary of metadata to display.
    context_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        
    def activate(self):
        """Called when this workspace becomes the visible one."""
        pass

    def deactivate(self):
        """Called when the user navigates away from this workspace."""
        pass
