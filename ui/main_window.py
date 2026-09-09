import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from core.config import APP_NAME
from core.download_manager import DownloadManager

from ui.background_validator import BackgroundValidator
from ui.settings_page import SettingsPage

from ui.shell.app_shell import AppShell
from ui.workspaces.downloads_workspace import DownloadsWorkspace
from ui.workspaces.library_workspace import LibraryWorkspace
from ui.workspaces.settings_workspace import SettingsWorkspace
from ui.workspaces.graph_workspace import GraphWorkspace

from ui.theme.styles import build_application_stylesheet
from ui.theme.spacing import MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT

from storage.sqlite_track_repository import SqliteTrackRepository
from services.library_service import LibraryService
from ui.mappers.track_mapper import TrackPresentationMapper
from ui.signals.library_signals import library_signals
from PySide6.QtCore import QTimer


def get_resource_path(relative_path: str) -> str:
    """Obtiene la ruta absoluta de un recurso, soportando empaquetado con PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        # Cargar icono de la ventana
        icon_path = get_resource_path(os.path.join("ui", "waveload_icon.png"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Habilitar Drag and Drop global
        self.setAcceptDrops(True)

        # 1. Initialize core services
        from application.bootstrap import app_container
        self.settings_service = app_container.settings_service
        self.controller = DownloadManager()
        self.settings_page = SettingsPage(settings_service=self.settings_service)
        self.validator = BackgroundValidator(use_browser_auth=self.settings_service.get_use_cookies())
        
        self.track_repository = app_container.track_repository
        self.library_service = app_container.library_service
        self.track_service = app_container.track_service
        self.import_use_case = app_container.import_use_case
        self.analysis_coordinator = app_container.analysis_coordinator
        self.audio_player_service = app_container.audio_player_service

        # Bridge Domain Events to UI Signals
        from core.event_bus import event_bus, TrackCreatedEvent
        event_bus.subscribe(TrackCreatedEvent, self._on_domain_track_created)

        # Analysis results flow back to the library UI as full-row updates.
        self.analysis_coordinator.analysis_ready.connect(self._on_track_analyzed)

        # 2. Build the App Shell
        self.shell = AppShell()
        self.setCentralWidget(self.shell)
        self.shell.context_panel.set_audio_player(self.audio_player_service)

        # 3. Instantiate Workspaces
        self.downloads_ws = DownloadsWorkspace(
            controller=self.controller,
            validator=self.validator,
            settings_service=self.settings_service,
            audio_player_service=self.audio_player_service
        )
        self.library_ws = LibraryWorkspace()
        self.settings_ws = SettingsWorkspace(self.settings_page)
        self.graph_ws = GraphWorkspace(library_service=self.library_service)

        # 4. Register Workspaces with the Shell
        self.shell.register_workspace("downloads", self.downloads_ws)
        self.shell.register_workspace("library", self.library_ws)
        self.shell.register_workspace("graph", self.graph_ws)
        self.shell.register_workspace("settings", self.settings_ws)

        # 5. Connect Shell routing
        self.shell.sidebar.navigation_requested.connect(self._on_navigation_requested)
        
        # Connect Context Panel routing
        self.downloads_ws.context_changed.connect(self._on_context_changed)
        self.library_ws.track_selected.connect(self._on_library_track_selected)
        
        # Connect Context Panel toggle logic
        self.library_ws.toggle_panel_requested.connect(self._on_toggle_context_panel)

        # Library musical analysis (BPM / key / energy)
        self.library_ws.analyze_requested.connect(self._on_analyze_library)
        self.analysis_coordinator.progress.connect(self.library_ws.set_analysis_progress)

        # Knowledge graph: node selection reuses the library detail + compatibles.
        self.graph_ws.track_selected.connect(self._on_library_track_selected)
        self.graph_ws.toggle_panel_requested.connect(self.shell.set_context_panel_visible)

        # Connect Settings signals to sidebar folder box update
        self.settings_service.setting_changed.connect(self._on_setting_changed)
        self.shell.sidebar.open_folder_btn.clicked.connect(self._open_output_folder)
        self.shell.sidebar.change_folder_btn.clicked.connect(self._change_output_folder)

        # Connect Toolbar and Library Empty State Import
        self.shell.toolbar.settings_btn.clicked.connect(lambda: self._on_navigation_requested("settings"))
        self.shell.toolbar.import_btn.clicked.connect(self._on_import_music)
        self.library_ws.import_requested.connect(self._on_import_music)
        self.shell.toolbar.search_input.textChanged.connect(self._on_global_search)

        # 6. Initial State
        self._update_sidebar_folder()
        self._on_navigation_requested("downloads")
        
        # Restore context panel state
        from PySide6.QtCore import QSettings
        settings = QSettings("WaveLoad", "WaveLoad5")
        val = settings.value("context_panel_visible", False)
        # Handle string "true"/"false" vs boolean True/False across platforms
        panel_visible = str(val).lower() == "true" if isinstance(val, str) else bool(val)
        self.library_ws.btn_toggle_panel.setChecked(panel_visible)
        self.shell.set_context_panel_visible(panel_visible)
        
        # Connect library signals for incremental updates
        library_signals.track_added.connect(self.library_ws.add_track)
        library_signals.track_updated.connect(self.library_ws.update_track)
        library_signals.track_removed.connect(self.library_ws.remove_track)
        
        # Apply the new global design system stylesheet
        self.setStyleSheet(build_application_stylesheet())
        
        # Defer library loading slightly to allow UI to render the loading state
        QTimer.singleShot(100, self._load_initial_library_data)

    def _load_initial_library_data(self):
        """Fetches tracks from the backend and maps them for presentation."""
        # 1. Ask Application Service for Domain Objects
        domain_tracks = self.library_service.get_all_tracks()
        
        # 2. Map Domain Objects to Presentation Models (Dicts/ViewModels)
        presentation_tracks = TrackPresentationMapper.to_presentation_list(domain_tracks)
        
        # 3. Hand to the UI layer
        self.library_ws.set_tracks(presentation_tracks)

    def _on_domain_track_created(self, event):
        """Bridge between Domain background events and the UI thread."""
        # event.track is a domain.track.Track
        presentation_track = TrackPresentationMapper.to_presentation(event.track)
        # Emitting a Qt signal is thread-safe; it will cross the thread boundary safely
        library_signals.track_added.emit(presentation_track)

        # Kick off musical analysis (BPM / key / energy) for the new track.
        path = self.analysis_coordinator._primary_audio_path(event.track)
        if path:
            self.analysis_coordinator.analyze_track(str(event.track.id), path)

    def _on_track_analyzed(self, track_id: str, result):
        """Analysis finished: re-map the track and push a full-row update."""
        import uuid  # noqa: PLC0415
        track = self.track_repository.get_by_id(uuid.UUID(track_id))
        if track:
            library_signals.track_updated.emit(TrackPresentationMapper.to_presentation(track))

    def _on_analyze_library(self):
        """User asked to (re)analyse the whole library.

        Forces a full re-analysis so any tracks measured with an older, less
        accurate algorithm get corrected BPM/key values.
        """
        tracks = self.library_service.get_all_tracks()
        queued = self.analysis_coordinator.analyze_library(tracks, force=True)
        if queued == 0:
            QMessageBox.information(self, "WaveLoad", "No hay pistas para analizar.")

    def _on_navigation_requested(self, key: str):
        self.shell.sidebar.set_active(key)
        if key == "downloads":
            self.shell.switch_workspace(self.downloads_ws)
            # Downloads might have its own panel logic later, for now hide it
            self.shell.set_context_panel_visible(False)
        elif key == "library":
            self.shell.switch_workspace(self.library_ws)
            # Restore to user's preference
            self.shell.set_context_panel_visible(self.library_ws.btn_toggle_panel.isChecked())
        elif key == "graph":
            self.shell.switch_workspace(self.graph_ws)
            self.shell.set_context_panel_visible(self.graph_ws.btn_info.isChecked())
            self.graph_ws.ensure_built()
        elif key == "settings":
            self.shell.switch_workspace(self.settings_ws)
            self.shell.set_context_panel_visible(False)

    def _on_context_changed(self, metadata: dict):
        if not metadata:
            self.shell.context_panel.show_empty_state()
            return

        # Only populate context panel if it's visible, though we could populate it invisibly.
        # Actually, it's better to populate it so if user opens it, data is there.
        self.shell.context_panel.show_track_details(metadata)

    def _on_library_track_selected(self, metadata: dict):
        """Library selection: show details plus harmonically compatible tracks."""
        self._on_context_changed(metadata)
        if not metadata or metadata.get("is_multi"):
            return
        if metadata.get("key") in (None, "—"):
            return  # not analysed yet — nothing to match against
        from services.compatibility_service import CompatibilityService  # noqa: PLC0415
        pool = self.library_ws.get_all_track_dicts()
        compatibles = CompatibilityService.find_compatible(metadata, pool)
        self.shell.context_panel.set_compatibles(compatibles)

    def _on_toggle_context_panel(self, visible: bool):
        self.shell.set_context_panel_visible(visible)
        from PySide6.QtCore import QSettings
        settings = QSettings("WaveLoad", "WaveLoad5")
        settings.setValue("context_panel_visible", visible)

    def _on_global_search(self, query: str):
        # Only route search to the library workspace for now
        # Auto-switch to library if not there? The philosophy is that search is global.
        # For Sprint 2, just pass it to library workspace.
        self.library_ws.apply_search(query)
        if self.shell.workspace_stack.currentWidget() != self.library_ws:
            self._on_navigation_requested("library")

    def _on_import_music(self):
        """Handles the import workflow, triggered from Toolbar or Empty State."""
        from ui.dialogs.import_selection_dialog import WLImportSelectionDialog
        
        dialog = WLImportSelectionDialog(self)
        result = dialog.exec()
        
        if result == 0:
            return  # Cancelled
            
        paths = []
        if result == 1:
            files, _ = QFileDialog.getOpenFileNames(
                self, "Importar Archivos", str(self.settings_service.get_output_dir()),
                "Archivos de Audio (*.mp3 *.wav *.flac *.m4a *.aiff);;Todos los archivos (*.*)"
            )
            paths = files
        elif result == 2:
            folder = QFileDialog.getExistingDirectory(self, "Importar Carpeta", str(self.settings_service.get_output_dir()))
            if folder:
                paths = [folder]

        if not paths:
            return

        # Start Use Case
        from ui.dialogs.import_progress_dialog import ImportProgressDialog, ImportSummaryDialog
        
        signals = self.import_use_case.execute(paths)
        if not signals:
            QMessageBox.information(self, "Importación", "No se encontraron archivos de audio soportados.")
            return

        # Show non-blocking progress dialog
        self.progress_dialog = ImportProgressDialog(self)
        
        def on_progress(current, total, text):
            self.progress_dialog.update_progress(current, total, text)
            
        def on_finished(stats):
            self.progress_dialog.accept() # Close progress dialog
            # Show summary
            summary = ImportSummaryDialog(stats, self)
            summary.exec()

        signals.progress.connect(on_progress)
        signals.finished.connect(on_finished)
        
        self.progress_dialog.show()

    def _on_setting_changed(self, key: str, value: any):
        if key == "output_dir":
            self._update_sidebar_folder()

    def _update_sidebar_folder(self):
        out_dir = self.settings_service.get_output_dir()
        self.shell.sidebar.set_output_path(str(out_dir))

    def _open_output_folder(self):
        out_dir = self.settings_service.get_output_dir()
        try:
            os.startfile(out_dir)
        except Exception as e:
            QMessageBox.critical(self, "WaveLoad", f"No se pudo abrir la carpeta:\n{e}")

    def _change_output_folder(self):
        out_dir = self.settings_service.get_output_dir()
        new_dir = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Descargas", str(out_dir))
        if new_dir:
            success = self.settings_service.set_output_dir(new_dir)
            if not success:
                from ui.components.dialogs import show_error_dialog
                show_error_dialog(self, "Error de Configuración", "No se pudo configurar la carpeta de salida.\nVerifica que tengas permisos de escritura.")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        mime = event.mimeData()
        urls_to_add = []
        if mime.hasUrls():
            urls_to_add = [u.toString() for u in mime.urls()]
        elif mime.hasText():
            urls_to_add = mime.text().splitlines()

        if urls_to_add:
            if self.shell.workspace_stack.currentWidget() == self.downloads_ws:
                self.downloads_ws.append_urls_from_drop(urls_to_add)
                event.acceptProposedAction()
            else:
                self._on_navigation_requested("downloads")
                self.downloads_ws.append_urls_from_drop(urls_to_add)
                event.acceptProposedAction()