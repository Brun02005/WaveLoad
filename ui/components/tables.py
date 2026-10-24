"""
ui/components/tables.py
=======================
Table components for WaveLoad 5.
Contains the high-performance Library table, model, and delegate.
"""

from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QTableView, QStyledItemDelegate, QHeaderView, QStyleOptionViewItem, QApplication
)
from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QPoint, QRect, QSize,
    Signal,
)
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics

from ui.theme.colors import (
    SURFACE_1, SURFACE_3, SURFACE_4, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER_SUBTLE, BORDER_DEFAULT, ACCENT, PRIMARY_ORANGE,
)
from ui.theme.typography import (
    FONT_FAMILY_PRIMARY, FONT_SIZE_BASE, FONT_SIZE_SM, tabular,
)
from ui.theme.icons import Icons, pixmap


# Column Indices — focused DJ-crate layout: identity + the mixing essentials.
COL_ARTWORK = 0
COL_TITLE = 1
COL_ARTIST = 2
COL_GENRE = 3
COL_BPM = 4
COL_KEY = 5
COL_ENERGY = 6
COL_DURATION = 7
COL_DATE = 8

HEADERS = [
    "", "Título", "Artista", "Género", "BPM", "Tono", "Energía", "Tiempo", "Añadido"
]

# --- Columnas adaptables ------------------------------------------------------
# Antes había anchos fijos y el Título era la única columna que cedía: con el
# panel de detalles abierto, en Colecciones o con el escalado de Windows al
# 125 %, quedaba reducido a "…" y no se sabía qué tema era. Ahora el título
# tiene prioridad y, si no entra todo, se ocultan primero las columnas que
# menos dicen.

# Columnas de ancho fijo (números y chips): siempre miden lo mismo.
FIXED_WIDTHS = {
    COL_ARTWORK: 48, COL_BPM: 56, COL_KEY: 60, COL_ENERGY: 68,
    COL_DURATION: 64, COL_DATE: 92,
}
# Columnas de texto: (peso en el reparto del sobrante, ancho mínimo legible).
FLEX_COLUMNS = {
    COL_TITLE: (0.5, 200),
    COL_ARTIST: (0.3, 120),
    COL_GENRE: (0.2, 110),
}
# Qué se oculta primero cuando no entra todo.
HIDE_ORDER = (COL_DATE, COL_GENRE, COL_ENERGY, COL_ARTWORK, COL_DURATION, COL_KEY)


def fit_columns(available: int, has_genres: bool = True) -> dict:
    """El ancho de cada columna visible para ``available`` píxeles.

    Devuelve ``{columna: ancho}``; las que no están en el resultado se ocultan.
    Pura (sin Qt) para poder probarla sin una ventana.
    """
    visibles = set(FIXED_WIDTHS) | set(FLEX_COLUMNS)
    if not has_genres:
        visibles.discard(COL_GENRE)  # una columna vacía sólo quita lugar
    for columna in (None, *HIDE_ORDER):
        if columna is not None:
            visibles.discard(columna)
        fijo = sum(w for c, w in FIXED_WIDTHS.items() if c in visibles)
        minimo = sum(m for c, (_, m) in FLEX_COLUMNS.items() if c in visibles)
        if fijo + minimo <= available:
            break

    anchos = {c: w for c, w in FIXED_WIDTHS.items() if c in visibles}
    flex = {c: v for c, v in FLEX_COLUMNS.items() if c in visibles}
    sobrante = max(0, available - sum(anchos.values()) - sum(m for _, m in flex.values()))
    peso_total = sum(p for p, _ in flex.values()) or 1
    for c, (peso, minimo) in flex.items():
        anchos[c] = minimo + int(sobrante * peso / peso_total)
    # Lo que se perdió por redondeo va al título, que es el que más lo necesita.
    if COL_TITLE in anchos:
        anchos[COL_TITLE] += max(0, available - sum(anchos.values()))
    return anchos


# La alineación del encabezado sigue a la de la columna: un título centrado
# sobre datos alineados a la izquierda se lee como un error.
HEADER_ALIGN = {
    COL_BPM: Qt.AlignRight | Qt.AlignVCenter,
    COL_DURATION: Qt.AlignRight | Qt.AlignVCenter,
    COL_KEY: Qt.AlignCenter,
    COL_ENERGY: Qt.AlignCenter,
}


def camelot_qcolors(code: str):
    """Return (background, foreground) QColors for a Camelot key chip.

    Colours follow the Camelot wheel: the number (1..12) picks a hue; the A/B
    letter shares the hue (relative major/minor sit together on the wheel).
    Returns a neutral pair for unknown/absent keys.
    """
    if not code or code in ("—", ""):
        return QColor(SURFACE_4), QColor(TEXT_MUTED)
    try:
        number = int(code[:-1])
    except (ValueError, TypeError):
        return QColor(SURFACE_4), QColor(TEXT_MUTED)
    hue = ((number - 1) * 30) % 360
    bg = QColor.fromHsv(hue, 120, 66)
    fg = QColor.fromHsv(hue, 130, 235)
    return bg, fg


