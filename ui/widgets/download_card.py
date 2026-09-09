import re
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, Signal
from ui.theme.colors import (
    SURFACE_BASE, SURFACE_3, SURFACE_4, BORDER_DEFAULT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, PRIMARY_GREEN, PRIMARY_RED
)
from ui.theme.icons import Icons
from ui.components.buttons import WLIconButton


class DownloadCard(QWidget):
    play_toggle_requested = Signal(int)  # index

    def __init__(self, index: int, url: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.url = url
        self.title = url
        self.status = "pending"  # pending, downloading, completed, failed, cancelled
        self.preview_source = None

        self._build_ui()
        self._apply_styles()

    def set_preview_source(self, source):
        self.preview_source = source
        self.play_btn.setEnabled(bool(source))

    def set_playing(self, is_playing: bool):
        self.play_btn.setText(Icons.PAUSE if is_playing else Icons.PLAY)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Icono de estado
        self.icon_label = QLabel("🕒")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setObjectName("statusIcon")
        self.icon_label.setFixedWidth(24)

        # Contenido principal
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        # Fila superior: Título y Porcentaje
        top_row = QHBoxLayout()
        self.title_label = QLabel(self.url)
        self.title_label.setObjectName("titleLabel")
        self.title_label.setWordWrap(False)
        # Elipsis si el texto es muy largo
        metrics = self.title_label.fontMetrics()
        elided = metrics.elidedText(self.url, Qt.ElideRight, 380)
        self.title_label.setText(elided)

        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("percentLabel")
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.percent_label.setFixedWidth(50)

        top_row.addWidget(self.title_label, 1)
        top_row.addWidget(self.percent_label)

        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # Fila inferior: Estado, Velocidad y ETA
        bottom_row = QHBoxLayout()
        self.status_label = QLabel("Pendiente...")
        self.status_label.setObjectName("statusLabel")

        self.speed_label = QLabel("")
        self.speed_label.setObjectName("speedLabel")
        self.speed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.eta_label = QLabel("")
        self.eta_label.setObjectName("etaLabel")
        self.eta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        bottom_row.addWidget(self.status_label)
        bottom_row.addStretch()
        bottom_row.addWidget(self.speed_label)
        bottom_row.addWidget(self.eta_label)

        info_layout.addLayout(top_row)
        info_layout.addWidget(self.progress_bar)
        info_layout.addLayout(bottom_row)

        self.play_btn = WLIconButton(Icons.PLAY)
        self.play_btn.setEnabled(False)
        self.play_btn.setToolTip("Escuchar antes de descargar")
        self.play_btn.clicked.connect(lambda: self.play_toggle_requested.emit(self.index))

        layout.addWidget(self.icon_label)
        layout.addLayout(info_layout)
        layout.addWidget(self.play_btn)

    def _apply_styles(self):
        # El estilo principal del Card en modo oscuro (Spotify/Discord-inspired)
        self.setObjectName("downloadCard")
        self.setStyleSheet(f"""
            QWidget#downloadCard {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 4px;
            }}
            QWidget#downloadCard:hover {{
                background-color: {SURFACE_4};
                border-color: {BORDER_STRONG};
            }}
            QLabel#titleLabel {{
                color: {TEXT_PRIMARY};
                font-weight: 600;
                font-size: 13px;
                text-transform: uppercase;
            }}
            QLabel#percentLabel {{
                color: {PRIMARY_GREEN};
                font-weight: 800;
                font-size: 12px;
            }}
            QProgressBar {{
                background-color: {SURFACE_BASE};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {PRIMARY_GREEN};
                border-radius: 2px;
            }}
            QLabel#statusLabel {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                text-transform: uppercase;
                font-weight: 600;
            }}
            QLabel#speedLabel, QLabel#etaLabel {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                font-family: Consolas, monospace;
            }}
            QLabel#statusIcon {{
                font-size: 16px;
            }}
        """)

    def set_title(self, title: str):
        self.title = title
        metrics = self.title_label.fontMetrics()
        # Darle suficiente espacio
        elided = metrics.elidedText(title, Qt.ElideRight, 450)
        self.title_label.setText(elided)
        self.title_label.setToolTip(title)

    def update_progress(self, text: str):
        """
        Recibe el texto formateado, por ej:
        - "45.2% | 1.2MiB/s | ETA 00:15"
        - "Convirtiendo a MP3..."
        - "Descargando..."
        """
        self.status = "downloading"
        self.status_label.setText("DESCARGANDO...")
        self.icon_label.setText("📥")
        self.icon_label.setStyleSheet(f"color: {PRIMARY_GREEN};") # Neón

        if "Convirtiendo" in text:
            self.status_label.setText("CONVIRTIENDO A MP3...")
            self.progress_bar.setRange(0, 0) # Efecto pulso / indefinido
            self.percent_label.setText("CONV.")
            self.speed_label.setText("")
            self.eta_label.setText("")
            # Cambiar color a blanco/gris para la conversión
            self.progress_bar.setStyleSheet(f"""
                QProgressBar::chunk {{
                    background-color: {TEXT_PRIMARY};
                }}
            """)
            return

        # Parsear porcentaje, velocidad y ETA
        # Ejemplo: "45.2% | 1.2MiB/s | ETA 00:15"
        self.progress_bar.setRange(0, 100)
        
        # Extraer porcentaje
        pct_match = re.search(r"(\d+(?:\.\d+)?)%", text)
        if pct_match:
            pct_val = float(pct_match.group(1))
            self.progress_bar.setValue(int(pct_val))
            self.percent_label.setText(f"{int(pct_val)}%")
        
        # Extraer velocidad y ETA si están separados por "|"
        parts = [p.strip() for p in text.split("|")]
        if len(parts) >= 2:
            # Si el primero es porcentaje, el segundo es velocidad
            speed_text = parts[1]
            self.speed_label.setText(f"⚡ {speed_text}")
        else:
            self.speed_label.setText("")

        if len(parts) >= 3:
            eta_text = parts[2]
            # Quitar prefijo "ETA " si ya lo tiene para no duplicar
            eta_clean = eta_text.replace("ETA ", "").strip()
            self.eta_label.setText(f"⏳ {eta_clean}")
        else:
            self.eta_label.setText("")

    def set_finished(self, status: str, detail: str):
        """
        Finaliza la tarjeta
        status: ok, warning, cancelado, error
        """
        self.progress_bar.setRange(0, 100)
        self.speed_label.setText("")
        self.eta_label.setText("")

        if status == "ok":
            self.status = "completed"
            self.progress_bar.setValue(100)
            self.percent_label.setText("100%")
            self.status_label.setText("COMPLETADO")
            self.status_label.setStyleSheet(f"color: {PRIMARY_GREEN};")
            self.icon_label.setText("✅")
            self.progress_bar.setStyleSheet(f"""
                QProgressBar::chunk {{
                    background-color: {PRIMARY_GREEN};
                }}
            """)
            if detail:
                self.title_label.setText(detail)
                self.title_label.setToolTip(detail)
        elif status == "cancelado":
            self.status = "cancelled"
            self.progress_bar.setValue(0)
            self.percent_label.setText("CANCEL.")
            self.status_label.setText("CANCELADO")
            self.status_label.setStyleSheet(f"color: {TEXT_MUTED};")
            self.icon_label.setText("⛔")
            self.progress_bar.setStyleSheet(f"""
                QProgressBar::chunk {{
                    background-color: {TEXT_MUTED};
                }}
            """)
        else: # error o warning
            self.status = "failed"
            self.progress_bar.setValue(0)
            self.percent_label.setText("FALLO")
            self.status_label.setText(f"ERROR: {detail}")
            self.status_label.setStyleSheet(f"color: {PRIMARY_RED};")
            self.icon_label.setText("❌")
            self.progress_bar.setStyleSheet(f"""
                QProgressBar::chunk {{
                    background-color: {PRIMARY_RED};
                }}
            """)
