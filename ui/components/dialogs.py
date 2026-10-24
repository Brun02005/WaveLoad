"""
ui/components/dialogs.py
========================
Dialog components for WaveLoad 5.
"""

from PySide6.QtWidgets import QMessageBox


class WLConfirmDialog(QMessageBox):
    """
    A styled confirmation dialog for critical actions.
    (Placeholder wrapper around QMessageBox for now).
    """
    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setText(text)
        self.setIcon(QMessageBox.Question)
        self.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        self.setDefaultButton(QMessageBox.No)
        # Note: full custom styling of QMessageBox is complex in QSS.
        # This wrapper provides a seam for future custom dialog implementations.


def show_error_dialog(parent, title: str, message: str):
    """Helper to show a standard error dialog."""
    # We prefix with the error icon just in case the OS dialog icon isn't clear enough
    QMessageBox.critical(parent, title, message)
