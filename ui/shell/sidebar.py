"""
ui/shell/sidebar.py
===================
Left navigation sidebar for WaveLoad.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PySide6.QtCore import Qt, Signal

from ui.theme.colors import ACCENT
from ui.theme.spacing import SIDEBAR_WIDTH
from ui.theme.icons import Icons, pixmap
from ui.components.buttons import WLNavButton, WLSecondaryButton


# Orden del flujo de trabajo: conseguir música, ordenarla, filtrarla, armar.
NAV_ITEMS = (
    ("downloads", "Descargas", Icons.DOWNLOAD),
    ("library", "Librería", Icons.LIBRARY),
    ("collections", "Colecciones", Icons.COLLECTIONS),
    ("graph", "Grafo y sets", Icons.GRAPH),
)

NAV_TITLES = {key: label for key, label, _ in NAV_ITEMS} | {"settings": "Ajustes"}


class Sidebar(QWidget):
    """
    Main navigation sidebar. Emits navigation_requested when a section is clicked.
    """
    navigation_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(SIDEBAR_WIDTH)

        self._nav_buttons = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 16)
        layout.setSpacing(2)

        # Marca: alineada en alto con la toolbar para que la línea superior sea una.
        brand = QWidget()
        brand.setFixedHeight(56)
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(10, 0, 0, 0)
        brand_row.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(pixmap(Icons.APP_LOGO, 22, ACCENT))
        self.logo_label = QLabel("WaveLoad")
        self.logo_label.setObjectName("wl_logoLabel")
        brand_row.addWidget(mark)
        brand_row.addWidget(self.logo_label)
        brand_row.addStretch()
        layout.addWidget(brand)
        layout.addSpacing(14)

        # "Colecciones" estuvo oculto hasta que el motor funcionó de punta a
        # punta (2026-09-09). El principio es que todo lo que se muestra
        # funciona; una entrada "Próximamente" es un callejón sin salida.
        section = QLabel("BIBLIOTECA")
        section.setObjectName("wl_navSection")
        layout.addWidget(section)
        layout.addSpacing(6)
        for key, label, icon_name in NAV_ITEMS:
            self._add_nav_button(key, label, icon_name, layout)

        layout.addStretch()
        self._add_nav_button("settings", "Ajustes", Icons.SETTINGS, layout)
        layout.addSpacing(12)

        self.folder_box = self._build_folder_box()
        layout.addWidget(self.folder_box)

        self.set_active("downloads")

    def _add_nav_button(self, key: str, text: str, icon_name: str, layout):
        btn = WLNavButton(text, icon=icon_name)
        btn.clicked.connect(lambda: self.navigation_requested.emit(key))
        layout.addWidget(btn)
        self._nav_buttons[key] = btn

    def set_active(self, key: str):
        """Visually activate the specified nav button and deactivate others."""
        for k, btn in self._nav_buttons.items():
            btn.set_active(k == key)

    def _build_folder_box(self) -> QWidget:
        box = QWidget()
        box.setObjectName("wl_sidebarFolderBox")
        box.setAttribute(Qt.WA_StyledBackground, True)

        l = QVBoxLayout(box)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(4)

        title = QLabel("CARPETA DE DESCARGAS")
        title.setObjectName("wl_sfTitle")

        self.path_label = QLabel("Cargando…")
        self.path_label.setObjectName("wl_sfPath")

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.setSpacing(6)
        self.open_folder_btn = WLSecondaryButton("Abrir")
        self.open_folder_btn.setObjectName("wl_sfBtn")
        self.change_folder_btn = WLSecondaryButton("Cambiar")
        self.change_folder_btn.setObjectName("wl_sfBtn")

        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.change_folder_btn)

        l.addWidget(title)
        l.addWidget(self.path_label)
        l.addLayout(btn_layout)

        return box

    def set_output_path(self, path_str: str):
        """Muestra la carpeta por su nombre: la ruta completa va en el tooltip."""
        from pathlib import PureWindowsPath  # noqa: PLC0415
        name = PureWindowsPath(path_str).name or path_str
        metrics = self.path_label.fontMetrics()
        self.path_label.setText(metrics.elidedText(name, Qt.ElideMiddle, SIDEBAR_WIDTH - 52))
        self.path_label.setToolTip(path_str)
