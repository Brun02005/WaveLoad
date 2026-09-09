from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QMessageBox
from PySide6.QtCore import Qt

from ui.theme.colors import SURFACE_3, TEXT_PRIMARY, TEXT_SECONDARY, STATUS_INFO
from ui.components.buttons import WLPrimaryButton

class ImportProgressDialog(QDialog):
    """
    Non-blocking dialog that shows import progress.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importando Colección")
        self.setFixedSize(400, 180)
        self.setStyleSheet(f"background-color: {SURFACE_3}; color: {TEXT_PRIMARY}; border-radius: 8px;")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        self.title_label = QLabel("Escaneando archivos...")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Preparando la importación.")
        self.subtitle_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        layout.addWidget(self.subtitle_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #2D2D2D;
                border-radius: 4px;
                height: 8px;
                text-align: center;
                color: transparent;
            }}
            QProgressBar::chunk {{
                background-color: {STATUS_INFO};
                border-radius: 4px;
            }}
        """)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0) # Indeterminate initially
        layout.addWidget(self.progress_bar)

        self.cancel_btn = QPushButton("Ejecutar en segundo plano")
        self.cancel_btn.setStyleSheet(f"color: {TEXT_SECONDARY}; border: none; font-size: 13px; padding: 8px;")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.accept) # Just hides the dialog
        
        layout.addStretch()
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignCenter)

    def update_progress(self, current: int, total: int, text: str):
        if self.progress_bar.maximum() == 0 and total > 0:
            self.progress_bar.setMaximum(total)
            
        self.progress_bar.setValue(current)
        self.title_label.setText(f"Importando... ({current}/{total})")
        self.subtitle_label.setText(text)

class ImportSummaryDialog(QMessageBox):
    """
    Displays the result statistics of the import process.
    """
    def __init__(self, stats: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resumen de Importación")
        self.setIcon(QMessageBox.Information)
        self.setText("<b>Proceso de importación finalizado</b>")
        
        details = (
            f"Archivos descubiertos: {stats.get('discovered', 0)}\n"
            f"Archivos de audio soportados: {stats.get('supported', 0)}\n"
            f"Pistas importadas exitosamente: {stats.get('imported', 0)}\n"
            f"Duplicados omitidos: {stats.get('skipped', 0)}\n"
            f"Archivos no soportados/ilegibles: {stats.get('unsupported', 0)}\n"
            f"Errores de importación: {stats.get('failed', 0)}\n"
        )
        
        self.setInformativeText(details)
