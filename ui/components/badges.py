"""
ui/components/badges.py
=======================
Indicator badges for WaveLoad 5.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt


class WLStatusBadge(QWidget):
    """
    A small circular LED-style indicator for status (valid, error, pending).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.set_status("pending")

    def set_status(self, status: str, tooltip: str = ""):
        """
        Set the visual status of the badge.
        Args:
            status: 'valid', 'error', 'duplicate', or 'pending'
        """
        if status == "valid":
            self.setObjectName("wl_statusValid")
        elif status == "error":
            self.setObjectName("wl_statusError")
        elif status == "duplicate":
            self.setObjectName("wl_statusDuplicate")
        else:
            self.setObjectName("wl_statusPending")
            
        if tooltip:
            self.setToolTip(tooltip)
            
        # Force style update
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
