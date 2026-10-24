from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QPushButton, QFileDialog, QFrame
)
from PySide6.QtCore import Qt, QSettings, Signal
from ui.components.buttons import WLSecondaryButton
from ui.theme.colors import (
    SURFACE_1, SURFACE_3, BORDER_DEFAULT, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)
from ui.theme.icons import Icons

class SettingsPage(QWidget):
    def __init__(self, settings_service, parent=None):
        super().__init__(parent)
        self.settings_service = settings_service
        self._build_ui()
        self._load_settings()
        self._apply_styles()
        self._connect_signals()

    def _build_ui(self):
        # El contenido va en una columna de ancho legible, no estirado a toda
        # la ventana: una fila de ajustes de 1200 px separa demasiado la
        # etiqueta de su control.
        outer = QHBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        column = QWidget()
        column.setMaximumWidth(760)
        outer.addWidget(column, 1)
        outer.addStretch(0)

        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(28)
        layout.setAlignment(Qt.AlignTop)

        # 1. Descargas
        self.dir_path_label = QLabel()
        self.dir_path_label.setObjectName("dirPathLabel")
        self.dir_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.change_dir_btn = WLSecondaryButton("Cambiar", icon=Icons.FOLDER)

        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("qualityCombo")
        self.quality_combo.setFixedWidth(200)
        self.quality_combo.addItem("320 kbps · máxima", "320")
        self.quality_combo.addItem("256 kbps · alta", "256")
        self.quality_combo.addItem("192 kbps · estándar", "192")
        self.quality_combo.addItem("128 kbps · liviana", "128")

        self.cookies_checkbox = QCheckBox()
        self.cookies_checkbox.setObjectName("cookiesCheckbox")
        self.cookies_checkbox.setCursor(Qt.PointingHandCursor)

        carpeta = QWidget()
        carpeta_row = QHBoxLayout(carpeta)
        carpeta_row.setContentsMargins(0, 0, 0, 0)
        carpeta_row.setSpacing(8)
        carpeta_row.addWidget(self.dir_path_label, 1)
        carpeta_row.addWidget(self.change_dir_btn)

        layout.addWidget(self._section("Descargas", [
            self._row("Carpeta", "Dónde se guardan las pistas descargadas y convertidas.",
                      carpeta, stacked=True),
            self._row("Calidad del MP3", "Tasa de bits de la conversión.", self.quality_combo),
            self._row("Usar cookies del navegador",
                      "Evita bloqueos temporales de YouTube usando tu sesión abierta.",
                      self.cookies_checkbox),
        ]))

        # 2. Al terminar
        self.auto_open_checkbox = QCheckBox()
        self.auto_open_checkbox.setObjectName("autoOpenCheckbox")
        self.auto_open_checkbox.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self._section("Al terminar una tanda", [
            self._row("Abrir la carpeta", "Muestra los archivos nuevos en el Explorador.",
                      self.auto_open_checkbox),
        ]))

    def _section(self, title: str, rows: list) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        v.addWidget(label)
        card = QFrame()
        card.setObjectName("settingsCard")
        c = QVBoxLayout(card)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(0)
        for i, row in enumerate(rows):
            if i:
                sep = QFrame()
                sep.setObjectName("settingsSep")
                sep.setFixedHeight(1)
                c.addWidget(sep)
            c.addWidget(row)
        v.addWidget(card)
        return box

    def _row(self, title: str, desc: str, control: QWidget, stacked: bool = False) -> QWidget:
        """Una fila: título y explicación a la izquierda, el control a la
        derecha. ``stacked`` pone el control debajo, para los que son anchos."""
        row = QWidget()
        outer = QVBoxLayout(row) if stacked else QHBoxLayout(row)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10 if stacked else 16)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("rowTitle")
        d = QLabel(desc)
        d.setObjectName("settingDesc")
        d.setWordWrap(True)
        texts.addWidget(t)
        texts.addWidget(d)
        # En una fila horizontal los textos toman el ancho sobrante; apilada,
        # no se estiran a lo alto.
        outer.addLayout(texts, 0 if stacked else 1)
        if stacked:
            outer.addWidget(control)
        else:
            outer.addWidget(control, 0, Qt.AlignVCenter)
        return row

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QLabel#sectionTitle {{
                color: {TEXT_SECONDARY};
                font-size: 12px;
                font-weight: 600;
            }}
            QFrame#settingsCard {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 10px;
            }}
            QFrame#settingsSep {{
                background-color: {BORDER_SUBTLE};
                border: none;
            }}
            QLabel#rowTitle {{
                color: {TEXT_PRIMARY};
                font-weight: 500;
            }}
            QLabel#settingDesc {{
                color: {TEXT_MUTED};
                font-size: 12px;
            }}
            QLabel#dirPathLabel {{
                background-color: {SURFACE_1};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
                padding: 7px 10px;
                color: {TEXT_SECONDARY};
            }}
        """)

    def _load_settings(self):
        # Cargar carpeta de destino
        self.dir_path_label.setText(str(self.settings_service.get_output_dir()))

        # Cargar calidad de audio
        saved_quality = self.settings_service.get_audio_quality()
        index = self.quality_combo.findData(saved_quality)
        if index != -1:
            self.quality_combo.setCurrentIndex(index)

        # Cargar checkbox de cookies (por defecto True)
        self.cookies_checkbox.setChecked(self.settings_service.get_use_cookies())

        # Cargar checkbox de auto-abrir carpeta (por defecto True)
        self.auto_open_checkbox.setChecked(self.settings_service.get_auto_open_folder())

    def _connect_signals(self):
        self.change_dir_btn.clicked.connect(self._on_change_dir)
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        self.cookies_checkbox.stateChanged.connect(self._on_cookies_changed)
        self.auto_open_checkbox.stateChanged.connect(self._on_auto_open_changed)
        # Connect to SettingsService changes to update UI dynamically
        self.settings_service.setting_changed.connect(self._on_setting_changed_externally)

    def _on_change_dir(self):
        current = self.dir_path_label.text()
        chosen = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida", current)
        if chosen:
            success = self.settings_service.set_output_dir(chosen)
            if not success:
                from ui.components.dialogs import show_error_dialog
                show_error_dialog(self, "Error de Configuración", "No se pudo configurar la carpeta de salida.\nVerifica que tengas permisos de escritura.")

    def _on_quality_changed(self):
        quality = self.quality_combo.currentData()
        self.settings_service.set_audio_quality(quality)

    def _on_cookies_changed(self, state):
        self.settings_service.set_use_cookies(self.cookies_checkbox.isChecked())

    def _on_auto_open_changed(self, state):
        self.settings_service.set_auto_open_folder(self.auto_open_checkbox.isChecked())

    def _on_setting_changed_externally(self, key: str, value: any):
        if key == "output_dir":
            self.dir_path_label.setText(str(value))
        elif key == "audio_quality":
            index = self.quality_combo.findData(value)
            if index != -1:
                self.quality_combo.setCurrentIndex(index)
        elif key == "use_browser_auth":
            self.cookies_checkbox.setChecked(value)
        elif key == "auto_open_folder":
            self.auto_open_checkbox.setChecked(value)

    # Métodos getter rápidos para compatibilidad
    def get_output_dir(self) -> Path:
        return self.settings_service.get_output_dir()

    def get_audio_quality(self) -> str:
        return self.settings_service.get_audio_quality()

    def get_use_cookies(self) -> bool:
        return self.settings_service.get_use_cookies()

    def get_auto_open(self) -> bool:
        return self.settings_service.get_auto_open_folder()
