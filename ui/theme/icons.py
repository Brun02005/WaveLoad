"""
ui/theme/icons.py
=================
WaveLoad Design System — Iconos

Un set propio de iconos lineales en SVG (grilla de 24 px, trazo de 1,75 px,
extremos redondeados), dibujados para que convivan con Inter. Reemplazan a los
emoji: un emoji se dibuja con la fuente de color del sistema, cambia según la
versión de Windows y no se puede teñir, así que nunca combina con la interfaz.

Cada icono se pinta en el color que se pida y se cachea por (nombre, color,
tamaño). Los consumidores no conocen el SVG: piden un nombre de ``Icons``.

Uso:
    from ui.theme.icons import Icons, icon, pixmap
    button.setIcon(icon(Icons.DOWNLOAD))
    label.setPixmap(pixmap(Icons.SUCCESS, 16, STATUS_VALID))
"""

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ui.theme.colors import TEXT_SECONDARY


class Icons:
    """Nombres de iconos. Son claves de ``_PATHS``, no glifos."""

    # Navegación
    APP_LOGO = "logo"
    DOWNLOAD = "download"
    LIBRARY = "library"
    GRAPH = "graph"
    COLLECTIONS = "layers"
    SETTINGS = "sliders"
    SEARCH = "search"
    IMPORT = "folder-in"

    # Acciones
    START = "download"
    CANCEL = "stop"
    DELETE = "close"
    CLOSE = "close"
    PASTE = "clipboard"
    CLEAR = "trash"
    OPEN_FOLDER = "folder"
    FOLDER = "folder"
    NEW_BATCH = "plus"
    PLUS = "plus"
    REFRESH = "refresh"
    FILE = "file"
    EDIT = "edit"
    DUPLICATE = "copy"
    CRATE = "crate"
    EXPORT = "export"
    ROUTE = "route"
    PANEL = "panel"
    SET = "list"

    # Estado
    SUCCESS = "check-circle"
    ERROR = "x-circle"
    WARNING = "alert"
    PENDING = "clock"
    DOWNLOADING = "download"
    CONVERTING = "zap"
    COMPLETED = "check-circle"
    CANCELLED = "stop"
    FAILED = "x-circle"
    CHECK = "check"
    INFO = "info"

    # Medios
    TRACK = "music"
    VIDEO = "video"
    PLAYLIST = "list"
    TIMER = "clock"
    PLAY = "play"
    PAUSE = "pause"
    VOLUME = "volume"
    VOLUME_OFF = "volume-off"

    # Flechas
    ARROW_RIGHT = "chevron-right"
    ARROW_DOWN = "chevron-down"
    ARROW_LEFT = "chevron-left"
    ARROW_UP = "chevron-up"
    MOVE_UP = "arrow-up"
    MOVE_DOWN = "arrow-down"

    # Varios
    SPEED = "zap"
    ETA = "clock"
    BATCH_FINISHED = "flag"
    EYE = "eye"
    EYE_OFF = "eye-off"


_CIRCLE = '<circle cx="12" cy="12" r="9"/>'
_FOLDER = (
    '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2h8.5A1.5 1.5 0 0 1 21 9.5v8'
    'A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/>'
)

