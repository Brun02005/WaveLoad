"""
ui/theme/assets.py
==================
WaveLoad Design System — Recursos de la interfaz

Carga las fuentes empaquetadas y prepara los pocos SVG que Qt Style Sheets
necesita como archivo (la flecha del combo, el tilde del checkbox, las flechas
del spinbox): QSS no acepta un icono en memoria, sólo ``url(ruta)``.

Todo es idempotente: se puede llamar más de una vez sin efecto.
"""

import hashlib
import logging
import sys
import tempfile
from pathlib import Path

from PySide6.QtGui import QFontDatabase

logger = logging.getLogger(__name__)

_FONT_FILES = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf")
_fonts_loaded = False
_qss_dir: Path | None = None


def asset_path(*parts: str) -> Path:
    """Ruta a un recurso de ``ui/assets``, tanto en desarrollo como en el .exe."""
    meipass = getattr(sys, "_MEIPASS", None)
    root = Path(meipass) / "ui" if meipass else Path(__file__).resolve().parent.parent
    return root.joinpath("assets", *parts)


def load_fonts() -> bool:
    """Registra Inter en la aplicación. Devuelve False si no se pudo; la
    interfaz cae entonces a Segoe UI, que es la siguiente en la pila."""
    global _fonts_loaded
    if _fonts_loaded:
        return True
    ok = True
    for name in _FONT_FILES:
        path = asset_path("fonts", name)
        if QFontDatabase.addApplicationFont(str(path)) < 0:
            logger.warning("No se pudo cargar la fuente %s", path)
            ok = False
    _fonts_loaded = ok
    return ok


def apply_theme(app) -> None:
    """Deja la aplicación lista para construir widgets: estilo base, fuente y
    hoja de estilos, en ese orden y una sola vez.

    - **Fusion como estilo base.** La interfaz se pinta entera con QSS; el
      estilo nativo "windows11" de Qt 6.7+ interpreta parte de esas reglas a su
      manera y, combinado con la hoja de estilos, crasheó al arrancar
      (access violation dentro de ``setStyleSheet``).
    - **Fuente en puntos, no en píxeles.** Una fuente en píxeles reporta
      ``pointSize() == -1``, y el código de Qt que recalcula tamaños en puntos
      terminaba en ``QFont::setPointSize(-1)``, el aviso que precedió al crash.
      13 px a 96 ppp son 9,75 pt.
    - **La hoja de estilos antes que los widgets**, a nivel aplicación: cada
      widget se estiliza una vez al crearse, en vez de re-estilar el árbol
      entero al final.
    """
    if getattr(app, "_waveload_theme", False):
        return
    from PySide6.QtGui import QFont  # noqa: PLC0415
    from ui.theme.styles import build_application_stylesheet  # noqa: PLC0415
    from ui.theme.typography import FONT_FAMILY_PRIMARY, FONT_SIZE_BASE  # noqa: PLC0415

    app.setStyle("Fusion")
    family = FONT_FAMILY_PRIMARY if load_fonts() else "Segoe UI"
    app_font = QFont(family)
    app_font.setPointSizeF(FONT_SIZE_BASE * 72 / 96)
    app.setFont(app_font)
    app.setStyleSheet(build_application_stylesheet())
    app._waveload_theme = True


def qss_icon(name: str, color: str, stroke_width: float = 2.0) -> str:
    """Ruta (con barras normales, como la quiere QSS) a un SVG teñido."""
    from ui.theme.icons import svg_markup  # noqa: PLC0415 — evita ciclo de imports

    global _qss_dir
    if _qss_dir is None:
        _qss_dir = Path(tempfile.gettempdir()) / "waveload_ui"
        _qss_dir.mkdir(parents=True, exist_ok=True)
    markup = svg_markup(name, color, stroke_width)
    digest = hashlib.sha1(markup.encode("utf-8")).hexdigest()[:10]
    path = _qss_dir / f"{name}-{digest}.svg"
    if not path.exists():
        path.write_text(markup, encoding="utf-8")
    return path.as_posix()
