"""
ui/workspaces/downloads_workspace.py
====================================
Downloads module workspace for WaveLoad 5.
Migrated from the legacy MainWindow to a modular component.
"""

import os
import re
import time
from typing import List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QStackedWidget, QMessageBox, QListView,
    QPlainTextEdit
)
from PySide6.QtCore import Qt, QTimer, Signal

from core.config import MAX_LINKS_PER_BATCH
from core.download_manager import DownloadManager
from core.utils import (
    build_final_mp3_path, deduplicate_urls, friendly_error_message, is_probable_url,
)
from ui.theme.colors import PRIMARY_RED

from ui.workspaces.base_workspace import BaseWorkspace
from ui.background_validator import BackgroundValidator
from ui.settings_page import SettingsPage

from ui.widgets.preview_model import PreviewModel
from ui.widgets.preview_delegate import PreviewDelegate
from ui.widgets.download_card import DownloadCard
from ui.widgets.summary_widget import SummaryWidget

from ui.components.panels import WLCollapsiblePanel
from ui.components.inputs import WLTextArea
from ui.components.buttons import (
    WLDangerButton, WLGhostButton, WLPrimaryButton, WLSecondaryButton,
)
from ui.components.empty_state import WLEmptyState
from ui.theme.icons import Icons
from ui.components.progress import WLProgressBar


