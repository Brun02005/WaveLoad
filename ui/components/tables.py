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
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QRect, QSize
)
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics

from ui.theme.colors import (
    SURFACE_1, SURFACE_3, SURFACE_4, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER_SUBTLE, BORDER_DEFAULT, ACCENT,
)
from ui.theme.typography import FONT_FAMILY_MONO, FONT_SIZE_BASE, FONT_SIZE_SM
from ui.theme.icons import Icons


# Column Indices — focused DJ-crate layout: identity + the mixing essentials.
COL_ARTWORK = 0
COL_TITLE = 1
COL_ARTIST = 2
COL_BPM = 3
COL_KEY = 4
COL_ENERGY = 5
COL_DURATION = 6
COL_DATE = 7

HEADERS = [
    "", "Título", "Artista", "BPM", "Key", "Energía", "Duración", "Añadido"
]


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

        if role == Qt.DisplayRole:
            if col == COL_TITLE: return track.get("title", "")
            elif col == COL_ARTIST: return track.get("artist", "")
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
        self._mono = QFont(FONT_FAMILY_MONO)
        self._mono.setPixelSize(FONT_SIZE_BASE)
        self._chip_font = QFont(FONT_FAMILY_MONO)
        self._chip_font.setPixelSize(FONT_SIZE_SM)
        self._chip_font.setWeight(QFont.Weight.DemiBold)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        try:
            from PySide6.QtWidgets import QStyle
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            if selected:
                # Subtle teal-tinted selection with an accent bar on the left edge.
                painter.fillRect(option.rect, QColor(SURFACE_3))
                bar = QRect(option.rect.left(), option.rect.top(), 2, option.rect.height())
                painter.fillRect(bar, QColor(ACCENT))

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
            painter.setPen(QColor(TEXT_PRIMARY))
            painter.setFont(option.font)
        elif col in (COL_BPM, COL_DURATION):
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.setFont(self._mono)
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
        art_size = 30
        x = rect.x() + (rect.width() - art_size) // 2
        y = rect.y() + (rect.height() - art_size) // 2
        art_rect = QRect(x, y, art_size, art_size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(SURFACE_1))
        painter.drawRoundedRect(art_rect, 5, 5)
        painter.setPen(QColor(TEXT_MUTED))
        painter.drawText(art_rect, Qt.AlignCenter, Icons.TRACK)

    def _paint_key_chip(self, painter: QPainter, option: QStyleOptionViewItem, track: dict):
        """Paints the Camelot key as a colour-coded pill."""
        code = track.get("key")
        if not code or code == "—":
            return
        bg, fg = camelot_qcolors(code)
        metrics = QFontMetrics(self._chip_font)
        w = max(34, metrics.horizontalAdvance(code) + 16)
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
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wl_trackTable")
        
        # Core interaction
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.ExtendedSelection)
        self.setEditTriggers(QTableView.NoEditTriggers)
        self.setFocusPolicy(Qt.StrongFocus) # Keyboard navigation
        
        # Visuals
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)
        
        # Performance
        self.horizontalHeader().setStretchLastSection(True)
        # Fixed row height + resize mode optimizes for large datasets
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(44)
        
        # Internal wiring
        self._source_model = LibraryTableModel()
        self._proxy_model = LibrarySortFilterProxy()
        self._proxy_model.setSourceModel(self._source_model)
        
        self.setModel(self._proxy_model)
        self.setItemDelegate(LibraryTableDelegate(self))
        
        self._configure_columns()

    def _configure_columns(self):
        """Sets optimal initial widths for columns."""
        header = self.horizontalHeader()
        header.setMinimumSectionSize(40)

        self.setColumnWidth(COL_ARTWORK, 48)
        self.setColumnWidth(COL_TITLE, 260)   # stretched
        self.setColumnWidth(COL_ARTIST, 180)
        self.setColumnWidth(COL_BPM, 64)
        self.setColumnWidth(COL_KEY, 64)
        self.setColumnWidth(COL_ENERGY, 72)
        self.setColumnWidth(COL_DURATION, 76)
        self.setColumnWidth(COL_DATE, 96)

        header.setSectionResizeMode(COL_ARTWORK, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_ARTIST, QHeaderView.Interactive)
        for c in (COL_BPM, COL_KEY, COL_ENERGY, COL_DURATION, COL_DATE):
            header.setSectionResizeMode(c, QHeaderView.Fixed)

    def set_tracks(self, tracks: List[Dict[str, Any]]):
        """Populates the table with track data."""
        self._source_model.set_tracks(tracks)

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
