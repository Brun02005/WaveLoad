import os
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QFontMetrics, QPixmap, QPen, QBrush
from PySide6.QtCore import Qt, QRect, QSize, QEvent, Signal, QPoint

from ui.widgets.preview_model import PreviewModel
from ui.theme.colors import (
    ACCENT, SURFACE_3, SURFACE_4, BORDER_SUBTLE, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_INVERSE, PRIMARY_RED,
    STATUS_PENDING, STATUS_VALID, STATUS_DUPLICATE, STATUS_ERROR
)
from ui.theme.icons import Icons, pixmap
from ui.theme.typography import tabular

class PreviewDelegate(QStyledItemDelegate):
    remove_requested = Signal(str)
    # Escuchar antes de descargar: la clave es la URL que resuelve el stream.
    play_requested = Signal(str)
    import_playlist_requested = Signal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_height = 68
        self.margin = 10
        self.thumb_width = 76
        self.thumb_height = 44
        self.icon_size = 24
        
        # Cache for pixmaps
        self._pixmap_cache = {}
        # Lo que está sonando o cargando, para dibujar pausa o espera en esa fila.
        self.playing_key = None
        self.loading_key = None

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), self.item_height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        metadata = index.data(PreviewModel.MetadataRole)
        is_loading = index.data(PreviewModel.IsLoadingRole)
        is_duplicate = index.data(PreviewModel.IsDuplicateRole)
        error_msg = index.data(PreviewModel.ErrorMsgRole)

        rect = option.rect
        if option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor(SURFACE_3))
        painter.setPen(QPen(QColor(BORDER_SUBTLE), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        content_rect = self._content_rect(rect)

        # 1. Miniatura (o un icono que dice qué es)
        thumb_rect = self._thumb_rect(content_rect)
        clip = QPainterPath()
        clip.addRoundedRect(thumb_rect, 6, 6)
        painter.fillPath(clip, QColor(SURFACE_4))

        has_pixmap = False
        if metadata and metadata.get("thumbnail_path"):
            path = metadata["thumbnail_path"]
            if os.path.exists(path):
                if path not in self._pixmap_cache:
                    self._pixmap_cache[path] = QPixmap(path).scaled(
                        self.thumb_width, self.thumb_height,
                        Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                    )
                pm = self._pixmap_cache[path]
                pm_rect = pm.rect()
                pm_rect.moveCenter(thumb_rect.center())
                painter.save()
                painter.setClipPath(clip)
                painter.drawPixmap(pm_rect, pm)
                painter.restore()
                has_pixmap = True

        if not has_pixmap:
            if error_msg:
                glyph, color = Icons.WARNING, PRIMARY_RED
            elif metadata and metadata.get("is_playlist"):
                glyph, color = Icons.PLAYLIST, TEXT_MUTED
            elif is_loading:
                glyph, color = Icons.VIDEO, TEXT_MUTED
            else:
                glyph, color = Icons.TRACK, TEXT_MUTED
            painter.drawPixmap(thumb_rect.center().x() - 9, thumb_rect.center().y() - 9,
                               pixmap(glyph, 18, color))

        # 1b. Botón de escuchar sobre la miniatura, siempre visible en lo que
        # se puede reproducir: sin él no había forma de oír un tema antes de
        # bajarlo.
        key = self.preview_key(index)
        if key:
            hovered = bool(option.state & QStyle.State_MouseOver)
            sonando = key == self.playing_key
            cargando = key == self.loading_key and not sonando
            circle = QRect(thumb_rect.center().x() - 14, thumb_rect.center().y() - 14, 28, 28)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ACCENT) if (hovered or sonando) else QColor(0, 0, 0, 150))
            painter.drawEllipse(circle)
            glyph = Icons.PENDING if cargando else (Icons.PAUSE if sonando else Icons.PLAY)
            color = TEXT_INVERSE if (hovered or sonando) else TEXT_PRIMARY
            painter.drawPixmap(circle.center().x() - 6, circle.center().y() - 6, pixmap(glyph, 12, color))

        # 2. Texto
        text_x = thumb_rect.right() + 14
        text_w = content_rect.right() - text_x - 140

        title_font = QFont(option.font)
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.Medium)
        title_text = "Leyendo enlace…"
        if error_msg:
            title_text = "No se pudo leer el enlace"
        elif metadata:
            title_text = metadata.get("title", "Sin título")
        painter.setFont(title_font)
        painter.setPen(QColor(TEXT_PRIMARY))
        metrics = QFontMetrics(title_font)
        painter.drawText(QRect(text_x, content_rect.center().y() - 19, text_w, 20),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(title_text, Qt.ElideRight, text_w))

        sub_font = tabular(QFont(option.font))
        sub_font.setPixelSize(12)
        detail, detail_color = "", QColor(TEXT_MUTED)
        if error_msg:
            detail, detail_color = error_msg, QColor(PRIMARY_RED)
        elif metadata:
            dur = metadata.get("duration", 0) or 0
            dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}"
            size_mb = metadata.get("estimated_size_mb", 0.0) or 0.0
            uploader = metadata.get("uploader") or ""
            if metadata.get("is_playlist"):
                count = metadata.get("track_count", 0)
                partes = [uploader, f"{count} pistas", dur_str, f"{size_mb:.0f} MB"]
            else:
                partes = [uploader, dur_str, f"{size_mb:.1f} MB"]
            detail = "  ·  ".join(p for p in partes if p)
            if is_duplicate:
                detail = "Ya está en la carpeta  ·  " + detail
                detail_color = QColor(STATUS_DUPLICATE)
        painter.setFont(sub_font)
        painter.setPen(detail_color)
        sub_metrics = QFontMetrics(sub_font)
        painter.drawText(QRect(text_x, content_rect.center().y() + 2, text_w, 18),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         sub_metrics.elidedText(detail, Qt.ElideRight, text_w))

        # 3. Indicador de estado
        if error_msg:
            status_color = QColor(STATUS_ERROR)
        elif is_duplicate:
            status_color = QColor(STATUS_DUPLICATE)
        elif metadata and not is_loading:
            status_color = QColor(STATUS_VALID)
        else:
            status_color = QColor(STATUS_PENDING)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(status_color))
        painter.drawEllipse(QRect(content_rect.right() - 128, content_rect.center().y() - 4, 8, 8))

        # 4. Botones (geometría virtual; ver editorEvent)
        if metadata and metadata.get("is_playlist"):
            import_rect = self._get_import_btn_rect(content_rect)
            painter.setBrush(QBrush(QColor(SURFACE_4)))
            painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
            painter.drawRoundedRect(import_rect, 6, 6)
            painter.setPen(QColor(TEXT_PRIMARY))
            btn_font = QFont(option.font)
            btn_font.setPixelSize(12)
            btn_font.setWeight(QFont.Weight.Medium)
            painter.setFont(btn_font)
            painter.drawText(import_rect, Qt.AlignCenter, "Abrir lista")

        del_rect = self._get_delete_btn_rect(content_rect)
        painter.drawPixmap(del_rect.center().x() - 7, del_rect.center().y() - 7,
                           pixmap(Icons.DELETE, 14, TEXT_SECONDARY))

        painter.restore()

    def _content_rect(self, rect: QRect) -> QRect:
        """Una sola fuente para la geometría: paint y editorEvent la comparten.
        Antes editorEvent la recortaba 5 px más y los clics caían corridos."""
        return rect.adjusted(self.margin + 4, self.margin, -self.margin, -self.margin)

    def _get_delete_btn_rect(self, content_rect: QRect) -> QRect:
        return QRect(content_rect.right() - self.icon_size, content_rect.center().y() - self.icon_size // 2, self.icon_size, self.icon_size)

    def _get_import_btn_rect(self, content_rect: QRect) -> QRect:
        # Placed left of delete button
        w = 84
        h = 26
        return QRect(content_rect.right() - self.icon_size - 10 - w, content_rect.center().y() - h // 2, w, h)

    @staticmethod
    def preview_key(index):
        """La URL que se reproduce para esta fila, o None si no se puede:
        todavía cargando, con error, o una playlist entera."""
        metadata = index.data(PreviewModel.MetadataRole)
        if not metadata or index.data(PreviewModel.IsLoadingRole) or index.data(PreviewModel.ErrorMsgRole):
            return None
        if metadata.get("is_playlist"):
            return None
        return metadata.get("url") or index.data(PreviewModel.UrlRole)

    def _thumb_rect(self, content_rect: QRect) -> QRect:
        return QRect(content_rect.left(), content_rect.center().y() - self.thumb_height // 2,
                     self.thumb_width, self.thumb_height)

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem, index) -> bool:
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            content_rect = self._content_rect(option.rect)
            
            # Escuchar: clic en la miniatura.
            key = self.preview_key(index)
            if key and self._thumb_rect(content_rect).contains(event.pos()):
                self.play_requested.emit(key)
                return True

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
