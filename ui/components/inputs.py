"""
ui/components/inputs.py
=======================
Reusable input components for WaveLoad 5.
"""

from PySide6.QtWidgets import QLineEdit, QPlainTextEdit


class WLSearchInput(QLineEdit):
    """
    Search bar with icon placeholder.
    Used in the top toolbar.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_searchInput")
        self.setPlaceholderText(" Buscar...")
        self.setFixedHeight(36)
        # Note: A proper search icon inside the QLineEdit usually requires
        # a QAction or custom painting. The placeholder text emoji is a start.


class WLTextArea(QPlainTextEdit):
    """
    Multi-line text area.
    Used for URL input box, log box, etc.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_inputBox")
