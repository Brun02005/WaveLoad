"""
services/audio_player_service.py
=================================
Single shared audio player for the whole app — local library tracks and
not-yet-downloaded stream previews both go through here, so only one thing
ever plays at a time regardless of which UI surface (context panel,
download card) triggered it.
"""

import logging

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from workers.stream_resolve_worker import StreamResolveWorker

logger = logging.getLogger(__name__)


class AudioPlayerService(QObject):
    resolving_stream = Signal(str)          # key — resolving a stream url
    playback_started = Signal(str)          # key — now playing
    playback_paused = Signal()
    playback_stopped = Signal()
    playback_position_changed = Signal(int)  # ms
    playback_duration_changed = Signal(int)  # ms
    playback_error = Signal(str)            # human-readable message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._current_key: str | None = None

        self._player.positionChanged.connect(lambda ms: self.playback_position_changed.emit(int(ms)))
        self._player.durationChanged.connect(lambda ms: self.playback_duration_changed.emit(int(ms)))
        self._player.errorOccurred.connect(self._on_qt_error)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_local_file(self, path: str) -> None:
        self.stop()
        self._current_key = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def play_url(self, url: str) -> None:
        self.stop()
        self._current_key = url
        self.resolving_stream.emit(url)
        worker = StreamResolveWorker(url)
        worker.signals.resolved.connect(self._on_stream_resolved)
        worker.signals.failed.connect(self._on_stream_resolve_failed)
        QThreadPool.globalInstance().start(worker)

    def toggle_play_pause_for(self, key: str | None, is_local: bool) -> None:
        if not key:
            return
        if key == self._current_key and self._player.source().toString():
            if self.is_playing():
                self.pause()
            else:
                self._player.play()
            return
        if is_local:
            self.play_local_file(key)
        else:
            self.play_url(key)

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()
        self._current_key = None
        self.playback_stopped.emit()

    def seek(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)

    def set_volume(self, volume_0_to_100: int) -> None:
        self._audio_output.setVolume(max(0, min(100, volume_0_to_100)) / 100.0)

    def current_key(self) -> str | None:
        return self._current_key

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_stream_resolved(self, source_key: str, stream_url: str) -> None:
        if source_key != self._current_key:
            return  # user already moved on to something else
        self._player.setSource(QUrl(stream_url))
        self._player.play()

    def _on_stream_resolve_failed(self, source_key: str, error: str) -> None:
        if source_key != self._current_key:
            return
        self._current_key = None
        self.playback_error.emit(error)

    def _on_qt_error(self, error, error_string: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        logger.warning(f"AudioPlayerService playback error: {error_string}")
        self.playback_error.emit(error_string or "Error de reproducción.")

    def _on_playback_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState and self._current_key:
            self.playback_started.emit(self._current_key)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.playback_paused.emit()
