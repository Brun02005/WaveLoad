"""
ui/shell/context_panel.py
=========================
Right contextual panel for WaveLoad 5.
Displays details about the currently selected track or item.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt

from ui.theme.spacing import CONTEXT_PANEL_MIN_WIDTH, MARGINS_CARD
from ui.theme.icons import Icons
from ui.theme.colors import (
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, SURFACE_1, BORDER_DEFAULT, BORDER_SUBTLE,
)
from ui.theme.typography import FONT_STACK_MONO
from ui.components.panels import WLInfoRow
from ui.components.buttons import WLIconButton
from ui.components.tables import camelot_qcolors


class ContextPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_player = None
        self._playback_key = None
        self._playback_is_local = False
        self.setObjectName("wl_contextPanel")
        self.setMinimumWidth(CONTEXT_PANEL_MIN_WIDTH)
        # Desktop layout: keep it fixed horizontally unless user drags splitter, expand vertically
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        self._build_empty_state()
        self._build_multi_state()
        self._build_track_detail()
        
        self.show_empty_state()

    def _build_empty_state(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setAlignment(Qt.AlignCenter)
        
        icon = QLabel(Icons.INFO)
        icon.setStyleSheet(f"font-size: 32px; color: {TEXT_SECONDARY};")
        icon.setAlignment(Qt.AlignCenter)
        
        text = QLabel("Selecciona una pista\npara ver detalles")
        text.setObjectName("wl_contextSubtitle")
        text.setAlignment(Qt.AlignCenter)
        
        l.addWidget(icon)
        l.addWidget(text)
        self.stack.addWidget(page)
        self.idx_empty = self.stack.indexOf(page)

    def _build_multi_state(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setAlignment(Qt.AlignCenter)
        
        icon = QLabel(Icons.COLLECTIONS)
        icon.setStyleSheet(f"font-size: 32px; color: {TEXT_SECONDARY};")
        icon.setAlignment(Qt.AlignCenter)
        
        self.multi_text = QLabel("Varias pistas seleccionadas")
        self.multi_text.setObjectName("wl_contextSubtitle")
        self.multi_text.setAlignment(Qt.AlignCenter)
        
        l.addWidget(icon)
        l.addWidget(self.multi_text)
        self.stack.addWidget(page)
        self.idx_multi = self.stack.indexOf(page)

    def _build_track_detail(self):
        self.page_track = QWidget()
        l = QVBoxLayout(self.page_track)
        l.setContentsMargins(0, 0, 0, 0)
        
        # Make the details scrollable in case the window is short
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(*MARGINS_CARD)
        content_layout.setSpacing(12)
        content_layout.setAlignment(Qt.AlignTop)
        
        # 1. Header (Artwork + Title + Artist)
        self.artwork = QLabel(Icons.TRACK)
        self.artwork.setAlignment(Qt.AlignCenter)
        self.artwork.setStyleSheet(f"""
            background-color: {SURFACE_1}; 
            border: 1px solid {BORDER_DEFAULT}; 
            border-radius: 8px;
            font-size: 48px;
        """)
        self.artwork.setFixedSize(220, 220)
        
        art_l = QVBoxLayout()
        art_l.setAlignment(Qt.AlignCenter)
        art_l.addWidget(self.artwork)
        content_layout.addLayout(art_l)
        
        self.title_label = QLabel("Título de la canción")
        self.title_label.setObjectName("wl_contextTitle")
        self.title_label.setWordWrap(True)
        content_layout.addWidget(self.title_label)

        self.artist_label = QLabel("Artista")
        self.artist_label.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        self.artist_label.setWordWrap(True)
        content_layout.addWidget(self.artist_label)

        play_row = QHBoxLayout()
        self.play_btn = WLIconButton(Icons.PLAY)
        self.play_btn.setEnabled(False)
        self.play_btn.setToolTip("Reproducir")
        self.play_btn.clicked.connect(self._on_play_clicked)
        play_row.addWidget(self.play_btn)
        play_row.addStretch()
        content_layout.addLayout(play_row)

        # Separator
        self._add_separator(content_layout)
        
        # 2. Musical Metadata (BPM, Key, Genre, Remix)
        self.row_remix = WLInfoRow("Remix:")
        self.row_genre = WLInfoRow("Género:")
        self.row_bpm = WLInfoRow("BPM:")
        self.row_key = WLInfoRow("Key:")
        self.row_duration = WLInfoRow("Duración:")
        
        content_layout.addWidget(self.row_remix)
        content_layout.addWidget(self.row_genre)
        content_layout.addWidget(self.row_bpm)
        content_layout.addWidget(self.row_key)
        content_layout.addWidget(self.row_duration)

        # Separator
        self._add_separator(content_layout)

        # 2b. Harmonic compatibility ("Compatibles para mezclar")
        self.compat_section = QWidget()
        compat_l = QVBoxLayout(self.compat_section)
        compat_l.setContentsMargins(0, 0, 0, 0)
        compat_l.setSpacing(6)
        compat_header = QLabel("Compatibles para mezclar")
        compat_header.setObjectName("wl_sectionTitle")
        compat_l.addWidget(compat_header)
        self.compat_container = QWidget()
        self.compat_layout = QVBoxLayout(self.compat_container)
        self.compat_layout.setContentsMargins(0, 0, 0, 0)
        self.compat_layout.setSpacing(2)
        compat_l.addWidget(self.compat_container)
        content_layout.addWidget(self.compat_section)
        self.compat_section.setVisible(False)
        self._add_separator(content_layout)

        # 3. Technical Metadata (Format, Quality, Size)
        self.row_format = WLInfoRow("Formato:")
        self.row_quality = WLInfoRow("Calidad:")
        self.row_bitrate = WLInfoRow("Bitrate:")
        self.row_samplerate = WLInfoRow("Frecuencia:")
        self.row_size = WLInfoRow("Tamaño:")
        
        content_layout.addWidget(self.row_format)
        content_layout.addWidget(self.row_quality)
        content_layout.addWidget(self.row_bitrate)
        content_layout.addWidget(self.row_samplerate)
        content_layout.addWidget(self.row_size)
        
        # Separator
        self._add_separator(content_layout)
        
        # 4. System Metadata (Folder, Date, Status)
        self.row_album = WLInfoRow("Álbum:")
        self.row_folder = WLInfoRow("Ubicación:")
        self.row_date = WLInfoRow("Añadido:")
        self.row_status = WLInfoRow("Estado:")
        
        content_layout.addWidget(self.row_album)
        content_layout.addWidget(self.row_folder)
        content_layout.addWidget(self.row_date)
        content_layout.addWidget(self.row_status)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        l.addWidget(scroll)
        
        self.stack.addWidget(self.page_track)
        self.idx_track = self.stack.indexOf(self.page_track)

    def _add_separator(self, layout):
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BORDER_SUBTLE}; margin-top: 8px; margin-bottom: 8px;")
        layout.addWidget(sep)

    def set_compatibles(self, compatibles: list):
        """Populate the harmonic-compatibility list for the selected track.

        `compatibles` is a list of CompatibleTrack (from CompatibilityService).
        Hides the whole section when there are no matches.
        """
        # Clear previous rows.
        while self.compat_layout.count():
            item = self.compat_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not compatibles:
            self.compat_section.setVisible(False)
            return

        for c in compatibles:
            self.compat_layout.addWidget(self._make_compat_row(c))
        self.compat_section.setVisible(True)

    def _make_compat_row(self, c) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 3, 0, 3)
        h.setSpacing(8)

        bg, fg = camelot_qcolors(c.key_camelot)
        chip = QLabel(c.key_camelot)
        chip.setAlignment(Qt.AlignCenter)
        chip.setFixedSize(38, 20)
        chip.setStyleSheet(
            f"background-color: {bg.name()}; color: {fg.name()}; border-radius: 10px; "
            f"font-family: {FONT_STACK_MONO}; font-weight: 600; font-size: 11px;"
        )
        h.addWidget(chip)

        info = QVBoxLayout()
        info.setSpacing(0)
        title = QLabel(c.title)
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        title.setMaximumWidth(190)
        from PySide6.QtGui import QFontMetrics  # noqa: PLC0415
        title.setText(QFontMetrics(title.font()).elidedText(c.title, Qt.ElideRight, 190))
        bpm_txt = f"{round(c.bpm)} BPM" if c.bpm else ""
        sub = QLabel(f"{c.relation} · {bpm_txt}" if bpm_txt else c.relation)
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        info.addWidget(title)
        info.addWidget(sub)
        h.addLayout(info)
        h.addStretch()
        return row

    def set_audio_player(self, player):
        self._audio_player = player
        player.playback_started.connect(self._on_playback_changed)
        player.playback_paused.connect(self._refresh_play_button)
        player.playback_stopped.connect(self._refresh_play_button)

    def _on_play_clicked(self):
        if self._audio_player and self._playback_key:
            self._audio_player.toggle_play_pause_for(self._playback_key, self._playback_is_local)

    def _on_playback_changed(self, _key: str):
        self._refresh_play_button()

    def _refresh_play_button(self):
        if not self._audio_player or not self._playback_key:
            self.play_btn.setText(Icons.PLAY)
            return
        playing_this = (
            self._audio_player.current_key() == self._playback_key
            and self._audio_player.is_playing()
        )
        self.play_btn.setText(Icons.PAUSE if playing_this else Icons.PLAY)

    def show_empty_state(self):
        self.stack.setCurrentIndex(self.idx_empty)

    def show_track_details(self, metadata: dict):
        if metadata.get("is_multi"):
            self.multi_text.setText(metadata.get("title", "Varias pistas seleccionadas"))
            self.stack.setCurrentIndex(self.idx_multi)
            return

        self.stack.setCurrentIndex(self.idx_track)

        # Clear any previous compatibility list; the library flow repopulates it.
        self.set_compatibles([])

        # Header
        self.title_label.setText(metadata.get("title", "Desconocido"))
        self.artist_label.setText(metadata.get("artist") or metadata.get("uploader", "Artista desconocido"))

        # A downloaded file plays straight from disk; anything else needs a
        # stream URL resolved on demand.
        if metadata.get("path"):
            self._playback_key, self._playback_is_local = metadata["path"], True
        elif metadata.get("url"):
            self._playback_key, self._playback_is_local = metadata["url"], False
        else:
            self._playback_key, self._playback_is_local = None, False
        self.play_btn.setEnabled(self._playback_key is not None and self._audio_player is not None)
        self._refresh_play_button()

        # Musical
        self.row_remix.set_value(metadata.get("remix", "—"))
        self.row_genre.set_value(metadata.get("genre", "—"))
        
        bpm = metadata.get("bpm")
        self.row_bpm.set_value(str(bpm) if bpm else "—")
        self.row_key.set_value(metadata.get("key", "—"))
        
        dur = metadata.get("duration")
        if dur:
            try:
                m, s = divmod(int(dur), 60)
                self.row_duration.set_value(f"{int(m)}:{int(s):02d}")
            except (ValueError, TypeError):
                self.row_duration.set_value("—")
        else:
            self.row_duration.set_value("—")
        
        # Technical
        self.row_format.set_value(metadata.get("format", "—"))
        self.row_quality.set_value(metadata.get("quality", "—"))
        self.row_bitrate.set_value(metadata.get("bitrate", "—"))
        self.row_samplerate.set_value(metadata.get("samplerate", "—"))
        self.row_size.set_value(metadata.get("filesize", "—"))
        
        # System
        self.row_album.set_value(metadata.get("album", "—"))
        self.row_folder.set_value(metadata.get("folder", "—"))
        self.row_date.set_value(metadata.get("date_added", "—"))
        
        # Status handles the dual nature (loading from validation vs loaded)
        status = metadata.get("status")
        if metadata.get("is_loading"):
            status = "Verificando..."
        elif not status:
            status = "Listo"
            
        self.row_status.set_value(status)