class DownloadsWorkspace(BaseWorkspace):
    """
    The main downloads workspace module.
    Handles URL input, background validation, active downloads progress, and summary.
    """
    def __init__(self, controller: DownloadManager, validator: BackgroundValidator, settings_service: any, audio_player_service: any = None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.validator = validator
        self.settings_service = settings_service
        self.audio_player_service = audio_player_service

        # State tracking
        self.validation_cache: Dict[str, dict] = {}
        self.active_validations = set()
        self.download_cards: Dict[int, DownloadCard] = {}
        self.current_download_urls: List[str] = []

        self.start_time = 0.0
        self.successful_downloads = 0
        self.failed_downloads = 0

        # Debounce timer for URL parsing
        self.input_timer = QTimer(self)
        self.input_timer.setInterval(500)
        self.input_timer.setSingleShot(True)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        # ----------------------------------------------------
        # Main Stack for Downloads (Input -> Active -> Summary)
        # ----------------------------------------------------
        self.stack = QStackedWidget()

        # PAGE 0: INPUT & PREVIEW
        self.page_input = self._build_input_page()
        self.stack.addWidget(self.page_input)

        # PAGE 1: ACTIVE DOWNLOADS
        self.page_active = self._build_active_page()
        self.stack.addWidget(self.page_active)

        # PAGE 2: SUMMARY
        self.page_summary = self._build_summary_page()
        self.stack.addWidget(self.page_summary)

        layout.addWidget(self.stack, 1)

        # ----------------------------------------------------
        # Logging Area
        # ----------------------------------------------------
        self.log_panel = WLCollapsiblePanel("Registro técnico")

        self.log_box = WLTextArea()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(110)
        self.log_box.setMaximumHeight(160)
        self.log_box.setObjectName("wl_logBox")

        self.log_panel.add_content(self.log_box)
        layout.addWidget(self.log_panel)

    def _build_input_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # URL Input
        self.input_box = WLTextArea()
        self.input_box.setPlaceholderText(
            "Pegá enlaces de YouTube, Spotify o SoundCloud, uno por línea"
        )
        self.input_box.setMinimumHeight(100)
        self.input_box.setMaximumHeight(140)
        layout.addWidget(self.input_box)

        # Input Actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.paste_btn = WLSecondaryButton("Pegar", icon=Icons.PASTE)
        self.clear_btn = WLGhostButton("Limpiar", icon=Icons.CLEAR)

        self.counter_label = QLabel(f"0 de {MAX_LINKS_PER_BATCH} enlaces")
        self.counter_label.setObjectName("wl_counterLabel")
        self.counter_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        actions_layout.addWidget(self.paste_btn)
        actions_layout.addWidget(self.clear_btn)
        actions_layout.addStretch()
        actions_layout.addWidget(self.counter_label)
        layout.addLayout(actions_layout)

        # Preview Section
        preview_title = QLabel("Vista previa")
        preview_title.setObjectName("wl_sectionTitle")
        layout.addSpacing(8)
        layout.addWidget(preview_title)

        self.preview_list = QListView()
        self.preview_list.setObjectName("wl_previewListView")
        self.preview_model = PreviewModel()
        self.preview_delegate = PreviewDelegate()
        self.preview_list.setModel(self.preview_model)
        self.preview_list.setItemDelegate(self.preview_delegate)
        # Transparent background for the list view so it blends with surface
        self.preview_list.setStyleSheet("background-color: transparent; border: none;")
        self.preview_list.setSelectionMode(QListView.SingleSelection)
        self.preview_list.setMouseTracking(True)

        # Sin enlaces, la lista vacía es un hueco: se explica qué va ahí.
        self.preview_stack = QStackedWidget()
        self.preview_empty = WLEmptyState(
            Icons.DOWNLOAD,
            "Todavía no hay enlaces",
            "Pegá uno o varios enlaces arriba. WaveLoad lee título, duración y "
            "tamaño antes de descargar, y avisa si alguno ya está en tu carpeta.",
        )
        self.preview_stack.addWidget(self.preview_empty)
        self.preview_stack.addWidget(self.preview_list)
        for signal in (self.preview_model.rowsInserted, self.preview_model.rowsRemoved,
                       self.preview_model.modelReset):
            signal.connect(self._sync_preview_empty)
        layout.addWidget(self.preview_stack, 1)

        # Start Button
        self.start_btn = WLPrimaryButton("Descargar", icon=Icons.START)
        self.start_btn.setEnabled(False)
        layout.addWidget(self.start_btn)

        return page

    def _build_active_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Scrollable area for download cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.downloads_container = QWidget()
        self.downloads_list_layout = QVBoxLayout(self.downloads_container)
        self.downloads_list_layout.setContentsMargins(0, 0, 0, 0)
        self.downloads_list_layout.setSpacing(8)
        self.downloads_list_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.downloads_container)
        layout.addWidget(self.scroll_area, 1)

        # Global Progress Box
        self.global_progress_box = QWidget()
        self.global_progress_box.setObjectName("wl_globalProgressBox")
        gp_layout = QVBoxLayout(self.global_progress_box)
        gp_layout.setContentsMargins(12, 12, 12, 12)
        gp_layout.setSpacing(8)

        gp_header = QHBoxLayout()
        self.global_progress_title = QLabel("Descargando")
        self.global_progress_title.setObjectName("wl_globalProgressTitle")

        self.global_stats_label = QLabel("0% completado")
        self.global_stats_label.setObjectName("wl_globalStatsLabel")
        self.global_stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        gp_header.addWidget(self.global_progress_title)
        gp_header.addWidget(self.global_stats_label)

        self.global_progress_bar = WLProgressBar()

        gp_layout.addLayout(gp_header)
        gp_layout.addWidget(self.global_progress_bar)
        layout.addWidget(self.global_progress_box)

        # Bottom Actions
        bottom_actions = QHBoxLayout()
        self.cancel_btn = WLDangerButton("Cancelar descargas", icon=Icons.CANCEL)
        bottom_actions.addStretch()
        bottom_actions.addWidget(self.cancel_btn)
        layout.addLayout(bottom_actions)

        return page

    def _build_summary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setAlignment(Qt.AlignCenter)

        self.summary_card = SummaryWidget()
        layout.addWidget(self.summary_card)
        return page

    def _connect_signals(self):
        # Input actions
        self.input_box.textChanged.connect(self._on_input_text_changed)
        self.input_timer.timeout.connect(self._process_input_changed)
        self.paste_btn.clicked.connect(self._paste_from_clipboard)
        self.clear_btn.clicked.connect(self._clear_input)

        # Preview list interactions
        self.preview_delegate.remove_requested.connect(self._remove_url_from_input)
        self.preview_delegate.import_playlist_requested.connect(self._on_import_playlist)
        self.preview_delegate.play_requested.connect(self._on_preview_play)
        self.preview_list.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Validator background events
        self.validator.validation_started.connect(self._on_validation_started)
        self.validator.validation_finished.connect(self._on_validation_finished)
        self.validator.validation_failed.connect(self._on_validation_failed)

        # Main actions
        self.start_btn.clicked.connect(self._start_download)
        self.cancel_btn.clicked.connect(self._cancel_download)

        # Summary actions
        self.summary_card.close_requested.connect(self._reset_to_input)
        self.summary_card.open_folder_requested.connect(self._open_output_folder)

        # Controller bindings (The orchestrator)
        self.controller.log.connect(self._append_log)
        self.controller.item_validated.connect(self._on_item_validated)
        self.controller.item_progress.connect(self._on_item_progress)
        self.controller.item_finished.connect(self._on_item_finished)
        self.controller.batch_progress.connect(self._on_batch_progress)
        self.controller.batch_finished.connect(self._on_batch_finished)
        self.controller.batch_error.connect(self._on_batch_error)

        if self.audio_player_service:
            self.audio_player_service.playback_started.connect(self._on_playback_started)
            self.audio_player_service.playback_paused.connect(self._on_playback_stopped)
            self.audio_player_service.playback_stopped.connect(self._on_playback_stopped)
            self.audio_player_service.now_playing_changed.connect(self._on_now_playing)
            self.audio_player_service.playback_error.connect(lambda _m: self._on_playback_stopped())

    # ----------------------------------------------------
    # INPUT HANDLING
    # ----------------------------------------------------
    def _on_input_text_changed(self):
        self.input_timer.start()

    def _process_input_changed(self):
        urls = self._parse_urls()
        count = len(urls)

        # Update counter UI
        if count > MAX_LINKS_PER_BATCH:
            self.counter_label.setText(f"{count} de {MAX_LINKS_PER_BATCH} enlaces · se descargan los primeros {MAX_LINKS_PER_BATCH}")
            self.counter_label.setStyleSheet(f"color: {PRIMARY_RED};")
        else:
            self.counter_label.setText(f"{count} de {MAX_LINKS_PER_BATCH} enlaces")
            self.counter_label.setStyleSheet("")

        # Sync preview model
        self.preview_model.set_urls(urls)

        # Dispatch validation for unknown URLs
        for url in urls:
            if url not in self.validation_cache and url not in self.active_validations:
                self.active_validations.add(url)
                self.validator.validate_url(url)

        self._update_action_buttons()

    def _parse_urls(self) -> List[str]:
        text = self.input_box.toPlainText()
        tokens = text.split()
        valid = [t for t in tokens if is_probable_url(t)]
        return deduplicate_urls(valid)

    def _paste_from_clipboard(self):
        import PySide6.QtGui as QtGui
        import PySide6.QtWidgets as QtWidgets
        clipboard = QtWidgets.QApplication.clipboard()
        mime_data = clipboard.mimeData()

        text = ""
        if mime_data.hasUrls():
            text = "\n".join([url.toString() for url in mime_data.urls()])
        elif mime_data.hasText():
            text = mime_data.text()

        if text:
            tokens = text.split()
            valid = [t for t in tokens if is_probable_url(t)]
            deduped = deduplicate_urls(valid)

            if deduped:
                current_text = self.input_box.toPlainText()
                new_text = current_text + "\n" + "\n".join(deduped) if current_text else "\n".join(deduped)
                self.input_box.setPlainText(new_text.strip())

    def _clear_input(self):
        self.input_box.clear()

    def _sync_preview_empty(self, *_):
        vacia = self.preview_model.rowCount() == 0
        self.preview_stack.setCurrentWidget(self.preview_empty if vacia else self.preview_list)

    def _remove_url_from_input(self, url: str):
        text = self.input_box.toPlainText()
        pattern = r'(?m)^' + re.escape(url) + r'\s*$'
        new_text = re.sub(pattern, '', text)
        new_text = os.linesep.join([s for s in new_text.splitlines() if s.strip()])
        self.input_box.setPlainText(new_text.strip())

    def _on_import_playlist(self, playlist_url: str, entries: list):
        if not entries:
            return

        # Hard limit
        import_entries = entries[:MAX_LINKS_PER_BATCH]
        truncated = len(entries) > MAX_LINKS_PER_BATCH

        urls_to_add = []
        for entry in import_entries:
            if isinstance(entry, tuple) and len(entry) >= 1:
                urls_to_add.append(entry[0])
            elif isinstance(entry, str):
                urls_to_add.append(entry)

        text = self.input_box.toPlainText()
        tracks_text = "\n".join(urls_to_add)
        pattern = r'(?m)^' + re.escape(playlist_url) + r'(?:\s|$)'
        new_text = re.sub(pattern, tracks_text + "\n", text)
        self.input_box.setPlainText(new_text.strip())

        if truncated:
            QMessageBox.information(
                self, "WaveLoad",
                f"Se importaron las primeras {len(import_entries)} canciones.\n"
                f"Se alcanzó el límite máximo de {MAX_LINKS_PER_BATCH} enlaces."
            )

    # ----------------------------------------------------
    # VALIDATION HANDLING
    # ----------------------------------------------------
    def _check_if_duplicate(self, metadata: dict) -> bool:
        title = metadata.get("title")
        if not title:
            return False
        output_dir = self.settings_service.get_output_dir()
        final_path = build_final_mp3_path(output_dir, title)
        return final_path.exists()

    def _on_validation_started(self, url: str):
        pass

    def _on_validation_finished(self, url: str, metadata: dict):
        if url in self.active_validations:
            self.active_validations.remove(url)

        self.validation_cache[url] = metadata
        is_dup = self._check_if_duplicate(metadata)
        self.preview_model.update_metadata(url, metadata, is_duplicate=is_dup)
        self._update_action_buttons()

        # If this URL happens to be selected right now, update the context panel
        selected_url = self._get_selected_url()
        if selected_url == url:
            self.context_changed.emit(metadata)

    def _on_validation_failed(self, url: str, error: str):
        if url in self.active_validations:
            self.active_validations.remove(url)

        self.validation_cache[url] = {"error": error}
        self.preview_model.set_error(url, error)
        self._update_action_buttons()

    def _update_action_buttons(self):
        # Count effective tracks: playlists expand into their entries, so a single
        # playlist link makes the download button live and reports its real size.
        effective = 0
        for url in self._parse_urls():
            meta = self.validation_cache.get(url)
            if not meta or "error" in meta:
                continue
            if meta.get("is_playlist"):
                effective += meta.get("track_count", 0) or len(meta.get("entries", []))
            else:
                effective += 1

        is_validating = len(self.active_validations) > 0
        can_dl = effective > 0 and not is_validating

        self.start_btn.setEnabled(can_dl)

        if is_validating:
            self.start_btn.setText("Verificando enlaces…")
        elif effective > MAX_LINKS_PER_BATCH:
            # Allowed: the batch is truncated to the first MAX at download time.
            self.start_btn.setText(f"Descargar {MAX_LINKS_PER_BATCH} de {effective} pistas")
        elif effective > 0:
            self.start_btn.setText(
                f"Descargar {effective} pista{'s' if effective != 1 else ''}"
            )
        else:
            self.start_btn.setText("Descargar")

    # ----------------------------------------------------
    # SELECTION & CONTEXT PANEL
    # ----------------------------------------------------
    def _get_selected_url(self):
        indexes = self.preview_list.selectionModel().selectedIndexes()
        if indexes:
            return self.preview_model.data(indexes[0], PreviewModel.UrlRole)
        return None

    def _on_selection_changed(self, selected, deselected):
        url = self._get_selected_url()
        if url and url in self.validation_cache:
            meta = self.validation_cache[url]
            if "error" not in meta:
                # Add loading flag for the context panel display logic
                meta_copy = meta.copy()
                meta_copy["is_loading"] = url in self.active_validations
                self.context_changed.emit(meta_copy)
                return
        # If no selection or errored, emit empty dict to show empty state
        self.context_changed.emit({})

    # ----------------------------------------------------
    # DOWNLOAD EXECUTION
    # ----------------------------------------------------
    def _expand_to_download_urls(self):
        """Expands the current preview into concrete (url, title) download pairs.

        Any playlist is auto-expanded into its individual tracks so the user can
        just paste a playlist and hit download — no manual "IMPORTAR" step needed.
        Returns the deduplicated list capped at MAX_LINKS_PER_BATCH, plus a
        `truncated` flag indicating the cap was hit.
        """
        pairs = []
        self._preview_failures = []
        for url in self._parse_urls():
            meta = self.validation_cache.get(url)
            if meta and "error" in meta:
                # No se descarta en silencio: entra a la tanda como fallida,
                # con su motivo, y aparece en el resumen.
                self._preview_failures.append((url, meta.get("title") or url, meta["error"]))
                continue
            if not meta:
                continue
            if meta.get("is_playlist"):
                for entry in meta.get("entries", []):
                    if isinstance(entry, tuple) and entry:
                        e_url = entry[0]
                        e_title = entry[1] if len(entry) > 1 else None
                    elif isinstance(entry, str):
                        e_url, e_title = entry, None
                    else:
                        continue
                    if e_url:
                        pairs.append((e_url, e_title))
            else:
                pairs.append((url, meta.get("title")))

        # Deduplicate by URL, keeping the first title seen.
        seen = set()
        deduped = []
        for u, t in pairs:
            if u in seen:
                continue
            seen.add(u)
            deduped.append((u, t))

        truncated = len(deduped) > MAX_LINKS_PER_BATCH
        return deduped[:MAX_LINKS_PER_BATCH], truncated

    def _start_download(self):
        pairs, truncated = self._expand_to_download_urls()

        if not pairs:
            motivos = "\n".join(
                f"• {friendly_error_message(e)}" for _, _, e in self._preview_failures[:6]
            )
            QMessageBox.warning(
                self, "WaveLoad",
                "Ninguno de los enlaces se puede descargar." + (f"\n\n{motivos}" if motivos else ""),
            )
            return

        if truncated:
            QMessageBox.information(
                self, "WaveLoad",
                f"La selección supera el máximo de {MAX_LINKS_PER_BATCH} enlaces.\n"
                f"Se descargarán las primeras {MAX_LINKS_PER_BATCH} canciones."
            )

        valid_urls = [u for u, _ in pairs]
        title_hints = {u: t for u, t in pairs if t}
        self.current_download_urls = valid_urls
        self.successful_downloads = 0
        self.failed_downloads = 0
        self.skipped_downloads = 0
        self.failed_items = []   # (título, motivo, enlace)
        self.start_time = time.time()

        # Clear old cards
        for i in reversed(range(self.downloads_list_layout.count())):
            item = self.downloads_list_layout.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()
                self.downloads_list_layout.removeItem(item)

        self.download_cards.clear()

        # Create new cards
        for idx, url in enumerate(self.current_download_urls):
            card = DownloadCard(idx, url)
            # Prefer the playlist-entry / validated title so cards never show raw URLs.
            title = title_hints.get(url)
            if not title and url in self.validation_cache:
                meta = self.validation_cache[url]
                title = meta.get("title")
            if title:
                card.set_title(title)
            meta = self.validation_cache.get(url) or {}
            if self.audio_player_service and not meta.get("error"):
                card.set_preview_source(meta.get("url") or url)
                card.play_toggle_requested.connect(self._on_card_play_toggle)
            self.downloads_list_layout.addWidget(card)
            self.download_cards[idx] = card

        # Los que ya fallaron en la vista previa van al final, como fallidos.
        base = len(self.current_download_urls)
        for offset, (url, title, error) in enumerate(self._preview_failures):
            card = DownloadCard(base + offset, url)
            card.set_title(title)
            motivo = friendly_error_message(error)
            card.set_finished("error", motivo)
            self.downloads_list_layout.addWidget(card)
            self.failed_downloads += 1
            self.failed_items.append((title, motivo, url))

        self.downloads_list_layout.addStretch()

        self.global_progress_bar.setValue(0)
        self.global_progress_title.setText(f"Descargando: 0 / {len(self.current_download_urls)}")
        self.global_stats_label.setText("0% completado")

        self.stack.setCurrentIndex(1)
        self._append_log("—" * 60)
        self._append_log(f"Iniciando tanda de {len(self.current_download_urls)} pistas")

        out_dir = self.settings_service.get_output_dir()
        use_cookies = self.settings_service.get_use_cookies()
        quality = self.settings_service.get_audio_quality()

        # We don't disable nav buttons directly here anymore, we emit a signal or
        # let the AppShell handle it if needed. For now, we trust the user.

        self.controller.start(self.current_download_urls, out_dir, use_cookies, quality)

    def _cancel_download(self):
        self.controller.cancel()
        self._append_log("Cancelación solicitada")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelando…")

    # ----------------------------------------------------
    # CONTROLLER SLOTS
    # ----------------------------------------------------
    def _append_log(self, text: str):
        self.log_box.appendPlainText(text)

    def _on_item_validated(self, index: int, title: str, status: str, detail: str):
        if index in self.download_cards:
            card = self.download_cards[index]
            if title and title != "—":
                card.set_title(title)
            # El resultado final (fallido, ya estaba) llega por item_finished.

    def _on_card_play_toggle(self, index: int):
        card = self.download_cards.get(index)
        if not card or not card.preview_source or not self.audio_player_service:
            return
        self.audio_player_service.toggle_play_pause_for(
            card.preview_source, is_local=False, title=card.title,
            subtitle="Vista previa · sin descargar",
        )

    def _on_preview_play(self, key: str):
        if not self.audio_player_service:
            return
        meta = next((m for m in self.validation_cache.values()
                     if isinstance(m, dict) and (m.get("url") == key)), None) or \
            self.validation_cache.get(key) or {}
        self.audio_player_service.toggle_play_pause_for(
            key, is_local=False, title=meta.get("title", ""),
            subtitle=meta.get("uploader") or "Vista previa · sin descargar",
        )

    def _on_now_playing(self, key: str, *_):
        self.preview_delegate.loading_key = key
        self.preview_delegate.playing_key = None
        self.preview_list.viewport().update()

    def _on_playback_started(self, key: str):
        self.preview_delegate.loading_key = None
        self.preview_delegate.playing_key = key
        self.preview_list.viewport().update()
        self._sync_card_playing_states(key)

    def _on_playback_stopped(self):
        self.preview_delegate.loading_key = None
        self.preview_delegate.playing_key = None
        self.preview_list.viewport().update()
        self._sync_card_playing_states(None)

    def _sync_card_playing_states(self, playing_key):
        for card in self.download_cards.values():
            card.set_playing(bool(playing_key) and card.preview_source == playing_key)

    def _on_item_progress(self, index: int, text: str):
        if index in self.download_cards:
            self.download_cards[index].update_progress(text)

    def _on_item_finished(self, index: int, status: str, final_name: str):
        card = self.download_cards.get(index)
        if card is None:
            return
        motivo = final_name if status != "error" else friendly_error_message(final_name)
        card.set_finished(status, motivo)
        if status == "ok":
            self.successful_downloads += 1
        elif status == "duplicado":
            self.skipped_downloads += 1
        elif status != "cancelado":
            self.failed_downloads += 1
            url = self.current_download_urls[index] if index < len(self.current_download_urls) else ""
            self.failed_items.append((card.title, motivo, url))

    def _on_batch_progress(self, completed: int, total: int):
        percent = int((completed / total) * 100) if total else 0
        self.global_progress_bar.setValue(percent)
        self.global_progress_title.setText(f"Descargando: {completed} / {total}")
        self.global_stats_label.setText(f"{percent}% completado")

    def _on_batch_finished(self):
        elapsed = time.time() - self.start_time
        self._append_log("Tanda terminada")

        self.summary_card.set_stats(
            self.successful_downloads, self.failed_downloads, elapsed,
            skipped=self.skipped_downloads, failures=self.failed_items,
        )

        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Cancelar descargas")

        self.stack.setCurrentIndex(2)

        # Antes leía self.settings_page, que esta pantalla nunca tuvo: la opción
        # "Abrir la carpeta al terminar" fallaba en silencio en cada tanda.
        if self.settings_service.get_auto_open_folder():
            self._open_output_folder()

    def _on_batch_error(self, message: str):
        self._append_log(f"Error en la tanda: {message}")
        QMessageBox.critical(self, "WaveLoad", message)
        self.stack.setCurrentIndex(0)

    # ----------------------------------------------------
    # UTILS
    # ----------------------------------------------------
    def _reset_to_input(self):
        self.input_box.clear()
        self.stack.setCurrentIndex(0)

    def _open_output_folder(self):
        out_dir = self.settings_service.get_output_dir()
        try:
            os.startfile(out_dir)
        except Exception as e:
            QMessageBox.critical(self, "WaveLoad", f"No se pudo abrir la carpeta:\n{e}")

    # Expose appending for drag & drop routing from shell
    def append_urls_from_drop(self, urls: List[str]):
        if not urls:
            return
        current_text = self.input_box.toPlainText()
        new_text = current_text + "\n" + "\n".join(urls) if current_text else "\n".join(urls)
        self.input_box.setPlainText(new_text.strip())
