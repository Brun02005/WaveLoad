import os
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPixmap, QPen, QBrush
from PySide6.QtCore import Qt, QRect, QSize, QEvent, Signal, QPoint

from ui.widgets.preview_model import PreviewModel
from ui.theme.colors import (
    SURFACE_BASE, SURFACE_4, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY, PRIMARY_RED, PRIMARY_GREEN,
    STATUS_PENDING, STATUS_VALID, STATUS_DUPLICATE, STATUS_ERROR
)

class PreviewDelegate(QStyledItemDelegate):
    remove_requested = Signal(str)
    import_playlist_requested = Signal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_height = 70
        self.margin = 10
        self.thumb_width = 80
        self.thumb_height = 50
        self.icon_size = 24
        
        # Cache for pixmaps
        self._pixmap_cache = {}

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), self.item_height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Get data
        url = index.data(PreviewModel.UrlRole)
        metadata = index.data(PreviewModel.MetadataRole)
        is_loading = index.data(PreviewModel.IsLoadingRole)
        is_duplicate = index.data(PreviewModel.IsDuplicateRole)
        error_msg = index.data(PreviewModel.ErrorMsgRole)

        # Draw Background
        rect = option.rect
        
        # Hover state
        if option.state & QStyle.State_MouseOver:
            bg_color = QColor(SURFACE_4)
        else:
            bg_color = QColor("transparent")

        painter.fillRect(rect, bg_color)
        
        # Bottom separator line
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # Content Rect
        content_rect = rect.adjusted(self.margin, self.margin, -self.margin, -self.margin)

        # 1. Thumbnail
        thumb_rect = QRect(content_rect.left(), content_rect.top(), self.thumb_width, self.thumb_height)
        painter.setBrush(QBrush(QColor(SURFACE_BASE)))
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
        painter.drawRoundedRect(thumb_rect, 2, 2)

        has_pixmap = False
        if metadata and metadata.get("thumbnail_path"):
            path = metadata["thumbnail_path"]
            if os.path.exists(path):
                if path not in self._pixmap_cache:
                    pm = QPixmap(path).scaled(self.thumb_width, self.thumb_height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    self._pixmap_cache[path] = pm
                
                pm = self._pixmap_cache[path]
                # Center pixmap inside thumb_rect
                pm_rect = pm.rect()
                pm_rect.moveCenter(thumb_rect.center())
                # Clip to rounded rect
                painter.save()
                path_clip = painter.clipPath()
                painter.setClipRect(thumb_rect)
                painter.drawPixmap(pm_rect, pm)
                painter.restore()
                has_pixmap = True

        if not has_pixmap:
            painter.setPen(QColor(TEXT_PRIMARY))
            font = painter.font()
            font.setPixelSize(20)
            painter.setFont(font)
            if error_msg:
                icon_text = "⚠️"
            elif metadata and metadata.get("is_playlist"):
                icon_text = "📁"
            elif is_loading:
                icon_text = "🎥"
            else:
                icon_text = "🎵"
            painter.drawText(thumb_rect, Qt.AlignCenter, icon_text)

        # 2. Text (Title, Uploader, Duration)
        text_x = thumb_rect.right() + 12
        text_w = content_rect.right() - text_x - 120 # Leave space for buttons and status

        # Title
        title_font = painter.font()
        title_font.setPixelSize(13)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(TEXT_PRIMARY))
        
        title_text = "Cargando información..."
        if error_msg:
            title_text = "Error al analizar enlace"
        elif metadata:
            title_text = metadata.get("title", "Desconocido")
            
        metrics = QFontMetrics(title_font)
        elided_title = metrics.elidedText(title_text, Qt.ElideRight, text_w)
        painter.drawText(QRect(text_x, content_rect.top(), text_w, 20), Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        # Subtitle (Uploader & Duration)
        sub_font = painter.font()
        sub_font.setPixelSize(11)
        sub_font.setBold(False)
        painter.setFont(sub_font)
        
        uploader_text = "YOUTUBE"
        dur_text = "—"
        dur_color = QColor(TEXT_SECONDARY)
        
        if error_msg:
            uploader_text = "YOUTUBE SERVER"
            dur_text = f"Causa: {error_msg}"
            dur_color = QColor(PRIMARY_RED)
        elif metadata:
            uploader_text = str(metadata.get("uploader", "CANAL")).upper()
            dur = metadata.get("duration", 0)
            minutes = int(dur // 60)
            seconds = int(dur % 60)
            dur_str = f"{minutes:02d}:{seconds:02d}"
            size_mb = metadata.get("estimated_size_mb", 0.0)
            
            if metadata.get("is_playlist"):
                count = metadata.get("track_count", 0)
                dur_text = f"{count} VIDEOS | TOTAL: {dur_str} | EST: {size_mb:.1f} MB"
                dur_color = QColor(PRIMARY_GREEN)
            else:
                dur_text = f"{dur_str} ({size_mb:.1f} MB)"

        # Draw Uploader
        painter.setPen(QColor(TEXT_SECONDARY))
        uploader_rect = QRect(text_x, content_rect.top() + 24, text_w // 2, 16)
        painter.drawText(uploader_rect, Qt.AlignLeft | Qt.AlignVCenter, metrics.elidedText(uploader_text, Qt.ElideRight, uploader_rect.width()))
        
        # Draw Duration
        painter.setPen(dur_color)
        sub_font.setBold(True)
        painter.setFont(sub_font)
        dur_rect = QRect(text_x + text_w // 2, content_rect.top() + 24, text_w // 2, 16)
        painter.drawText(dur_rect, Qt.AlignLeft | Qt.AlignVCenter, dur_text)

        # 3. Status Indicator
        status_color = QColor(STATUS_PENDING) # pending
        if error_msg:
            status_color = QColor(STATUS_ERROR) # error
        elif is_duplicate:
            status_color = QColor(STATUS_ERROR) # Treat as error or custom duplicate color if we have one. Oh, we don't import STATUS_DUPLICATE. Wait, let's import it.
            # Wait, let's see. Yes, STATUS_DUPLICATE is imported. Let's use QColor(STATUS_DUPLICATE)!
        elif metadata and not is_loading:
            status_color = QColor(STATUS_VALID) # valid

        # Wait, let's write:
        # if is_duplicate: status_color = QColor(STATUS_DUPLICATE)
        # Yes, let's do it exactly:
        if is_duplicate:
            status_color = QColor(STATUS_DUPLICATE)

        indicator_rect = QRect(content_rect.right() - 80, content_rect.center().y() - 5, 10, 10)
        painter.setBrush(QBrush(status_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(indicator_rect)

        # 4. Buttons (Virtual geometry)
        # Import Button
        if metadata and metadata.get("is_playlist"):
            import_rect = self._get_import_btn_rect(content_rect)
            painter.setBrush(QBrush(QColor(SURFACE_4)))
            painter.setPen(QPen(QColor(PRIMARY_GREEN), 1))
            painter.drawRoundedRect(import_rect, 2, 2)
            painter.setPen(QColor(PRIMARY_GREEN))
            painter.setFont(sub_font)
            painter.drawText(import_rect, Qt.AlignCenter, "IMPORTAR")

        # Delete Button (✕)
        del_rect = self._get_delete_btn_rect(content_rect)
        painter.setPen(QColor(TEXT_SECONDARY))
        del_font = painter.font()
        del_font.setPixelSize(12)
        del_font.setBold(True)
        painter.setFont(del_font)
        painter.drawText(del_rect, Qt.AlignCenter, "✕")

        painter.restore()

    def _get_delete_btn_rect(self, content_rect: QRect) -> QRect:
        return QRect(content_rect.right() - self.icon_size, content_rect.center().y() - self.icon_size // 2, self.icon_size, self.icon_size)

    def _get_import_btn_rect(self, content_rect: QRect) -> QRect:
        # Placed left of delete button
        w = 60
        h = 24
        return QRect(content_rect.right() - self.icon_size - 10 - w, content_rect.center().y() - h // 2, w, h)

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem, index) -> bool:
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            content_rect = option.rect.adjusted(5, 5, -5, -5).adjusted(self.margin, self.margin, -self.margin, -self.margin)
            
            # Check Delete button click
            del_rect = self._get_delete_btn_rect(content_rect)
            if del_rect.contains(event.pos()):
                url = index.data(PreviewModel.UrlRole)
                self.remove_requested.emit(url)
                return True

            # Check Import button click
            metadata = index.data(PreviewModel.MetadataRole)
            if metadata and metadata.get("is_playlist"):
                import_rect = self._get_import_btn_rect(content_rect)
                if import_rect.contains(event.pos()):
                    url = index.data(PreviewModel.UrlRole)
                    entries = metadata.get("entries", [])
                    self.import_playlist_requested.emit(url, entries)
                    return True

        return super().editorEvent(event, model, option, index)
