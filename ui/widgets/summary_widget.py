from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal

from ui.components.buttons import WLGhostButton, WLPrimaryButton, WLSecondaryButton
from ui.theme.colors import (
    SURFACE_3, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    STATUS_VALID, PRIMARY_RED,
)
from ui.theme.icons import Icons, pixmap
from ui.theme.typography import tabular


class _Metric(QWidget):
    """Un número grande con su etiqueta debajo."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("metricBox")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(2)
        self.value = QLabel("0")
        self.value.setFont(tabular(self.value.font()))
        self.value.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: 600;")
        caption = QLabel(label)
        caption.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(self.value)
        layout.addWidget(caption)


class SummaryWidget(QWidget):
    close_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("summaryCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._build_ui()
        self.setStyleSheet(f"""
            QWidget#summaryCard {{
                background-color: transparent;
            }}
            QWidget#failuresBox {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 10px;
            }}
            QWidget#metricBox {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 10px;
                min-width: 120px;
            }}
        """)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        badge = QLabel()
        badge.setFixedSize(48, 48)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(pixmap(Icons.BATCH_FINISHED, 22, TEXT_SECONDARY))
        badge.setStyleSheet(f"background-color: {SURFACE_3}; border-radius: 12px;")

        self.header_label = QLabel("Tanda terminada")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 600;")

        self.subtitle_label = QLabel("Las pistas convertidas ya están en tu carpeta y en la librería.")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet(f"color: {TEXT_SECONDARY};")

        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)
        metrics_layout.setAlignment(Qt.AlignCenter)
        self.success_widget = _Metric("descargadas", STATUS_VALID)
        self.failed_widget = _Metric("fallidas", PRIMARY_RED)
        self.skipped_widget = _Metric("ya estaban", TEXT_SECONDARY)
        self.time_widget = _Metric("duración", TEXT_PRIMARY)
        self.success_val = self.success_widget.value
        self.failed_val = self.failed_widget.value
        self.time_val = self.time_widget.value
        for widget in (self.success_widget, self.failed_widget, self.skipped_widget,
                       self.time_widget):
            metrics_layout.addWidget(widget)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.setAlignment(Qt.AlignCenter)
        self.open_folder_btn = WLSecondaryButton("Abrir carpeta", icon=Icons.OPEN_FOLDER)
        self.open_folder_btn.setFixedHeight(36)
        self.open_folder_btn.clicked.connect(self.open_folder_requested.emit)
        self.new_batch_btn = WLPrimaryButton("Nueva descarga", height=36)
        self.new_batch_btn.clicked.connect(self.close_requested.emit)
        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.new_batch_btn)

        layout.addWidget(badge, 0, Qt.AlignHCenter)
        layout.addSpacing(16)
        layout.addWidget(self.header_label)
        layout.addSpacing(4)
        layout.addWidget(self.subtitle_label)
        layout.addSpacing(24)
        layout.addLayout(metrics_layout)
        layout.addSpacing(24)
        layout.addLayout(btn_layout)

        # Qué falló y por qué. Sin esto el usuario veía "2 fallidas" sin saber
        # cuáles ni si valía la pena reintentarlas.
        self.failures_box = QWidget()
        self.failures_box.setObjectName("failuresBox")
        self.failures_box.setAttribute(Qt.WA_StyledBackground, True)
        self.failures_box.setMaximumWidth(640)
        fb = QVBoxLayout(self.failures_box)
        fb.setContentsMargins(16, 12, 12, 12)
        fb.setSpacing(6)
        cabecera = QHBoxLayout()
        self.failures_title = QLabel("No se pudieron descargar")
        self.failures_title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 600;")
        cabecera.addWidget(self.failures_title)
        cabecera.addStretch()
        self.copy_failed_btn = WLGhostButton("Copiar enlaces", icon=Icons.DUPLICATE)
        self.copy_failed_btn.setToolTip("Copia los enlaces que fallaron, para pegarlos y reintentar")
        self.copy_failed_btn.clicked.connect(self._copy_failed_links)
        cabecera.addWidget(self.copy_failed_btn)
        fb.addLayout(cabecera)
        self.failures_list = QVBoxLayout()
        self.failures_list.setSpacing(4)
        fb.addLayout(self.failures_list)
        layout.addSpacing(20)
        layout.addWidget(self.failures_box, 0, Qt.AlignHCenter)
        self.failures_box.setVisible(False)
        self._failed_links: list = []

    def set_stats(self, success_count: int, failed_count: int, elapsed_seconds: float,
                  skipped: int = 0, failures: list | None = None):
        self.success_val.setText(str(success_count))
        self.failed_val.setText(str(failed_count))
        self.skipped_widget.value.setText(str(skipped))
        self.skipped_widget.setVisible(skipped > 0)
        self._show_failures(failures or [])
        if elapsed_seconds < 60:
            time_str = f"{int(elapsed_seconds)} s"
        else:
            m = int(elapsed_seconds // 60)
            s = int(elapsed_seconds % 60)
            time_str = f"{m} min {s} s"
        self.time_val.setText(time_str)

    def _show_failures(self, failures: list):
        """``failures``: (título, motivo, enlace) de cada pista que falló."""
        while self.failures_list.count():
            item = self.failures_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._failed_links = [url for _, _, url in failures if url]
        self.copy_failed_btn.setText("Copiar enlaces")
        self.failures_box.setVisible(bool(failures))
        if not failures:
            return
        self.failures_title.setText(
            "No se pudo descargar 1 pista" if len(failures) == 1
            else f"No se pudieron descargar {len(failures)} pistas"
        )
        for titulo, motivo, _url in failures[:12]:
            fila = QWidget()
            h = QHBoxLayout(fila)
            h.setContentsMargins(0, 2, 0, 2)
            h.setSpacing(10)
            marca = QLabel()
            marca.setPixmap(pixmap(Icons.FAILED, 14, PRIMARY_RED))
            nombre = QLabel()
            nombre.setText(nombre.fontMetrics().elidedText(titulo, Qt.ElideRight, 260))
            nombre.setToolTip(titulo)
            nombre.setFixedWidth(260)
            nombre.setStyleSheet(f"color: {TEXT_PRIMARY};")
            razon = QLabel(motivo)
            razon.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
            razon.setWordWrap(True)
            h.addWidget(marca)
            h.addWidget(nombre)
            h.addWidget(razon, 1)
            self.failures_list.addWidget(fila)
        if len(failures) > 12:
            mas = QLabel(f"y {len(failures) - 12} más (están en el registro técnico)")
            mas.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
            self.failures_list.addWidget(mas)
        self.copy_failed_btn.setVisible(bool(self._failed_links))

    def _copy_failed_links(self):
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        QGuiApplication.clipboard().setText("\n".join(self._failed_links))
        self.copy_failed_btn.setText("Copiados")
