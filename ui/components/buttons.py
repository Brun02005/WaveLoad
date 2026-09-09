"""
ui/components/buttons.py
========================
Reusable button components for WaveLoad 5.
Styled automatically via the global stylesheet using object names.
"""

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt


class WLPrimaryButton(QPushButton):
    """
    High-emphasis call-to-action button (green).
    Used for Start Download, Import, etc.
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("wl_primaryBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(46)


class WLSecondaryButton(QPushButton):
    """
    Medium-emphasis button.
    Used for secondary actions like Paste, Clear, Open Folder.
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("wl_secondaryBtn")
        self.setCursor(Qt.PointingHandCursor)


class WLDangerButton(QPushButton):
    """
    Destructive action button (red).
    Used for Cancel, Delete, etc.
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("wl_dangerBtn")
        self.setCursor(Qt.PointingHandCursor)


class WLIconButton(QPushButton):
    """
    Square, icon-only button for toolbars and tight spaces.
    """
    def __init__(self, icon_text: str = "", parent=None):
        super().__init__(icon_text, parent)
        self.setObjectName("wl_toolbarBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(32, 32)
        # Optional: could enforce font size here if needed


class WLNavButton(QPushButton):
    """
    Sidebar navigation button with an active state toggle.
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("wl_navBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self._is_active = False

    def set_active(self, active: bool):
        """Toggle the active visual state of the nav button."""
        self._is_active = active
        self.setObjectName("wl_navBtnActive" if active else "wl_navBtn")
        # Force a style re-evaluation
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def is_active(self) -> bool:
        return self._is_active
