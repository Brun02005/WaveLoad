"""
ui/shell/app_shell.py
=====================
The master layout container for WaveLoad 5.
Implements the 5-zone layout: Toolbar, Sidebar, Workspace, Context Panel, Bottom Workspace.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QStackedWidget
from PySide6.QtCore import Qt

from ui.shell.sidebar import Sidebar
from ui.shell.toolbar import Toolbar
from ui.shell.context_panel import ContextPanel
from ui.shell.bottom_workspace import BottomWorkspace


class AppShell(QWidget):
    """
    The root layout widget for the MainWindow.
    Handles the structural arrangement of all primary panels.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_appShell")
        
        # Instantiate the panels
        self.toolbar = Toolbar()
        self.sidebar = Sidebar()
        self.context_panel = ContextPanel()
        self.bottom_workspace = BottomWorkspace()
        
        # The central workspace where module views are hosted
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setObjectName("wl_mainContainer")
        
        self._build_layout()

    def _build_layout(self):
        """Constructs the 5-zone layout."""
        # Sidebar de alto completo a la izquierda; a la derecha, la toolbar
        # arriba y el contenido abajo. Así la marca del sidebar queda alineada
        # con la toolbar en vez de quedar debajo de ella.
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.sidebar)

        right = QVBoxLayout()
        self._right = right
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.toolbar)
        main_layout.addLayout(right, 1)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Create a vertical splitter for (Central+Right) vs (Bottom)
        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.setHandleWidth(1)
        self.v_splitter.setChildrenCollapsible(False)
        
        # Create a horizontal splitter for (Central) vs (Right)
        self.h_splitter = QSplitter(Qt.Horizontal)
        self.h_splitter.setHandleWidth(1)
        self.h_splitter.setChildrenCollapsible(False)
        
        # Assemble horizontal split
        self.h_splitter.addWidget(self.workspace_stack)
        self.h_splitter.addWidget(self.context_panel)
        # Give central workspace priority for space
        self.h_splitter.setStretchFactor(0, 1)
        self.h_splitter.setStretchFactor(1, 0)

        # Assemble vertical split
        self.v_splitter.addWidget(self.h_splitter)
        self.v_splitter.addWidget(self.bottom_workspace)
        
        # Add the complete split view to the body
        body_layout.addWidget(self.v_splitter, 1)

        right.addLayout(body_layout, 1)

    def set_player(self, audio_player) -> None:
        """Agrega la barra del reproductor al pie de la columna de contenido."""
        from ui.shell.player_bar import PlayerBar  # noqa: PLC0415
        self.player_bar = PlayerBar(audio_player, self)
        self._right.addWidget(self.player_bar)

    def register_workspace(self, name: str, widget: QWidget):
        """Add a workspace module to the central stack."""
        self.workspace_stack.addWidget(widget)
        # Store index on widget for easy switching
        widget.setProperty("workspace_index", self.workspace_stack.indexOf(widget))

    def switch_workspace(self, widget: QWidget):
        """Switch the central stack to the given workspace."""
        idx = widget.property("workspace_index")
        if idx is not None:
            self.workspace_stack.setCurrentIndex(idx)

    def set_context_panel_visible(self, visible: bool):
        """Shows or hides the context panel, automatically reallocating space."""
        self.context_panel.setVisible(visible)
        if visible:
            # When shown, restore a preferred size by setting splitter sizes.
            # QSplitter automatically respects minimum sizes and size policies.
            # We don't force absolute values to let the OS handle it, but we give a hint.
            sizes = self.h_splitter.sizes()
            if sizes[1] == 0:
                self.h_splitter.setSizes([max(1, sizes[0] - 280), 280])
                
    def is_context_panel_visible(self) -> bool:
        return self.context_panel.isVisible()

