"""
ui/shell/sidebar.py
===================
Left navigation sidebar for WaveLoad 5.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout
from PySide6.QtCore import Qt, Signal

from ui.theme.spacing import SIDEBAR_WIDTH, MARGINS_SIDEBAR, SPACE_LG
from ui.theme.icons import Icons
from ui.components.buttons import WLNavButton, WLSecondaryButton


from ui.theme.colors import BORDER_DEFAULT

class Sidebar(QWidget):
    """
    Main navigation sidebar. Emits navigation_requested when a section is clicked.
    """
    navigation_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        
        self._nav_buttons = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*MARGINS_SIDEBAR)
        layout.setSpacing(SPACE_LG)

        # Logo
        self.logo_label = QLabel(f"{Icons.APP_LOGO} WaveLoad")
        self.logo_label.setObjectName("wl_logoLabel")
        layout.addWidget(self.logo_label)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {BORDER_DEFAULT}; border: none; height: 1px;")
        layout.addWidget(line)

        # Navigation
        self.nav_layout = QVBoxLayout()
        self.nav_layout.setSpacing(4)
        
        self._add_nav_button("downloads", f"{Icons.DOWNLOAD}  Descargas")
        self._add_nav_button("library", f"{Icons.LIBRARY}  Librería")
        self._add_nav_button("graph", f"{Icons.GRAPH}  Grafo")
        # "Colecciones" is not built yet — hidden until implemented (was a
        # "Próximamente" dead-end) so the shipped app has no non-working nav.
        self._add_nav_button("settings", f"{Icons.SETTINGS}  Ajustes")
        
        layout.addLayout(self.nav_layout)
        layout.addStretch()

        # Output Folder Box (migrated from current main_window)
        self.folder_box = self._build_folder_box()
        layout.addWidget(self.folder_box)
        
        # Set initial active state
        self.set_active("downloads")

    def _add_nav_button(self, key: str, text: str):
        btn = WLNavButton(text)
        btn.clicked.connect(lambda: self.navigation_requested.emit(key))
        self.nav_layout.addWidget(btn)
        self._nav_buttons[key] = btn

    def set_active(self, key: str):
        """Visually activate the specified nav button and deactivate others."""
        for k, btn in self._nav_buttons.items():
            btn.set_active(k == key)

    def _build_folder_box(self) -> QWidget:
        box = QWidget()
        box.setObjectName("wl_sidebarFolderBox")
        
        l = QVBoxLayout(box)
        l.setContentsMargins(10, 10, 10, 10)
        l.setSpacing(6)
        
        title = QLabel("Carpeta de Salida")
        title.setObjectName("wl_sfTitle")
        
        self.path_label = QLabel("Cargando...")
        self.path_label.setObjectName("wl_sfPath")
        self.path_label.setWordWrap(True)
        
        btn_layout = QHBoxLayout()
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
        """Update the displayed output folder path, truncating if necessary."""
        # Simple truncation for display
        display_text = path_str
        if len(path_str) > 28:
            display_text = "..." + path_str[-25:]
        self.path_label.setText(display_text)
        self.path_label.setToolTip(path_str)