class LibraryTableModel(QAbstractTableModel):
    """
    High-performance data model for the Library Workspace.
    Designed to handle 50,000+ tracks efficiently by keeping the UI responsive.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: List[Dict[str, Any]] = []

    def set_tracks(self, tracks: List[Dict[str, Any]]):
        self.beginResetModel()
        self._tracks = tracks
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._tracks)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None

        track = self._tracks[index.row()]
        col = index.column()

        # The delegate will use UserRole to get the raw dict
        if role == Qt.UserRole:
            return track

        if role == Qt.ToolTipRole:
            if track.get("missing"):
                return "Archivo no encontrado:\n" + (track.get("path") or "sin ruta")
            # El texto completo de lo que puede quedar cortado con "…".
            if col == COL_TITLE:
                return track.get("title") or None
            if col == COL_ARTIST and track.get("artist") not in (None, "—"):
                return track.get("artist")
            if col == COL_GENRE and track.get("genre") not in (None, "—"):
                return track.get("genre")
            return None

        if role == Qt.DisplayRole:
            if col == COL_TITLE: return track.get("title", "")
            elif col == COL_ARTIST: return track.get("artist", "")
            elif col == COL_GENRE:
                genre = track.get("genre")
                return genre if genre and genre != "—" else ""
            elif col == COL_BPM:
                bpm = track.get("bpm")
                return str(bpm) if bpm and bpm != "—" else ""
            elif col == COL_KEY:
                key = track.get("key")
                return str(key) if key and key != "—" else ""
            elif col == COL_ENERGY:
                # Painted as bars by the delegate; expose the number for sorting.
                energy = track.get("energy")
                return energy if energy is not None else -1
            elif col == COL_DURATION:
                dur = track.get("duration")
                if dur:
                    try:
                        m, s = divmod(int(dur), 60)
                        return f"{m}:{s:02d}"
                    except (ValueError, TypeError):
                        return ""
                return ""
            elif col == COL_DATE: return str(track.get("date_added", ""))
            # Artwork uses decoration or custom drawing in delegate

        elif role == Qt.TextAlignmentRole:
            if col in (COL_BPM, COL_DURATION):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            if col in (COL_KEY, COL_ENERGY):
                return int(Qt.AlignCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        return None

    def add_track(self, track: Dict[str, Any]):
        """Incrementally adds a track without rebuilding the table."""
        row = len(self._tracks)
        self.beginInsertRows(QModelIndex(), row, row)
        self._tracks.append(track)
        self.endInsertRows()

    def update_track(self, updated_track: Dict[str, Any]):
        """Incrementally updates a track if it exists."""
        track_id = updated_track.get("id")
        for row, track in enumerate(self._tracks):
            if track.get("id") == track_id:
                self._tracks[row] = updated_track
                idx_start = self.index(row, 0)
                idx_end = self.index(row, len(HEADERS) - 1)
                self.dataChanged.emit(idx_start, idx_end, [Qt.DisplayRole, Qt.UserRole])
                break

    def remove_tracks(self, track_ids) -> None:
        """Quita varias pistas de una vez: un solo reset en vez de una
        notificación por fila, que con cientos de filas se nota."""
        ids = set(track_ids)
        if not ids:
            return
        self.beginResetModel()
        self._tracks = [t for t in self._tracks if t.get("id") not in ids]
        self.endResetModel()

    def has_genres(self) -> bool:
        return any(t.get("genre") not in (None, "", "—") for t in self._tracks)

    def missing_count(self) -> int:
        return sum(1 for t in self._tracks if t.get("missing"))

    def remove_track(self, track_id: str):
        """Incrementally removes a track by ID."""
        for row, track in enumerate(self._tracks):
            if track.get("id") == track_id:
                self.beginRemoveRows(QModelIndex(), row, row)
                self._tracks.pop(row)
                self.endRemoveRows()
                break

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(HEADERS):
                return HEADERS[section].upper()
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(HEADER_ALIGN.get(section, Qt.AlignLeft | Qt.AlignVCenter))
        return None

    def get_track(self, index: QModelIndex) -> Dict[str, Any]:
        """Convenience method to retrieve the raw track metadata dict."""
        if index.isValid() and 0 <= index.row() < len(self._tracks):
            return self._tracks[index.row()]
        return {}


class LibrarySortFilterProxy(QSortFilterProxyModel):
    """
    Fast, in-memory proxy model for searching and filtering the library.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        # Search across all columns by default, or specific ones depending on config
        self.setFilterKeyColumn(-1)


