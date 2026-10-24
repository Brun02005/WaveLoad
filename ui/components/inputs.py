"""
ui/components/inputs.py
=======================
Reusable input components for WaveLoad.
"""

from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

from ui.theme.colors import TEXT_MUTED
from ui.theme.icons import Icons, icon


class WLSearchInput(QLineEdit):
    """
    Search bar with a leading search icon.
    Used in the top toolbar.
    """
    def __init__(self, parent=None, placeholder: str = "Buscar en la librería"):
        super().__init__(parent)
        self.setObjectName("wl_searchInput")
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(34)
        self.setClearButtonEnabled(True)
        self.addAction(icon(Icons.SEARCH, TEXT_MUTED, 16), QLineEdit.LeadingPosition)


class WLTextArea(QPlainTextEdit):
    """
    Multi-line text area.
    Used for URL input box, log box, etc.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_inputBox")
