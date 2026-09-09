from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from ui.theme.colors import (
    SURFACE_2, SURFACE_3, SURFACE_4, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_INVERSE,
    PRIMARY_GREEN, PRIMARY_GREEN_HOVER, PRIMARY_RED, STATUS_INFO
)

class SummaryWidget(QWidget):
    close_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        # Encabezado
        self.header_label = QLabel("🏁 Tanda Finalizada")
        self.header_label.setObjectName("summaryHeader")
        self.header_label.setAlignment(Qt.AlignCenter)

        self.subtitle_label = QLabel("Se ha completado el procesamiento de los enlaces.")
        self.subtitle_label.setObjectName("summarySubtitle")
        self.subtitle_label.setAlignment(Qt.AlignCenter)

        # Fila de métricas
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(24)
        metrics_layout.setAlignment(Qt.AlignCenter)

        # Éxitos
        self.success_widget = QWidget()
        self.success_widget.setObjectName("metricBox")
        s_layout = QVBoxLayout(self.success_widget)
        s_layout.setSpacing(4)
        s_layout.setAlignment(Qt.AlignCenter)
        self.success_icon = QLabel("✅")
        self.success_icon.setStyleSheet("font-size: 20px;")
        self.success_val = QLabel("0")
        self.success_val.setObjectName("successValue")
        self.success_lbl = QLabel("Éxito")
        self.success_lbl.setObjectName("metricLabel")
        s_layout.addWidget(self.success_icon)
        s_layout.addWidget(self.success_val)
        s_layout.addWidget(self.success_lbl)

        # Fallidos
        self.failed_widget = QWidget()
        self.failed_widget.setObjectName("metricBox")
        f_layout = QVBoxLayout(self.failed_widget)
        f_layout.setSpacing(4)
        f_layout.setAlignment(Qt.AlignCenter)
        self.failed_icon = QLabel("❌")
        self.failed_icon.setStyleSheet("font-size: 20px;")
        self.failed_val = QLabel("0")
        self.failed_val.setObjectName("failedValue")
        self.failed_lbl = QLabel("Fallidos")
        self.failed_lbl.setObjectName("metricLabel")
        f_layout.addWidget(self.failed_icon)
        f_layout.addWidget(self.failed_val)
        f_layout.addWidget(self.failed_lbl)

        # Tiempo
        self.time_widget = QWidget()
        self.time_widget.setObjectName("metricBox")
        t_layout = QVBoxLayout(self.time_widget)
        t_layout.setSpacing(4)
        t_layout.setAlignment(Qt.AlignCenter)
        self.time_icon = QLabel("⏱️")
        self.time_icon.setStyleSheet("font-size: 20px;")
        self.time_val = QLabel("0s")
        self.time_val.setObjectName("timeValue")
        self.time_lbl = QLabel("Duración")
        self.time_lbl.setObjectName("metricLabel")
        t_layout.addWidget(self.time_icon)
        t_layout.addWidget(self.time_val)
        t_layout.addWidget(self.time_lbl)

        metrics_layout.addWidget(self.success_widget)
        metrics_layout.addWidget(self.failed_widget)
        metrics_layout.addWidget(self.time_widget)

        # Botones de acción
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignCenter)

        self.open_folder_btn = QPushButton("📁  Abrir Carpeta")
        self.open_folder_btn.setObjectName("summaryOpenBtn")
        self.open_folder_btn.setCursor(Qt.PointingHandCursor)
        self.open_folder_btn.clicked.connect(self.open_folder_requested.emit)

        self.new_batch_btn = QPushButton("Nueva Descarga")
        self.new_batch_btn.setObjectName("summaryNewBtn")
        self.new_batch_btn.setCursor(Qt.PointingHandCursor)
        self.new_batch_btn.clicked.connect(self.close_requested.emit)

        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.new_batch_btn)

        layout.addWidget(self.header_label)
        layout.addWidget(self.subtitle_label)
        layout.addLayout(metrics_layout)
        layout.addLayout(btn_layout)

    def _apply_styles(self):
        self.setObjectName("summaryCard")
        self.setStyleSheet(f"""
            QWidget#summaryCard {{
                background-color: {SURFACE_2};
                border: 2px solid {BORDER_DEFAULT};
                border-radius: 12px;
            }}
            QLabel#summaryHeader {{
                color: {TEXT_PRIMARY};
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#summarySubtitle {{
                color: {TEXT_SECONDARY};
                font-size: 13px;
            }}
            QWidget#metricBox {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 8px;
                min-width: 90px;
                min-height: 90px;
            }}
            QLabel#successValue {{
                color: {PRIMARY_GREEN};
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#failedValue {{
                color: {PRIMARY_RED};
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#timeValue {{
                color: {STATUS_INFO};
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#metricLabel {{
                color: {TEXT_MUTED};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#summaryOpenBtn {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_DEFAULT};
                color: {TEXT_PRIMARY};
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton#summaryOpenBtn:hover {{
                background-color: {SURFACE_4};
            }}
            QPushButton#summaryNewBtn {{
                background-color: {PRIMARY_GREEN};
                border: none;
                color: {TEXT_INVERSE};
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton#summaryNewBtn:hover {{
                background-color: {PRIMARY_GREEN_HOVER};
            }}
        """)

    def set_stats(self, success_count: int, failed_count: int, elapsed_seconds: float):
        self.success_val.setText(str(success_count))
        self.failed_val.setText(str(failed_count))
        
        # Formatear el tiempo de manera amigable
        if elapsed_seconds < 60:
            time_str = f"{int(elapsed_seconds)}s"
        else:
            m = int(elapsed_seconds // 60)
            s = int(elapsed_seconds % 60)
            time_str = f"{m}m {s}s"
        self.time_val.setText(time_str)
