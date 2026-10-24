"""
ui/components/buttons.py
========================
Reusable button components for WaveLoad.
Styled automatically via the global stylesheet using object names.

Todos aceptan ``icon=`` con un nombre de ``ui.theme.icons.Icons``: el icono se
pinta en el color que corresponde a la variante del botón, no en el del emoji.
"""

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from ui.theme.colors import (
    ACCENT, PRIMARY_RED, TEXT_INVERSE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.theme.icons import icon as make_icon, icon_size, is_icon


def _set_icon(button: QPushButton, name, color: str, size: int = 16):
    if name and is_icon(name):
        button.setIcon(make_icon(name, color, size, TEXT_MUTED))
        button.setIconSize(icon_size(size))


class WLPrimaryButton(QPushButton):
    """
    High-emphasis call-to-action button (accent).
    Used for Start Download, Import, etc.
    """
    def __init__(self, text: str = "", parent=None, icon=None, height: int = 40):
        super().__init__(text, parent)
        self.setObjectName("wl_primaryBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(height)
        _set_icon(self, icon, TEXT_INVERSE)


class WLSecondaryButton(QPushButton):
    """
    Medium-emphasis button.
    Used for secondary actions like Paste, Clear, Open Folder.
    """
    def __init__(self, text: str = "", parent=None, icon=None):
        super().__init__(text, parent)
        self.setObjectName("wl_secondaryBtn")
        self.setCursor(Qt.PointingHandCursor)
        _set_icon(self, icon, TEXT_SECONDARY)


class WLGhostButton(QPushButton):
    """Botón sin fondo ni borde: acciones terciarias que no deben competir."""
    def __init__(self, text: str = "", parent=None, icon=None):
        super().__init__(text, parent)
        self.setObjectName("wl_ghostBtn")
        self.setCursor(Qt.PointingHandCursor)
        _set_icon(self, icon, TEXT_SECONDARY)


class WLDangerButton(QPushButton):
    """
    Destructive action button (red).
    Used for Cancel, Delete, etc.
    """
    def __init__(self, text: str = "", parent=None, icon=None):
        super().__init__(text, parent)
        self.setObjectName("wl_dangerBtn")
        self.setCursor(Qt.PointingHandCursor)
        _set_icon(self, icon, PRIMARY_RED)


class WLIconButton(QPushButton):
    """
    Square, icon-only button for toolbars and tight spaces.

    ``icon_name`` es un nombre de ``Icons``. Si no lo es se muestra como texto,
    para no romper a quien todavía pase un carácter.
    """
    def __init__(self, icon_name: str = "", parent=None, tooltip: str = "",
                 size: int = 32, icon_px: int = 18, color: str = TEXT_SECONDARY):
        super().__init__(parent)
        self.setObjectName("wl_toolbarBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(size, size)
        self._icon_px = icon_px
        self._color = color
        if tooltip:
            self.setToolTip(tooltip)
        self.set_icon(icon_name)

    def set_icon(self, name: str, color: str | None = None):
        if is_icon(name):
            self.setText("")
            _set_icon(self, name, color or self._color, self._icon_px)
        else:
            self.setIcon(QIcon())
            self.setText(name)


class WLNavButton(QPushButton):
    """
    Sidebar navigation button with an active state toggle.
    """
    def __init__(self, text: str = "", parent=None, icon=None):
        super().__init__(text, parent)
        self.setObjectName("wl_navBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self._icon_name = icon
        self._is_active = False
        self._refresh_icon()

    def _refresh_icon(self):
        _set_icon(self, self._icon_name, ACCENT if self._is_active else TEXT_SECONDARY, 18)

    def set_active(self, active: bool):
        """Toggle the active visual state of the nav button."""
        self._is_active = active
        self.setObjectName("wl_navBtnActive" if active else "wl_navBtn")
        self._refresh_icon()
        # Force a style re-evaluation
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def is_active(self) -> bool:
        return self._is_active

    def enterEvent(self, event):
        if not self._is_active:
            _set_icon(self, self._icon_name, TEXT_PRIMARY, 18)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._refresh_icon()
        super().leaveEvent(event)
