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
from ui.components.tables import WLTrackTable
from ui.components.empty_state import WLEmptyState


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
        
        # Encabezado: el título de la sección ya está en la toolbar; acá va
        # cuánto hay y las acciones sobre la librería.
        self.header_widget = QWidget()
        self.header_widget.setObjectName("wl_libraryHeader")
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(24, 14, 16, 10)
        header_layout.setSpacing(8)

        self.lbl_library_title = QLabel("")
        self.lbl_library_title.setObjectName("wl_caption")
        header_layout.addWidget(self.lbl_library_title)
        header_layout.addStretch()

        from ui.components.buttons import WLSecondaryButton
        self.btn_analyze = WLSecondaryButton("Analizar librería", icon=Icons.REFRESH)
        self.btn_analyze.setToolTip("Detecta BPM, tonalidad (Camelot) y energía de tus pistas")
        header_layout.addWidget(self.btn_analyze)

        self.btn_toggle_panel = WLIconButton(Icons.PANEL, tooltip="Mostrar u ocultar el panel de detalles")
        self.btn_toggle_panel.setCheckable(True)
        header_layout.addWidget(self.btn_toggle_panel)

        table_layout.addWidget(self.header_widget)

        self.table = WLTrackTable()
        table_layout.addWidget(self.table)
        self.stack.addWidget(self.page_table)

        self.page_loading = WLEmptyState(
            Icons.PENDING, "Cargando la librería", "Leyendo pistas y metadatos…"
        )
        self.stack.addWidget(self.page_loading)

        self.page_onboarding = WLEmptyState(
            Icons.LIBRARY,
            "Tu librería está vacía",
            "Importá la música que ya tenés o descargá pistas nuevas desde Descargas. "
            "WaveLoad analiza BPM, tonalidad y energía de cada una.",
            action_text="Importar música",
            action_icon=Icons.IMPORT,
        )
        self.action_btn = self.page_onboarding.action_btn
        self.stack.addWidget(self.page_onboarding)

        self.page_empty_search = WLEmptyState(
            Icons.SEARCH, "Sin resultados", "Ninguna pista coincide con la búsqueda."
        )
        self.stack.addWidget(self.page_empty_search)

        self.show_loading()

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
            self.btn_analyze.setText("Analizar librería")

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

    def _update_count(self):
        visibles = self.table.model().rowCount()
        if self._current_query and visibles != self._track_count:
            texto = f"{visibles} de {self._track_count} pistas"
        else:
            texto = f"{self._track_count} pista{'s' if self._track_count != 1 else ''}"
        faltantes = self.table.model().sourceModel().missing_count()
        if faltantes:
            texto += f"  ·  {faltantes} sin archivo"
        self.lbl_library_title.setText(texto)
        self.lbl_library_title.setToolTip(
            "Pistas cuyo archivo se borró o se movió. Clic derecho para ubicarlo "
            "o quitarlas de la librería." if faltantes else ""
        )

    def get_all_track_dicts(self) -> List[Dict[str, Any]]:
        """Returns the presentation dicts currently loaded (for compatibility)."""
        return self.table.model().sourceModel()._tracks

    def add_track(self, track: Dict[str, Any]):
        self.table.model().sourceModel().add_track(track)
        self._track_count += 1
        self._update_visibility()

    def update_track(self, track: Dict[str, Any]):
        self.table.model().sourceModel().update_track(track)
        self._update_count()

    def remove_tracks(self, track_ids: list):
        self.table.remove_tracks(track_ids)
        self._track_count = self.table.model().sourceModel().rowCount()
        self._update_visibility()

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
        self._update_count()
        if self._track_count == 0:
            self.stack.setCurrentWidget(self.page_onboarding)
        elif self.table.model().rowCount() == 0 and self._current_query:
            self.stack.setCurrentWidget(self.page_empty_search)
        else:
            self.stack.setCurrentWidget(self.page_table)
