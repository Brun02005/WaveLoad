"""
ui/workspaces/library_workspace.py
==================================
Library Workspace for WaveLoad 5.
The primary desktop workspace for professional DJs to prepare their music.
"""

from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QStackedWidget
)
from PySide6.QtCore import Qt, Signal

from ui.workspaces.base_workspace import BaseWorkspace
from ui.theme.icons import Icons
from ui.theme.colors import TEXT_SECONDARY, TEXT_MUTED, PRIMARY_ORANGE, BORDER_SUBTLE
from ui.components.tables import WLTrackTable
from ui.components.buttons import WLPrimaryButton


class LibraryWorkspace(BaseWorkspace):
    """
    The main library workspace. Designed to feel like a high-performance
    data grid rather than a generic file explorer.
    """
    
    # Emits raw track metadata for the context panel when selection changes
    track_selected = Signal(dict)
    
    # Emitted when the user wants to import music from the empty state
    import_requested = Signal()
    
    # Emitted when the user toggles the context panel
    toggle_panel_requested = Signal(bool)

    # Emitted when the user requests full-library musical analysis
    analyze_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State
        self._current_query = ""
        self._track_count = 0
        
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        from PySide6.QtWidgets import QHBoxLayout
        from ui.components.buttons import WLIconButton
        from ui.theme.colors import TEXT_PRIMARY
        
        # 1. Main Table View
        self.page_table = QWidget()
        table_layout = QVBoxLayout(self.page_table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        
        # Library Header
        self.header_widget = QWidget()
        self.header_widget.setObjectName("wl_libraryHeader")
        self.header_widget.setStyleSheet(f"background-color: transparent; border-bottom: 1px solid {BORDER_SUBTLE};")
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(16, 8, 16, 8)
        
        self.lbl_library_title = QLabel("Librería Local")
        self.lbl_library_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY};")
        header_layout.addWidget(self.lbl_library_title)
        
        header_layout.addStretch()

        from ui.components.buttons import WLSecondaryButton
        self.btn_analyze = WLSecondaryButton("Analizar biblioteca")
        self.btn_analyze.setToolTip("Detecta BPM y tonalidad (Camelot) de tus pistas")
        header_layout.addWidget(self.btn_analyze)

        self.btn_toggle_panel = WLIconButton(Icons.INFO)
        self.btn_toggle_panel.setToolTip("Mostrar/Ocultar Panel de Información")
        self.btn_toggle_panel.setCheckable(True)
        header_layout.addWidget(self.btn_toggle_panel)
        
        table_layout.addWidget(self.header_widget)
        
        self.table = WLTrackTable()
        table_layout.addWidget(self.table)
        self.stack.addWidget(self.page_table)

        # 2. Empty State: Loading
        self.page_loading = self._build_empty_state(
            icon=Icons.PENDING,
            title="Preparando Librería",
            subtitle="Cargando pistas y metadatos...",
            action_text=""
        )
        self.page_loading.findChild(QLabel, "wl_icon_label").setStyleSheet(f"font-size: 64px; color: {PRIMARY_ORANGE};")
        self.stack.addWidget(self.page_loading)

        # 3. Empty State: First-Time Onboarding
        self.page_onboarding = self._build_empty_state(
            icon=Icons.LIBRARY,
            title="Te damos la bienvenida a WaveLoad",
            subtitle="El centro de operaciones de tu colección musical.\nPara empezar, importa tu librería existente o descarga nuevas pistas.",
            action_text="Importar Colección"
        )
        # We'll re-bind the action button for onboarding later
        self.stack.addWidget(self.page_onboarding)

        # 4. Empty State: No Search Results
        self.page_empty_search = self._build_empty_state(
            icon=Icons.SEARCH,
            title="Sin Resultados",
            subtitle="No se encontraron pistas que coincidan con tu búsqueda.",
            action_text=""
        )
        self.stack.addWidget(self.page_empty_search)

        # Initialize
        self.show_loading()

    def _build_empty_state(self, icon: str, title: str, subtitle: str, action_text: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        icon_label = QLabel(icon)
        icon_label.setObjectName("wl_icon_label")
        icon_label.setStyleSheet(f"font-size: 64px; color: {TEXT_MUTED};")
        icon_label.setAlignment(Qt.AlignCenter)

        title_label = QLabel(title)
        title_label.setObjectName("wl_sectionTitle")
        title_label.setAlignment(Qt.AlignCenter)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        subtitle_label.setAlignment(Qt.AlignCenter)
        
        layout.addStretch()
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)

        if action_text:
            btn_layout = QVBoxLayout()
            btn_layout.setAlignment(Qt.AlignCenter)
            self.action_btn = WLPrimaryButton(action_text)
            self.action_btn.setFixedWidth(200)
            btn_layout.addWidget(self.action_btn)
            layout.addLayout(btn_layout)

        layout.addStretch()
        return page

    def _connect_signals(self):
        # Keyboard navigation and selection triggers context panel updates
        selection_model = self.table.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_changed)
        
        self.btn_toggle_panel.toggled.connect(self.toggle_panel_requested.emit)
        self.btn_analyze.clicked.connect(self.analyze_requested.emit)

        # Connect empty state action button
        if hasattr(self, 'action_btn') and self.action_btn:
            self.action_btn.clicked.connect(self.import_requested.emit)

    def set_analysis_progress(self, done: int, total: int):
        """Reflects background analysis progress on the analyze button."""
        if total and done < total:
            self.btn_analyze.setEnabled(False)
            self.btn_analyze.setText(f"Analizando {done}/{total}…")
        else:
            self.btn_analyze.setEnabled(True)
            self.btn_analyze.setText("Analizar biblioteca")

    def _on_selection_changed(self, selected, deselected):
        selected_tracks = self.table.get_selected_tracks()
        
        if not selected_tracks:
            self.track_selected.emit({})
        elif len(selected_tracks) == 1:
            self.track_selected.emit(selected_tracks[0])
        else:
            # Multi-selection handling (future integration)
            self.track_selected.emit({
                "title": f"{len(selected_tracks)} pistas seleccionadas",
                "is_multi": True
            })

    def set_tracks(self, tracks: List[Dict[str, Any]]):
        """Populates the library with data."""
        self._track_count = len(tracks)
        self.table.set_tracks(tracks)
        self._update_visibility()

    def get_all_track_dicts(self) -> List[Dict[str, Any]]:
        """Returns the presentation dicts currently loaded (for compatibility)."""
        return self.table.model().sourceModel()._tracks

    def add_track(self, track: Dict[str, Any]):
        self.table.model().sourceModel().add_track(track)
        self._track_count += 1
        self._update_visibility()

    def update_track(self, track: Dict[str, Any]):
        self.table.model().sourceModel().update_track(track)

    def remove_track(self, track_id: str):
        self.table.model().sourceModel().remove_track(track_id)
        self._track_count = max(0, self._track_count - 1)
        self._update_visibility()

    def apply_search(self, query: str):
        """Filters the library based on global search."""
        self._current_query = query
        self.table.apply_search(query)
        self._update_visibility()

    def show_loading(self):
        """Forces the loading state to be visible."""
        self.stack.setCurrentWidget(self.page_loading)

    def _update_visibility(self):
        """Determines which stacked widget page to show."""
        if self._track_count == 0:
            self.stack.setCurrentWidget(self.page_onboarding)
        elif self.table.model().rowCount() == 0 and self._current_query:
            self.stack.setCurrentWidget(self.page_empty_search)
        else:
            self.stack.setCurrentWidget(self.page_table)