# El cuerpo de cada SVG. Heredan stroke, ancho y extremos del <svg> raíz; los
# que llevan relleno lo piden con fill="currentColor".
_PATHS: dict[str, str] = {
    "logo": '<path stroke-width="2.2" d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "library": '<path d="M4 4v16M8 8v12M12 6v14M16 6l4 14"/>',
    "graph": (
        '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="8" r="2.5"/>'
        '<circle cx="10" cy="18" r="2.5"/>'
        '<path d="M8.5 6.4l7 1.2M6.8 8.4l2.4 7.2M16.4 10l-4.8 6"/>'
    ),
    "layers": '<path d="M12 3l9 4.5-9 4.5-9-4.5z"/><path d="M3 12l9 4.5 9-4.5M3 16.5l9 4.5 9-4.5"/>',
    "sliders": (
        '<path d="M4 7h9M19 7h1M4 17h1M11 17h9"/>'
        '<circle cx="16" cy="7" r="2.5"/><circle cx="8" cy="17" r="2.5"/>'
    ),
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.4-4.4"/>',
    "folder": _FOLDER,
    "folder-in": _FOLDER + '<path d="M12 11v5M9.5 13.5l2.5 2.5 2.5-2.5"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "clipboard": (
        '<rect x="8.5" y="3" width="7" height="4" rx="1"/>'
        '<path d="M15.5 5H17a1.5 1.5 0 0 1 1.5 1.5v13A1.5 1.5 0 0 1 17 21H7'
        'a1.5 1.5 0 0 1-1.5-1.5v-13A1.5 1.5 0 0 1 7 5h1.5"/>'
    ),
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5M14 11v5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "refresh": '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3L19.5 9"/><path d="M19.5 4.5V9H15"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "copy": (
        '<rect x="8" y="8" width="12" height="12" rx="2"/>'
        '<path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9'
        'A1.5 1.5 0 0 0 5.5 16H8"/>'
    ),
    "crate": '<path d="M3.5 8L12 4l8.5 4v8L12 20l-8.5-4z"/><path d="M3.5 8L12 12l8.5-4M12 12v8"/>',
    "export": '<path d="M12 15V4M7 9l5-5 5 5M5 14v5h14v-5"/>',
    "route": (
        '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/>'
        '<path d="M8 18h7.5a3 3 0 0 0 0-6h-7a3 3 0 0 1 0-6H16"/>'
    ),
    "panel": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
    "list": '<path d="M4 6h16M4 12h16M4 18h10"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check-circle": _CIRCLE + '<path d="M8 12.3l2.8 2.8L16.2 9.6"/>',
    "x-circle": _CIRCLE + '<path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6"/>',
    "alert": '<path d="M12 3.8L2.8 19.5h18.4z"/><path d="M12 10v4.5M12 17.2v.1"/>',
    "info": _CIRCLE + '<path d="M12 11v5.5M12 7.8v.1"/>',
    "clock": _CIRCLE + '<path d="M12 7v5l3.2 2"/>',
    "music": '<path d="M9 18V5.5l11-2V16"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10.5l5-3v9l-5-3"/>',
    "play": '<path fill="currentColor" d="M7.5 5.5v13l10.5-6.5z"/>',
    "pause": (
        '<rect fill="currentColor" x="6.5" y="5" width="3.5" height="14" rx="1"/>'
        '<rect fill="currentColor" x="14" y="5" width="3.5" height="14" rx="1"/>'
    ),
    "volume": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    "volume-off": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "chevron-left": '<path d="M15 6l-6 6 6 6"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "chevron-up": '<path d="M6 15l6-6 6 6"/>',
    "arrow-up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "arrow-down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
    "zap": '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z"/>',
    "flag": '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": (
        '<path d="M3 3l18 18M10.6 5.6A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5'
        'a16.6 16.6 0 0 1-2.9 3.7M6.6 6.6C4 8.3 2.5 12 2.5 12S6 18.5 12 18.5'
        'a9 9 0 0 0 4.4-1.1M9.9 9.9a3 3 0 0 0 4.2 4.2"/>'
    ),
}


def is_icon(name: str) -> bool:
    return name in _PATHS


def svg_markup(name: str, color: str, stroke_width: float = 1.75) -> str:
    """El SVG completo de un icono, ya teñido. Lo usan también los estilos QSS
    que necesitan un archivo (flecha del combo, tilde del checkbox)."""
    body = _PATHS[name].replace("currentColor", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def _device_ratio() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app else None
    # Mínimo 2: en una pantalla al 100 % el sobremuestreo igual afina el trazo.
    return max(2.0, screen.devicePixelRatio() if screen else 2.0)


@lru_cache(maxsize=512)
def pixmap(name: str, size: int = 18, color: str = TEXT_SECONDARY) -> QPixmap:
    """El icono rasterizado al tamaño lógico ``size`` en el color pedido."""
    ratio = _device_ratio()
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.transparent)
    if name in _PATHS:
        renderer = QSvgRenderer(QByteArray(svg_markup(name, color).encode("utf-8")))
        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, px.width(), px.height()))
        painter.end()
    px.setDevicePixelRatio(ratio)
    return px


@lru_cache(maxsize=512)
def icon(name: str, color: str = TEXT_SECONDARY, size: int = 18,
         disabled_color: str | None = None) -> QIcon:
    """Un QIcon con el icono en ``color`` y, si se pide, otro para deshabilitado."""
    qicon = QIcon()
    qicon.addPixmap(pixmap(name, size, color), QIcon.Normal)
    if disabled_color:
        qicon.addPixmap(pixmap(name, size, disabled_color), QIcon.Disabled)
    return qicon


def icon_size(size: int = 18) -> QSize:
    return QSize(size, size)
