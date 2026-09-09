"""
ui/theme/typography.py
======================
WaveLoad 5 Design System — Typography

Defines font families, size scale, weight constants, and helper
functions to create pre-configured QFont objects.

Usage:
    from ui.theme.typography import font, FONT_SIZE_BASE, WEIGHT_SEMIBOLD
    label.setFont(font(size=FONT_SIZE_BASE, weight=WEIGHT_SEMIBOLD))
"""

from PySide6.QtGui import QFont


# ---------------------------------------------------------------------------
# Font Families
# ---------------------------------------------------------------------------

FONT_FAMILY_PRIMARY = "Inter"
"""Primary UI font — used for all labels, buttons, headings, body text.
Falls back to system fonts if Inter is not installed."""

FONT_FAMILY_MONO = "JetBrains Mono"
"""Monospace font — used for file paths, BPM values, technical logs, code.
Falls back to Consolas, then system monospace."""

# Fallback chains for QSS (comma-separated for CSS font-family)
FONT_STACK_PRIMARY = (
    "'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, "
    "'Roboto', 'Helvetica Neue', Arial, sans-serif"
)

FONT_STACK_MONO = (
    "'JetBrains Mono', 'Cascadia Code', 'Fira Code', "
    "'Consolas', 'Monaco', monospace"
)


# ---------------------------------------------------------------------------
# Font Size Scale (in pixels)
# ---------------------------------------------------------------------------
# Based on a 4px increment minor scale for optical consistency.

FONT_SIZE_XS = 10
"""Extra small — fine print, icon labels."""

FONT_SIZE_SM = 11
"""Small — metadata, badges, helper text, captions."""

FONT_SIZE_BASE = 13
"""Base — body text, default labels, table cells."""

FONT_SIZE_MD = 14
"""Medium — navigation items, section headers, prominent labels."""

FONT_SIZE_LG = 16
"""Large — card titles, panel headers."""

FONT_SIZE_XL = 20
"""Extra large — page titles, hero headings."""

FONT_SIZE_XXL = 26
"""Double extra large — settings page title, major headings."""


# ---------------------------------------------------------------------------
# Font Weights
# ---------------------------------------------------------------------------

WEIGHT_REGULAR = QFont.Weight.Normal       # 400
"""Normal / Regular weight — body text, descriptions."""

WEIGHT_MEDIUM = QFont.Weight.Medium        # 500
"""Medium weight — checkboxes, form labels."""

WEIGHT_SEMIBOLD = QFont.Weight.DemiBold    # 600
"""Semi-bold — navigation items, secondary buttons, metadata labels."""

WEIGHT_BOLD = QFont.Weight.Bold            # 700
"""Bold — headings, card titles, section headers."""

WEIGHT_EXTRABOLD = QFont.Weight.ExtraBold  # 800
"""Extra bold — primary actions, logo, progress stats."""


# ---------------------------------------------------------------------------
# Font Factory
# ---------------------------------------------------------------------------

def font(
    size: int = FONT_SIZE_BASE,
    weight: QFont.Weight = WEIGHT_REGULAR,
    family: str = FONT_FAMILY_PRIMARY,
    italic: bool = False,
) -> QFont:
    """
    Create a configured QFont with the given parameters.

    Parameters
    ----------
    size : int
        Font size in pixels.
    weight : QFont.Weight
        Font weight enum value.
    family : str
        Font family name (will use system fallback if not available).
    italic : bool
        Whether the font should be italic.

    Returns
    -------
    QFont
        A configured QFont instance ready for use with setFont().

    Examples
    --------
    >>> label.setFont(font(size=FONT_SIZE_LG, weight=WEIGHT_BOLD))
    >>> mono_label.setFont(font(family=FONT_FAMILY_MONO, size=FONT_SIZE_SM))
    """
    f = QFont(family)
    f.setPixelSize(size)
    f.setWeight(weight)
    f.setItalic(italic)
    return f


def font_mono(
    size: int = FONT_SIZE_BASE,
    weight: QFont.Weight = WEIGHT_REGULAR,
) -> QFont:
    """Convenience shortcut for creating a monospace font."""
    return font(size=size, weight=weight, family=FONT_FAMILY_MONO)
