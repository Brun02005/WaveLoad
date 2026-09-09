"""
ui/theme/colors.py
==================
WaveLoad 5 Design System — Color Palette

Every color used in the application is defined here as a named constant.
No hex code should ever appear in component files or stylesheets directly.

Usage:
    from ui.theme.colors import PRIMARY_GREEN, SURFACE_BASE
"""


# ---------------------------------------------------------------------------
# Brand / Accent Colors
# ---------------------------------------------------------------------------
# The primary accent moved from an electric neon green to a refined teal/cyan
# for a more professional "audio studio" feel. Reserve it for primary actions,
# active navigation, and focus — not decorative fills.

ACCENT = "#16BEC6"
"""Primary accent (teal/cyan) — primary actions, active nav, focus."""

ACCENT_HOVER = "#12A3AB"
"""Hover state for accent interactive elements."""

ACCENT_MUTED = "#0C2B2E"
"""Muted accent background — active-nav pill, disabled primary button."""

# Backward-compatible aliases: existing components/styles import these names.
# The value is now teal, not green.
PRIMARY_GREEN = ACCENT
PRIMARY_GREEN_HOVER = ACCENT_HOVER
PRIMARY_GREEN_MUTED = ACCENT_MUTED

PRIMARY_ORANGE = "#FF9F43"
"""Processing, Queue, Background Operations, Metadata Analysis."""

PRIMARY_ORANGE_HOVER = "#E08C3A"
"""Hover state for orange interactive elements."""

PRIMARY_RED = "#FF4757"
"""Errors, Failed Downloads, Destructive Actions, Critical Warnings."""

PRIMARY_RED_HOVER = "#E03E4E"
"""Hover state for red interactive elements."""


# ---------------------------------------------------------------------------
# Surface Layers (Layered Dark Backgrounds)
# ---------------------------------------------------------------------------
# Ordered from deepest/darkest to most elevated/lightest.
# Use these to create depth through elevation rather than flat black.

SURFACE_BASE = "#0D0E10"
"""Deepest background — application window, behind all content."""

SURFACE_1 = "#131517"
"""Sidebar, bottom workspace, recessed areas."""

SURFACE_2 = "#1A1C1F"
"""Main workspace background, primary content area."""

SURFACE_3 = "#222528"
"""Cards, panels, elevated containers, input backgrounds."""

SURFACE_4 = "#2A2D31"
"""Hover states on cards, secondary elevated elements."""

SURFACE_5 = "#333639"
"""Highest elevation — tooltips, popovers, active dropdowns."""


# ---------------------------------------------------------------------------
# Border Colors
# ---------------------------------------------------------------------------

BORDER_SUBTLE = "#1F2225"
"""Barely-visible borders for section separation."""

BORDER_DEFAULT = "#2A2D31"
"""Standard borders on cards, inputs, panels."""

BORDER_STRONG = "#3A3D42"
"""High-contrast borders for focus states, important separators."""

BORDER_FOCUS = PRIMARY_GREEN
"""Border color for focused inputs and active elements."""


# ---------------------------------------------------------------------------
# Text Colors
# ---------------------------------------------------------------------------

TEXT_PRIMARY = "#F0F1F2"
"""Primary text — headings, body text, labels."""

TEXT_SECONDARY = "#9AA1A9"
"""Secondary text — descriptions, helper text, metadata."""

TEXT_MUTED = "#5A5E64"
"""Muted text — placeholders, disabled labels, captions."""

TEXT_INVERSE = "#0D0E10"
"""Text on light/colored backgrounds (e.g. text on green buttons)."""

TEXT_GREEN = PRIMARY_GREEN
"""Green-colored text for success messages, active indicators."""

TEXT_ORANGE = PRIMARY_ORANGE
"""Orange-colored text for processing states, warnings."""

TEXT_RED = PRIMARY_RED
"""Red-colored text for errors, failed states."""


# ---------------------------------------------------------------------------
# Status / Indicator Colors
# ---------------------------------------------------------------------------

STATUS_VALID = "#2EBD59"
"""Validated, confirmed, ready state (LED indicators)."""

STATUS_DUPLICATE = "#E67E22"
"""Duplicate detected (LED indicators)."""

STATUS_ERROR = "#F53B57"
"""Error, invalid, failed (LED indicators)."""

STATUS_PENDING = "#6C757D"
"""Loading, pending, unresolved (LED indicators)."""

STATUS_INFO = "#5B8DEF"
"""Informational, neutral highlights, links."""


# ---------------------------------------------------------------------------
# Scrollbar Colors
# ---------------------------------------------------------------------------

SCROLLBAR_TRACK = SURFACE_BASE
"""Scrollbar track background."""

SCROLLBAR_HANDLE = "#333639"
"""Scrollbar handle default."""

SCROLLBAR_HANDLE_HOVER = PRIMARY_GREEN
"""Scrollbar handle on hover."""


# ---------------------------------------------------------------------------
# Convenience Aliases
# ---------------------------------------------------------------------------

# For backward-compatibility during incremental migration.
# These map legacy color usage to the new system.
NEON_GREEN = PRIMARY_GREEN
DANGER_RED = PRIMARY_RED
WARNING_ORANGE = PRIMARY_ORANGE
