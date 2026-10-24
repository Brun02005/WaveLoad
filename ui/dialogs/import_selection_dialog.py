from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

from ui.components.buttons import WLGhostButton
from ui.theme.colors import (
    SURFACE_2, SURFACE_3, SURFACE_4, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER_SUBTLE, BORDER_STRONG,
)
from ui.theme.icons import Icons, pixmap


class _ImportOption(QPushButton):
    """Una opción del diálogo: icono, título y una línea que explica qué hace."""

    def __init__(self, icon_name: str, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_importBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(64)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(14)
        badge = QLabel()
        badge.setFixedSize(36, 36)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(pixmap(icon_name, 18, TEXT_SECONDARY))
        badge.setStyleSheet(f"background-color: {SURFACE_4}; border-radius: 9px;")
        badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(badge)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addStretch()
        t = QLabel(title)
        t.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 500;")
        d = QLabel(detail)
        d.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        for label in (t, d):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            texts.addWidget(label)
        texts.addStretch()
        row.addLayout(texts, 1)


class WLImportSelectionDialog(QDialog):
    """
    A selection dialog asking the user whether they want to import individual
    files or an entire folder.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importar música")
        self.setFixedWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {SURFACE_2}; }}
            QPushButton#wl_importBtn {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 10px;
            }}
            QPushButton#wl_importBtn:hover {{
                border-color: {BORDER_STRONG};
                background-color: {SURFACE_4};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 16)
        layout.setSpacing(8)

        title = QLabel("Importar música")
        title.setObjectName("wl_title")
        subtitle = QLabel("Los archivos no se mueven: WaveLoad los suma a la librería y los analiza.")
        subtitle.setStyleSheet(f"color: {TEXT_SECONDARY};")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)

        self.btn_files = _ImportOption(Icons.FILE, "Archivos sueltos", "MP3, WAV, FLAC, M4A o AIFF")
        self.btn_folder = _ImportOption(Icons.FOLDER, "Una carpeta entera", "Incluye las subcarpetas")
        self.btn_files.clicked.connect(lambda: self.done(1))
        self.btn_folder.clicked.connect(lambda: self.done(2))
        layout.addWidget(self.btn_files)
        layout.addWidget(self.btn_folder)

        layout.addSpacing(6)
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        cancel_btn = WLGhostButton("Cancelar")
        cancel_btn.clicked.connect(lambda: self.done(0))
        cancel_layout.addWidget(cancel_btn)
        layout.addLayout(cancel_layout)
