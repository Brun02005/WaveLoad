"""
ui/theme/spacing.py
===================
WaveLoad 5 Design System — Spacing Scale & Layout Presets

Provides a consistent spacing scale and margin/padding presets
for layouts across the application.

Usage:
    from ui.theme.spacing import SPACE_MD, CONTENT_MARGINS
    layout.setContentsMargins(*CONTENT_MARGINS)
    layout.setSpacing(SPACE_MD)
"""


# ---------------------------------------------------------------------------
# Spacing Scale (in pixels)
# ---------------------------------------------------------------------------
# Based on a 4px base unit for consistent rhythm.

SPACE_NONE = 0
"""No spacing."""

SPACE_XXS = 2
"""Micro spacing — tight icon gaps, inline separators."""

SPACE_XS = 4
"""Extra small — inner padding of dense elements, badge padding."""

SPACE_SM = 8
"""Small — spacing between related elements, card inner padding."""

SPACE_MD = 12
"""Medium — standard spacing between UI groups, default layout spacing."""

SPACE_LG = 16
"""Large — section spacing, content margins in cards."""

SPACE_XL = 24
"""Extra large — page section separators, major content gaps."""

SPACE_XXL = 32
"""Double extra large — page-level top/bottom padding."""

SPACE_XXXL = 48
"""Triple extra large — hero sections, large empty states."""


# ---------------------------------------------------------------------------
# Layout Margin Presets (left, top, right, bottom)
# ---------------------------------------------------------------------------
# Use with: layout.setContentsMargins(*PRESET)

MARGINS_NONE = (0, 0, 0, 0)
"""Zero margins — for nested widgets that inherit parent spacing."""

MARGINS_TIGHT = (SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
"""Tight margins (8px all sides) — compact cards, toolbar items."""

MARGINS_CONTENT = (SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
"""Content margins (12px all sides) — standard content padding."""

MARGINS_CARD = (SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
"""Card margins (16px all sides) — cards, panels, elevated containers."""

MARGINS_PAGE = (SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
"""Page margins (24px all sides) — top-level page content areas."""

MARGINS_SETTINGS = (SPACE_XXL, SPACE_XXL, SPACE_XXL, SPACE_XXL)
"""Settings page margins (32px all sides) — spacious form layouts."""

MARGINS_SIDEBAR = (SPACE_LG, SPACE_XL, SPACE_LG, SPACE_XL)
"""Sidebar margins (16px horizontal, 24px vertical)."""


# ---------------------------------------------------------------------------
# Dimension Constants
# ---------------------------------------------------------------------------

SIDEBAR_WIDTH = 220
"""Fixed width for the navigation sidebar in pixels."""

TOOLBAR_HEIGHT = 48
"""Fixed height for the top toolbar in pixels."""

CONTEXT_PANEL_MIN_WIDTH = 280
"""Minimum width for the right contextual panel."""

CONTEXT_PANEL_DEFAULT_WIDTH = 320
"""Default/preferred width for the right contextual panel."""

BOTTOM_WORKSPACE_COLLAPSED_HEIGHT = 0
"""Height of the bottom workspace when collapsed."""

BOTTOM_WORKSPACE_EXPANDED_HEIGHT = 250
"""Default height of the bottom workspace when expanded."""

ICON_BUTTON_SIZE = 32
"""Standard size for square icon-only buttons."""

NAV_BUTTON_HEIGHT = 40
"""Height for sidebar navigation buttons."""

PRIMARY_BUTTON_HEIGHT = 46
"""Height for primary call-to-action buttons."""

PROGRESS_BAR_HEIGHT = 6
"""Height for progress bars."""

STATUS_INDICATOR_SIZE = 10
"""Size for status LED dot indicators."""

CARD_BORDER_RADIUS = 8
"""Border radius for cards and elevated containers."""

BUTTON_BORDER_RADIUS = 6
"""Border radius for buttons."""

INPUT_BORDER_RADIUS = 6
"""Border radius for input fields."""

THUMBNAIL_WIDTH = 80
"""Default thumbnail width in preview items."""

THUMBNAIL_HEIGHT = 50
"""Default thumbnail height in preview items."""


# ---------------------------------------------------------------------------
# Minimum Window Dimensions
# ---------------------------------------------------------------------------

MIN_WINDOW_WIDTH = 1280
"""Minimum window width for the 5-panel layout."""

MIN_WINDOW_HEIGHT = 760
"""Minimum window height for the 5-panel layout."""
