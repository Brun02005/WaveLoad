"""
ui/shell/player_bar.py
======================
La barra del reproductor: fija abajo de la ventana, visible desde cualquier
pantalla.

Antes no había un lugar que mostrara qué estaba sonando: para pausar había
que volver a la pista y abrir su panel de detalles. La barra aparece la primera
vez que algo suena y se queda hasta que el usuario la cierra.

No reproduce nada por su cuenta: refleja y controla a ``AudioPlayerService``,
que es el único reproductor de la app.
"""

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QSlider, QStyle, QStyleOptionSlider, QVBoxLayout, QWidget,
)

from ui.components.buttons import WLIconButton
from ui.theme.colors import (
    ACCENT, BORDER_SUBTLE, PRIMARY_RED, SURFACE_1, SURFACE_3, TEXT_INVERSE, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.theme.icons import Icons, pixmap
from ui.theme.typography import tabular

_SETTINGS = ("WaveLoad", "WaveLoad5")


def _mmss(ms: int) -> str:
    s = max(0, int(ms) // 1000)
    return f"{s // 60}:{s % 60:02d}"


class SeekSlider(QSlider):
    """Un QSlider que salta adonde se hace clic.

    El de Qt avanza de a un "page step" hacia el clic, así que para ir a un
    punto del tema había que agarrar la bolita y arrastrarla. Acá el clic
    mueve la bolita a ese punto y, si se mantiene apretado, sigue arrastrando
    desde ahí.
    """

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() > self.minimum():
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
            handle = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
            if not handle.contains(event.position().toPoint()):
                x = int(event.position().x()) - groove.x() - handle.width() // 2
                span = groove.width() - handle.width()
                value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), x, max(1, span), opt.upsideDown
                )
                self.setValue(value)
                self.sliderMoved.emit(value)
        # Con la bolita ya bajo el cursor, Qt toma el clic como inicio de
        # arrastre: sliderPressed ahora, sliderReleased al soltar.
        super().mousePressEvent(event)


