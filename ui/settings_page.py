from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QPushButton, QFileDialog, QFrame
)
from PySide6.QtCore import Qt, QSettings, Signal
from ui.theme.colors import (
    SURFACE_2, SURFACE_3, SURFACE_4, BORDER_DEFAULT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, STATUS_INFO
)

class SettingsPage(QWidget):
    def __init__(self, settings_service, parent=None):
        super().__init__(parent)
        self.settings_service = settings_service
        self._build_ui()
        self._load_settings()
        self._apply_styles()
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)

        # Título principal
        title_label = QLabel("Ajustes")
        title_label.setObjectName("settingsTitle")
        layout.addWidget(title_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet(f"background-color: {BORDER_DEFAULT}; height: 1px; border: none;")
        layout.addWidget(line)

        # 1. Directorio de Descargas
        dir_section = QVBoxLayout()
        dir_section.setSpacing(8)
        
        dir_title = QLabel("Carpeta de Descargas")
        dir_title.setObjectName("sectionTitle")
        
        dir_desc = QLabel("Ubicación donde se guardarán todas las pistas descargadas y convertidas.")
        dir_desc.setObjectName("settingDesc")
        
        dir_controls = QHBoxLayout()
        dir_controls.setSpacing(10)
        
        self.dir_path_label = QLabel()
        self.dir_path_label.setObjectName("dirPathLabel")
        self.dir_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        self.change_dir_btn = QPushButton("Cambiar...")
        self.change_dir_btn.setObjectName("changeDirBtn")
        self.change_dir_btn.setCursor(Qt.PointingHandCursor)
        
        dir_controls.addWidget(self.dir_path_label, 1)
        dir_controls.addWidget(self.change_dir_btn)
        
        dir_section.addWidget(dir_title)
        dir_section.addWidget(dir_desc)
        dir_section.addLayout(dir_controls)
        layout.addLayout(dir_section)

        # 2. Calidad de Audio
        quality_section = QVBoxLayout()
        quality_section.setSpacing(8)
        
        quality_title = QLabel("Calidad de Conversión")
        quality_title.setObjectName("sectionTitle")
        
        quality_desc = QLabel("Tasa de bits objetivo para la conversión de audio a MP3.")
        quality_desc.setObjectName("settingDesc")
        
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("qualityCombo")
        self.quality_combo.addItem("320 kbps (Máxima)", "320")
        self.quality_combo.addItem("256 kbps (Alta)", "256")
        self.quality_combo.addItem("192 kbps (Estándar)", "192")
        self.quality_combo.addItem("128 kbps (Ligera)", "128")
        
        quality_section.addWidget(quality_title)
        quality_section.addWidget(quality_desc)
        quality_section.addWidget(self.quality_combo)
        layout.addLayout(quality_section)

        # 3. Autenticación / Cookies
        cookies_section = QVBoxLayout()
        cookies_section.setSpacing(6)
        
        cookies_title = QLabel("Seguridad y Descargas")
        cookies_title.setObjectName("sectionTitle")
        
        self.cookies_checkbox = QCheckBox("Usar cookies del navegador")
        self.cookies_checkbox.setObjectName("cookiesCheckbox")
        self.cookies_checkbox.setCursor(Qt.PointingHandCursor)
        
        cookies_desc = QLabel("Inyecta cookies de sesión activa para evitar bloqueos temporales en YouTube.")
        cookies_desc.setObjectName("settingDesc")
        
        cookies_section.addWidget(cookies_title)
        cookies_section.addWidget(self.cookies_checkbox)
        cookies_section.addWidget(cookies_desc)
        layout.addLayout(cookies_section)

        # 4. Preferencias del Sistema
        prefs_section = QVBoxLayout()
        prefs_section.setSpacing(6)
        
        prefs_title = QLabel("Preferencias")
        prefs_title.setObjectName("sectionTitle")
        
        self.auto_open_checkbox = QCheckBox("Abrir carpeta al finalizar")
        self.auto_open_checkbox.setObjectName("autoOpenCheckbox")
        self.auto_open_checkbox.setCursor(Qt.PointingHandCursor)
        
        prefs_section.addWidget(prefs_title)
        prefs_section.addWidget(self.auto_open_checkbox)
        layout.addLayout(prefs_section)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QLabel#settingsTitle {{
                color: {TEXT_PRIMARY};
                font-size: 26px;
                font-weight: 700;
            }}
            QLabel#sectionTitle {{
                color: {TEXT_PRIMARY};
                font-size: 14px;
                font-weight: 600;
                margin-top: 10px;
            }}
            QLabel#dirPathLabel {{
                background-color: {SURFACE_2};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
                padding: 8px 12px;
                color: {TEXT_PRIMARY};
                font-family: Consolas, monospace;
                font-size: 12px;
            }}
            QPushButton#changeDirBtn {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_STRONG};
                color: {TEXT_PRIMARY};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton#changeDirBtn:hover {{
                background-color: {SURFACE_4};
            }}
            QComboBox#qualityCombo {{
                background-color: {SURFACE_2};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
                padding: 6px 10px;
                color: {TEXT_PRIMARY};
                min-width: 200px;
            }}
            QComboBox#qualityCombo QAbstractItemView {{
                background-color: {SURFACE_2};
                color: {TEXT_PRIMARY};
                selection-background-color: {STATUS_INFO};
            }}
            QLabel#settingDesc {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                margin-left: 2px;
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
                font-size: 13px;
                font-weight: 500;
                spacing: 8px;
                margin-top: 4px;
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
