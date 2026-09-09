from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from ui.theme.colors import SURFACE_2, SURFACE_3, SURFACE_4, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_INVERSE, BORDER_SUBTLE, PRIMARY_GREEN
from ui.theme.spacing import SPACE_MD, SPACE_LG, MARGINS_CARD
from ui.theme.icons import Icons

class WLImportSelectionDialog(QDialog):
    """
    A professional selection dialog asking the user whether they want to import 
    individual files or an entire folder. Replaces the temporary QMessageBox.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importar Colección")
        self.setFixedSize(400, 240)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {SURFACE_2}; }}
            QLabel#wl_title {{ color: {TEXT_PRIMARY}; font-size: 18px; font-weight: bold; }}
            QLabel#wl_subtitle {{ color: {TEXT_SECONDARY}; font-size: 14px; }}
            QPushButton#wl_importBtn {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 8px;
                color: {TEXT_PRIMARY};
                font-size: 14px;
                padding: 16px;
                text-align: left;
            }}
            QPushButton#wl_importBtn:hover {{
                border: 1px solid {PRIMARY_GREEN};
                background-color: {SURFACE_4};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*MARGINS_CARD)
        layout.setSpacing(SPACE_MD)

        title = QLabel("¿Qué deseas importar?")
        title.setObjectName("wl_title")
        subtitle = QLabel("Selecciona el tipo de contenido que quieres añadir a WaveLoad.")
        subtitle.setObjectName("wl_subtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(SPACE_MD)

        self.btn_files = QPushButton(f"{Icons.FILE}   Importar Archivos Sueltos")
        self.btn_files.setObjectName("wl_importBtn")
        self.btn_folder = QPushButton(f"{Icons.LIBRARY}   Importar Carpeta Completa")
        self.btn_folder.setObjectName("wl_importBtn")

        self.btn_files.clicked.connect(lambda: self.done(1))
        self.btn_folder.clicked.connect(lambda: self.done(2))

        layout.addWidget(self.btn_files)
        layout.addWidget(self.btn_folder)
        
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet(f"background: transparent; border: none; color: {TEXT_SECONDARY}; padding: 8px;")
        cancel_btn.clicked.connect(lambda: self.done(0))
        cancel_layout.addWidget(cancel_btn)
        
        layout.addLayout(cancel_layout)