class PlayerBar(QWidget):
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self._dragging = False
        self._duration = 0
        self._subtitle = ""
        self._volume_before_mute = 80

        self.setObjectName("wl_playerBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(68)
        self.setStyleSheet(
            f"#wl_playerBar {{ background-color: {SURFACE_1}; border-top: 1px solid {BORDER_SUBTLE}; }}"
        )
        self._build()
        self._connect()
        self.setVisible(False)

    # --- construcción ------------------------------------------------------

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 12, 0)
        row.setSpacing(12)

        # Qué suena
        self.art = QLabel()
        self.art.setFixedSize(42, 42)
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setStyleSheet(f"background-color: {SURFACE_3}; border-radius: 8px;")
        row.addWidget(self.art)

        textos = QVBoxLayout()
        textos.setSpacing(1)
        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 500;")
        self.lbl_subtitle = QLabel("")
        self.lbl_subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        textos.addStretch()
        textos.addWidget(self.lbl_title)
        textos.addWidget(self.lbl_subtitle)
        textos.addStretch()
        info = QWidget()
        info.setFixedWidth(260)
        info.setLayout(textos)
        row.addWidget(info)

        # Transporte
        self.btn_play = WLIconButton(Icons.PLAY, size=36, icon_px=16, color=TEXT_INVERSE)
        self.btn_play.setObjectName("wl_playBtn")
        self.btn_play.setStyleSheet(
            f"#wl_playBtn {{ background-color: {ACCENT}; border-radius: 18px; border: none; }}"
            f"#wl_playBtn:disabled {{ background-color: {SURFACE_3}; }}"
        )
        self.btn_play.setToolTip("Reproducir / pausar")
        row.addWidget(self.btn_play)

        self.lbl_pos = QLabel("0:00")
        self.lbl_dur = QLabel("0:00")
        for etiqueta in (self.lbl_pos, self.lbl_dur):
            etiqueta.setFont(tabular(etiqueta.font()))
            etiqueta.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
            etiqueta.setFixedWidth(40)
        self.lbl_pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider = SeekSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setToolTip("Hacé clic o arrastrá para moverte en el tema")
        row.addWidget(self.lbl_pos)
        row.addWidget(self.slider, 1)
        row.addWidget(self.lbl_dur)

        # Volumen y cerrar
        row.addSpacing(8)
        self.btn_mute = WLIconButton(Icons.VOLUME, size=30, icon_px=16, tooltip="Silenciar")
        row.addWidget(self.btn_mute)
        self.volume = SeekSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(96)
        row.addWidget(self.volume)
        row.addSpacing(4)
        self.btn_close = WLIconButton(Icons.CLOSE, size=30, icon_px=15,
                                      tooltip="Detener y cerrar el reproductor")
        row.addWidget(self.btn_close)

        guardado = QSettings(*_SETTINGS).value("volume", 80)
        try:
            inicial = max(0, min(100, int(guardado)))
        except (TypeError, ValueError):
            inicial = 80
        self.volume.setValue(inicial)
        self.player.set_volume(inicial)

    def _connect(self):
        p = self.player
        p.now_playing_changed.connect(self._on_now_playing)
        p.resolving_stream.connect(lambda _k: self._set_loading(True))
        p.playback_started.connect(self._on_started)
        p.playback_paused.connect(lambda: self._set_playing(False))
        p.playback_stopped.connect(lambda: self._set_playing(False))
        p.playback_position_changed.connect(self._on_position)
        p.playback_duration_changed.connect(self._on_duration)
        p.playback_error.connect(self._on_error)

        self.btn_play.clicked.connect(p.toggle_current)
        self.btn_close.clicked.connect(self._on_close)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.volume.valueChanged.connect(self._on_volume)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.slider.sliderReleased.connect(self._on_seek)
        self.slider.sliderMoved.connect(lambda v: self.lbl_pos.setText(_mmss(v)))

    # --- reflejo del reproductor ---------------------------------------------

    def _on_now_playing(self, key: str, title: str, subtitle: str, is_local: bool):
        from pathlib import PureWindowsPath  # noqa: PLC0415
        nombre = title or (PureWindowsPath(key).stem if is_local else "Vista previa")
        self._subtitle = subtitle or ("Librería" if is_local else "Vista previa · sin descargar")
        metrics = self.lbl_title.fontMetrics()
        self.lbl_title.setText(metrics.elidedText(nombre, Qt.ElideRight, 256))
        self.lbl_title.setToolTip(nombre)
        self.lbl_subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.lbl_subtitle.setText(self._subtitle)
        self.art.setPixmap(pixmap(Icons.TRACK if is_local else Icons.VIDEO, 18, TEXT_SECONDARY))
        self._duration = 0
        self.slider.setRange(0, 0)
        self.lbl_pos.setText("0:00")
        self.lbl_dur.setText("0:00")
        self._set_loading(not is_local)
        self.setVisible(True)

    def _set_loading(self, loading: bool):
        if loading:
            self.lbl_subtitle.setText("Cargando vista previa…")
        self.btn_play.setEnabled(not loading)
        self.slider.setEnabled(not loading)

    def _on_started(self, _key: str):
        self._set_loading(False)
        self.lbl_subtitle.setText(self._subtitle)
        self._set_playing(True)

    def _set_playing(self, playing: bool):
        self.btn_play.set_icon(Icons.PAUSE if playing else Icons.PLAY, TEXT_INVERSE)

    def _on_duration(self, ms: int):
        self._duration = ms
        self.slider.setRange(0, max(0, ms))
        self.lbl_dur.setText(_mmss(ms))

    def _on_position(self, ms: int):
        if self._dragging:
            return
        self.slider.setValue(ms)
        self.lbl_pos.setText(_mmss(ms))

    def _on_seek(self):
        self._dragging = False
        self.player.seek(self.slider.value())

    def _on_error(self, message: str):
        self._set_loading(False)
        self._set_playing(False)
        self.btn_play.setEnabled(False)
        self.lbl_subtitle.setStyleSheet(f"color: {PRIMARY_RED}; font-size: 12px;")
        self.lbl_subtitle.setText(f"No se pudo reproducir: {message}")
        self.lbl_subtitle.setToolTip(message)

    # --- controles --------------------------------------------------------------

    def _on_volume(self, value: int):
        self.player.set_volume(value)
        self.btn_mute.set_icon(Icons.VOLUME_OFF if value == 0 else Icons.VOLUME)
        QSettings(*_SETTINGS).setValue("volume", value)

    def _toggle_mute(self):
        if self.volume.value() > 0:
            self._volume_before_mute = self.volume.value()
            self.volume.setValue(0)
        else:
            self.volume.setValue(self._volume_before_mute or 80)

    def _on_close(self):
        self.player.stop()
        self.setVisible(False)