class LibraryTableDelegate(QStyledItemDelegate):
    """
    Custom delegate for rendering the Library table rows.
    Ensures high-performance painting of thumbnails, badges, and text
    without creating thousands of nested widgets.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.margin = 10
        # Cifras tabulares de Inter: los números alinean en columna sin pasar
        # a una fuente monoespaciada que desentona con el resto.
        self._numeric = tabular(QFont(FONT_FAMILY_PRIMARY))
        self._numeric.setPixelSize(FONT_SIZE_BASE)
        self._chip_font = tabular(QFont(FONT_FAMILY_PRIMARY))
        self._chip_font.setPixelSize(FONT_SIZE_SM)
        self._chip_font.setWeight(QFont.Weight.DemiBold)
        self._art = pixmap(Icons.TRACK, 14, TEXT_MUTED)
        self._art_missing = pixmap(Icons.WARNING, 14, PRIMARY_ORANGE)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        try:
            from PySide6.QtWidgets import QStyle
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            # La fila entera, no la celda: State_MouseOver sólo marca la celda.
            hovered = getattr(option.widget, "hover_row", -1) == index.row()
            if selected:
                painter.fillRect(option.rect, QColor(SURFACE_4))
                if index.column() == 0:
                    bar = QRect(option.rect.left(), option.rect.top() + 8, 2,
                                option.rect.height() - 16)
                    painter.fillRect(bar, QColor(ACCENT))
            elif hovered:
                painter.fillRect(option.rect, QColor(SURFACE_3))

            track = index.data(Qt.UserRole) or {}
            col = index.column()
            painter.setRenderHint(QPainter.Antialiasing)

            try:
                if col == COL_ARTWORK:
                    self._paint_artwork(painter, option, track)
                elif col == COL_KEY:
                    self._paint_key_chip(painter, option, track)
                elif col == COL_ENERGY:
                    self._paint_energy(painter, option, track)
                else:
                    self._paint_text(painter, option, index, col)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Error in delegate paint: {e}")
        finally:
            painter.restore()

    def _paint_text(self, painter, option, index, col):
        text = index.data(Qt.DisplayRole)
        if text in (None, ""):
            return
        rect = option.rect.adjusted(self.margin, 0, -self.margin, 0)

        if col == COL_TITLE:
            missing = (index.data(Qt.UserRole) or {}).get("missing")
            painter.setPen(QColor(TEXT_MUTED if missing else TEXT_PRIMARY))
            painter.setFont(option.font)
        elif col in (COL_BPM, COL_DURATION):
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.setFont(self._numeric)
        else:  # artist, date
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.setFont(option.font)

        align = index.data(Qt.TextAlignmentRole) or int(Qt.AlignLeft | Qt.AlignVCenter)
        metrics = QFontMetrics(painter.font())
        elided = metrics.elidedText(str(text), Qt.ElideRight, rect.width())
        painter.drawText(rect, align, elided)

    def _paint_artwork(self, painter: QPainter, option: QStyleOptionViewItem, track: dict):
        """Paints a fast thumbnail placeholder."""
        rect = option.rect
        art_size = 28
        x = rect.x() + (rect.width() - art_size) // 2
        y = rect.y() + (rect.height() - art_size) // 2
        art_rect = QRect(x, y, art_size, art_size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(SURFACE_3))
        painter.drawRoundedRect(art_rect, 6, 6)
        art = self._art_missing if track.get("missing") else self._art
        painter.drawPixmap(x + (art_size - 14) // 2, y + (art_size - 14) // 2, art)

    def _paint_key_chip(self, painter: QPainter, option: QStyleOptionViewItem, track: dict):
        """Paints the Camelot key as a colour-coded pill."""
        code = track.get("key")
        if not code or code == "—":
            return
        bg, fg = camelot_qcolors(code)
        metrics = QFontMetrics(self._chip_font)
        w = max(36, metrics.horizontalAdvance(code) + 16)
        h = 20
        cx = option.rect.center().x()
        cy = option.rect.center().y()
        chip = QRect(int(cx - w / 2), int(cy - h / 2), w, h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(chip, 10, 10)
        painter.setPen(fg)
        painter.setFont(self._chip_font)
        painter.drawText(chip, Qt.AlignCenter, code)

    def _paint_energy(self, painter: QPainter, option: QStyleOptionViewItem, track: dict):
        """Paints energy (1..10) as five ascending bars."""
        energy = track.get("energy")
        if energy is None:
            return
        filled = max(0, min(5, round(energy / 2)))
        bar_w, gap = 4, 3
        total_w = 5 * bar_w + 4 * gap
        x0 = option.rect.center().x() - total_w // 2
        base_y = option.rect.center().y() + 8
        painter.setPen(Qt.NoPen)
        for i in range(5):
            bar_h = 5 + i * 2
            r = QRect(x0 + i * (bar_w + gap), base_y - bar_h, bar_w, bar_h)
            painter.setBrush(QColor(ACCENT) if i < filled else QColor(BORDER_DEFAULT))
            painter.drawRoundedRect(r, 1, 1)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        # Fixed row height for consistent performance and rhythm
        return QSize(option.rect.width(), 44)


class WLTrackTable(QTableView):
    """
    Styled table view designed for the Library.
    Incorporates the high-performance model, proxy, and delegate.

    No decide qué hacer con las pistas: avisa que se pidió un menú o un
    borrado, con las pistas seleccionadas, y quien la usa resuelve.
    """
    # pistas seleccionadas (dicts de presentación), posición global del clic
    context_menu_requested = Signal(list, QPoint)
    # pistas seleccionadas, y si además van los archivos a la Papelera
    remove_requested = Signal(list, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_trackTable")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # Core interaction
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.ExtendedSelection)
        self.setEditTriggers(QTableView.NoEditTriggers)
        self.setFocusPolicy(Qt.StrongFocus) # Keyboard navigation

        # Visuals
        self.setAlternatingRowColors(False)
        self.setMouseTracking(True)  # para el hover por fila del delegate
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)

        # Performance
        # El título es la columna que se estira; si además se estira la última,
        # la fecha queda flotando con un hueco a la derecha.
        self.horizontalHeader().setStretchLastSection(False)
        # Fixed row height + resize mode optimizes for large datasets
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(44)

        # Internal wiring
        self._source_model = LibraryTableModel()
        self._proxy_model = LibrarySortFilterProxy()
        self._proxy_model.setSourceModel(self._source_model)

        self.setModel(self._proxy_model)
        self._source_model.dataChanged.connect(lambda *_: self._fit_columns())
        self._source_model.rowsInserted.connect(lambda *_: self._fit_columns())
        self.setItemDelegate(LibraryTableDelegate(self))

        self._configure_columns()

    def _configure_columns(self):
        """Los anchos los calcula ``_fit_columns`` según el espacio disponible."""
        header = self.horizontalHeader()
        header.setMinimumSectionSize(32)
        for c in range(len(HEADERS)):
            header.setSectionResizeMode(c, QHeaderView.Fixed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._fit_columns()

    def _fit_columns(self):
        disponible = self.viewport().width()
        if disponible <= 0:
            return
        anchos = fit_columns(disponible, self._source_model.has_genres())
        for c in range(len(HEADERS)):
            if c in anchos:
                self.setColumnHidden(c, False)
                self.setColumnWidth(c, anchos[c])
            else:
                self.setColumnHidden(c, True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_columns()

    hover_row = -1

    def _on_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        # Clic derecho sobre una fila no seleccionada: se actúa sobre esa fila,
        # como en el Explorador, no sobre la selección anterior.
        if not self.selectionModel().isRowSelected(index.row(), QModelIndex()):
            self.selectRow(index.row())
        tracks = self.get_selected_tracks()
        if tracks:
            self.context_menu_requested.emit(tracks, self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event):
        # Supr quita de la librería; Shift+Supr también manda a la Papelera,
        # igual que en el Explorador de Windows.
        if event.key() == Qt.Key_Delete:
            tracks = self.get_selected_tracks()
            if tracks:
                self.remove_requested.emit(tracks, bool(event.modifiers() & Qt.ShiftModifier))
            return
        super().keyPressEvent(event)

    def remove_tracks(self, track_ids) -> None:
        self._source_model.remove_tracks(track_ids)
        self._fit_columns()

    def mouseMoveEvent(self, event):
        row = self.rowAt(int(event.position().y()))
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def set_tracks(self, tracks: List[Dict[str, Any]]):
        """Populates the table with track data."""
        self._source_model.set_tracks(tracks)
        self._fit_columns()  # la columna Género aparece sólo si hay géneros

    def apply_search(self, query: str):
        """Filters the table based on the search query."""
        # Using wildcard/regex for more flexible search, keeping it simple for now
        self._proxy_model.setFilterRegularExpression(query)

    def get_selected_tracks(self) -> List[Dict[str, Any]]:
        """Returns the raw metadata dicts for all currently selected rows."""
        selected_indexes = self.selectionModel().selectedRows()
        tracks = []
        for proxy_idx in selected_indexes:
            source_idx = self._proxy_model.mapToSource(proxy_idx)
            tracks.append(self._source_model.get_track(source_idx))
        return tracks
