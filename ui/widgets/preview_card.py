import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, Signal
from ui.theme.colors import (
    SURFACE_BASE, SURFACE_1, SURFACE_2, SURFACE_3, SURFACE_4, SURFACE_5,
    BORDER_DEFAULT, BORDER_STRONG, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_INVERSE,
    PRIMARY_GREEN, PRIMARY_GREEN_HOVER, PRIMARY_RED, PRIMARY_ORANGE,
    STATUS_PENDING, STATUS_VALID, STATUS_DUPLICATE, STATUS_ERROR, STATUS_INFO
)

class PreviewCard(QWidget):
    remove_requested = Signal(str)                  # url
    import_playlist_requested = Signal(str, list)   # url, entries_list

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.metadata = None
        self.is_playlist = False
        self.entries = []

        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(12)

        # 1. Miniatura (Thumbnail)
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(80, 50)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setObjectName("thumbLabel")
        self._set_placeholder_thumbnail()

        # 2. Información del track
        self.info_layout = QVBoxLayout()
        self.info_layout.setSpacing(2)

        self.title_label = QLabel("Cargando información...")
        self.title_label.setObjectName("previewTitle")
        self.title_label.setWordWrap(False)

        # Fila de metadatos (Uploader & Duración)
        self.meta_layout = QHBoxLayout()
        self.meta_layout.setSpacing(10)

        self.uploader_label = QLabel("YouTube")
        self.uploader_label.setObjectName("previewUploader")

        self.duration_label = QLabel("—")
        self.duration_label.setObjectName("previewDuration")

        self.meta_layout.addWidget(self.uploader_label)
        self.meta_layout.addWidget(self.duration_label)
        self.meta_layout.addStretch()

        self.info_layout.addWidget(self.title_label)
        self.info_layout.addLayout(self.meta_layout)

        # 3. Estado (Indicador visual led)
        self.status_indicator = QWidget()
        self.status_indicator.setFixedSize(10, 10)
        self.status_indicator.setObjectName("statusIndicatorPending")
        self.status_indicator.setToolTip("Cargando validación...")

        # 4. Controles (Botón de eliminar y botón de playlist si corresponde)
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setSpacing(8)

        # Botón de importar playlist (oculto por defecto)
        self.import_btn = QPushButton("Importar")
        self.import_btn.setObjectName("importPlaylistBtn")
        self.import_btn.setVisible(False)
        self.import_btn.clicked.connect(self._on_import_clicked)

        # Botón eliminar
        self.delete_btn = QPushButton("✕")
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._on_delete_clicked)

        self.controls_layout.addWidget(self.import_btn)
        self.controls_layout.addWidget(self.delete_btn)

        # Añadir al layout principal
        self.main_layout.addWidget(self.thumb_label)
        self.main_layout.addLayout(self.info_layout, 1)
        self.main_layout.addWidget(self.status_indicator)
        self.main_layout.addLayout(self.controls_layout)

    def _apply_styles(self):
        self.setObjectName("previewCard")
        self.setStyleSheet(f"""
            QWidget#previewCard {{
                background-color: {SURFACE_2};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 8px;
            }}
            QWidget#previewCard:hover {{
                background-color: {SURFACE_4};
                border-color: {BORDER_STRONG};
            }}
            QLabel#thumbLabel {{
                background-color: {SURFACE_BASE};
                border-radius: 4px;
                border: 1px solid {BORDER_DEFAULT};
            }}
            QLabel#previewTitle {{
                color: {TEXT_PRIMARY};
                font-weight: 600;
                font-size: 13px;
            }}
            QLabel#previewUploader {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
            }}
            QLabel#previewDuration {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 600;
            }}
            /* Indicador de estado led */
            QWidget#statusIndicatorPending {{
                background-color: {STATUS_PENDING};
                border-radius: 5px;
            }}
            QWidget#statusIndicatorValid {{
                background-color: {STATUS_VALID};
                border-radius: 5px;
            }}
            QWidget#statusIndicatorDuplicate {{
                background-color: {STATUS_DUPLICATE};
                border-radius: 5px;
            }}
            QWidget#statusIndicatorError {{
                background-color: {STATUS_ERROR};
                border-radius: 5px;
            }}
            /* Botones */
            QPushButton#deleteBtn {{
                background-color: transparent;
                border: none;
                color: {TEXT_SECONDARY};
                font-size: 12px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton#deleteBtn:hover {{
                background-color: {PRIMARY_RED};
                color: {TEXT_PRIMARY};
            }}
            QPushButton#importPlaylistBtn {{
                background-color: {PRIMARY_GREEN};
                color: {TEXT_INVERSE};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#importPlaylistBtn:hover {{
                background-color: {PRIMARY_GREEN_HOVER};
            }}
        """)

    def _set_placeholder_thumbnail(self):
        # Un placeholder con texto o emoji
        self.thumb_label.setText("🎥")
        self.thumb_label.setStyleSheet("font-size: 20px; text-align: center;")

    def set_loading(self):
        self.title_label.setText("Analizando enlace...")
        self.uploader_label.setText("YouTube")
        self.duration_label.setText("—")
        self.status_indicator.setObjectName("statusIndicatorPending")
        self.status_indicator.setToolTip("Cargando validación...")
        self.import_btn.setVisible(False)
        self._set_placeholder_thumbnail()
        # Forzar recarga de hojas de estilo
        self.style().unpolish(self.status_indicator)
        self.style().polish(self.status_indicator)

    def set_metadata(self, metadata: dict, is_duplicate: bool = False):
        """
        Llena la tarjeta con los metadatos obtenidos de yt-dlp
        """
        self.metadata = metadata
        self.is_playlist = metadata.get("is_playlist", False)
        
        # Título
        title = metadata.get("title", "Desconocido")
        self.title = title
        metrics = self.title_label.fontMetrics()
        elided = metrics.elidedText(title, Qt.ElideRight, 350)
        self.title_label.setText(elided)
        self.title_label.setToolTip(title)

        # Uploader / Canal
        self.uploader_label.setText(metadata.get("uploader", "Canal"))

        # Duración formateada
        dur = metadata.get("duration", 0)
        minutes = int(dur // 60)
        seconds = int(dur % 60)
        dur_text = f"{minutes:02d}:{seconds:02d}"

        # Miniatura
        thumb_path = metadata.get("thumbnail_path")
        if thumb_path and os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            scaled = pixmap.scaled(self.thumb_label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.thumb_label.setPixmap(scaled)
            self.thumb_label.setStyleSheet("") # Quitar estilo de emoji
        else:
            if self.is_playlist:
                self.thumb_label.setText("📁")
            else:
                self.thumb_label.setText("🎵")
            self.thumb_label.setStyleSheet("font-size: 20px;")

        # Si es playlist, mostrar info especial y botón importar
        if self.is_playlist:
            self.entries = metadata.get("entries", [])
            count = metadata.get("track_count", 0)
            size_mb = metadata.get("estimated_size_mb", 0.0)
            self.duration_label.setText(f"{count} videos | Total: {dur_text} | Est: {size_mb:.1f} MB")
            self.duration_label.setStyleSheet(f"color: {PRIMARY_ORANGE}; font-weight: bold;") # Naranja (ex Violeta)
            
            self.import_btn.setVisible(True)
            self.status_indicator.setObjectName("statusIndicatorValid")
            self.status_indicator.setToolTip("Playlist detectada. ¡Haz clic en Importar para agregar las pistas!")
        else:
            size_mb = metadata.get("estimated_size_mb", 0.0)
            self.duration_label.setText(f"{dur_text} ({size_mb:.1f} MB)")
            
            if is_duplicate:
                self.status_indicator.setObjectName("statusIndicatorDuplicate")
                self.status_indicator.setToolTip("Ya existe un archivo con este nombre en la carpeta de destino.")
            else:
                self.status_indicator.setObjectName("statusIndicatorValid")
                self.status_indicator.setToolTip("Enlace válido y listo para descargar.")

        # Re-aplicar estilos para actualizar color de led
        self.style().unpolish(self.status_indicator)
        self.style().polish(self.status_indicator)

    def set_error(self, error_msg: str):
        self.title_label.setText("Error al analizar enlace")
        self.title_label.setToolTip(error_msg)
        self.uploader_label.setText("Servidor de Youtube")
        self.duration_label.setText(f"Causa: {error_msg}")
        self.duration_label.setStyleSheet(f"color: {PRIMARY_RED};") # Rojo
        
        self.status_indicator.setObjectName("statusIndicatorError")
        self.status_indicator.setToolTip(error_msg)
        
        self.thumb_label.setText("⚠️")
        self.thumb_label.setStyleSheet("font-size: 20px;")
        self.import_btn.setVisible(False)

        self.style().unpolish(self.status_indicator)
        self.style().polish(self.status_indicator)

    def _on_delete_clicked(self):
        # Eliminar archivo de miniatura si existe
        if self.metadata and self.metadata.get("thumbnail_path"):
            path = self.metadata["thumbnail_path"]
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        self.remove_requested.emit(self.url)

    def _on_import_clicked(self):
        if self.is_playlist and self.entries:
            self.import_playlist_requested.emit(self.url, self.entries)
            # Deshabilitar botón después de hacer clic para evitar doble importación
            self.import_btn.setEnabled(False)
            self.import_btn.setText("Importado")
            self.import_btn.setStyleSheet(f"background-color: {SURFACE_5}; color: {TEXT_MUTED};")
