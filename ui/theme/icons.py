"""
ui/theme/icons.py
=================
WaveLoad 5 Design System — Icon Management

Centralizes all icon references used across the application.
Currently uses Unicode emoji as placeholders. Future versions can
replace these with SVG paths or icon-font codepoints without
changing consumer code.

Usage:
    from ui.theme.icons import Icons
    button.setText(f"{Icons.DOWNLOAD} Download")
"""


class Icons:
    """
    Centralized icon registry.

    All icon strings used in the application should be referenced
    through this class. This provides a single place to swap emoji
    for proper SVG/icon-font icons in the future.
    """

    # ---------------------------------------------------------------------------
    # Navigation
    # ---------------------------------------------------------------------------
    APP_LOGO = "🎧"
    DOWNLOAD = "📥"
    LIBRARY = "📚"
    GRAPH = "🕸"
    COLLECTIONS = "📁"
    SETTINGS = "⚙"
    SEARCH = "🔍"
    IMPORT = "📂"

    # ---------------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------------
    START = "🚀"
    CANCEL = "⛔"
    DELETE = "✕"
    PASTE = "📋"
    CLEAR = "🗑"
    OPEN_FOLDER = "📁"
    NEW_BATCH = "➕"
    REFRESH = "🔄"
    FILE = "📄"

    # ---------------------------------------------------------------------------
    # Status
    # ---------------------------------------------------------------------------
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    PENDING = "🕒"
    DOWNLOADING = "📥"
    CONVERTING = "⚡"
    COMPLETED = "✅"
    CANCELLED = "⛔"
    FAILED = "❌"

    # ---------------------------------------------------------------------------
    # Media
    # ---------------------------------------------------------------------------
    TRACK = "🎵"
    VIDEO = "🎥"
    PLAYLIST = "📁"
    TIMER = "⏱️"
    PLAY = "▶"
    PAUSE = "⏸"

    # ---------------------------------------------------------------------------
    # Collapsible / Navigation Arrows
    # ---------------------------------------------------------------------------
    ARROW_RIGHT = "▶"
    ARROW_DOWN = "▼"
    ARROW_LEFT = "◀"
    ARROW_UP = "▲"

    # ---------------------------------------------------------------------------
    # Misc
    # ---------------------------------------------------------------------------
    SPEED = "⚡"
    ETA = "⏳"
    BATCH_FINISHED = "🏁"
    INFO = "ℹ️"
