"""
ui/components/progress.py
=========================
Progress bar components for WaveLoad 5.
"""

from PySide6.QtWidgets import QProgressBar


class WLProgressBar(QProgressBar):
    """
    Standard styled progress bar.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setValue(0)


from ui.theme.colors import TEXT_PRIMARY

class WLIndeterminateBar(QProgressBar):
    """
    Pulsing/indeterminate progress bar used for conversions or unknown durations.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setTextVisible(False)
        self.setRange(0, 0)  # Qt treats min=max=0 as indeterminate
        # Overriding the chunk color to white/grey for conversion state
        self.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {TEXT_PRIMARY};
            }}
        """)
