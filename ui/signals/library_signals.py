"""
ui/signals/library_signals.py
=============================
Provides a Qt Signal bridge for Library Service events.
Allows the UI to react to incremental library changes (e.g. background 
downloads finishing) without polling or coupling the UI directly to workers.
"""

from PySide6.QtCore import QObject, Signal

class LibrarySignals(QObject):
    """
    Global event bus for library updates.
    """
    track_added = Signal(dict)
    track_updated = Signal(dict)
    track_removed = Signal(str)

# Global instance for the application lifecycle
library_signals = LibrarySignals()
