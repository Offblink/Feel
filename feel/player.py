"""Qt6 QMediaPlayer 封装（FFmpeg 后端，见 SPEC 附录 A）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class MediaEngine(QObject):
    """播放引擎：暂停/继续、进度、音量、结束/错误信号。"""

    positionChanged = Signal(int)
    durationChanged = Signal(int)
    playingChanged = Signal(bool)
    mediaEnded = Signal()
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._volume = 80
        self._pause_on_ready = False
        self._pause_scheduled = False
        self._audio.setVolume(self._volume / 100.0)
        self._player.positionChanged.connect(lambda v: self.positionChanged.emit(int(v)))
        self._player.durationChanged.connect(lambda v: self.durationChanged.emit(int(v)))
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)

    # ---- 输出 ----
    def set_video_output(self, item) -> None:
        """挂/摘视频输出（传 None 摘除）。

        Qt6 FFmpeg 下，纯音频播放还挂着 QGraphicsVideoItem 时，一次全局 QSS
        刷新会死锁（本机实测，可稳定复现）；因此非视频媒体一律摘掉 video sink。
        """
        self._player.setVideoOutput(item)

    # ---- 装载 ----
    def load(self, path: str | Path) -> None:
        # Qt6 FFmpeg 后端：直接切换 source 时旧管线未完全释放，
        # 视频 -> 音频切换会死锁（实测）。先 release 让后端收尾再装载。
        self.release()
        self._pause_on_ready = False
        self._player.setSource(QUrl.fromLocalFile(str(path)))

    def load_paused(self, path: str | Path) -> None:
        """装载后停在 0:00（首帧），用于单曲播完复位。

        FFmpeg 后端在 Loading 期间 pause() 会被就绪后的自播覆盖，所以等
        LoadedMedia/BufferedMedia 再压一次 pause + setPosition(0)。
        """
        self.release()
        self._pause_on_ready = True
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.pause()

    def release(self) -> None:
        """停止并等待后端真正释放文件句柄（删除/换源前调用）。

        没有 source 时后端无事可等：直接返回，避免每次打开文件白等 120ms。
        """
        if self._player.source().isEmpty():
            return
        self.stop()
        loop = QEventLoop()
        QTimer.singleShot(120, loop.quit)
        loop.exec()

    def stop(self) -> None:
        # 本机 Qt6 FFmpeg 后端：seek 之后调用 QMediaPlayer.stop() 会死锁（实测），
        # pause() + setSource(QUrl()) 能安全释放管线。
        self._player.pause()
        self._player.setSource(QUrl())

    # ---- 控制 ----
    def play(self) -> None:
        self._pause_on_ready = False
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def seek(self, ms: int) -> None:
        self._player.setPosition(max(0, int(ms)))

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self._audio.setVolume(self._volume / 100.0)

    def set_playback_rate(self, rate: float) -> None:
        """播放速度倍率（Qt6 FFmpeg 后端实测支持 0.5×–2×，音频同步变调变速）。"""
        self._player.setPlaybackRate(float(rate))

    @property
    def playback_rate(self) -> float:
        return float(self._player.playbackRate())

    # ---- 状态 ----
    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlayingState

    @property
    def position(self) -> int:
        return self._player.position()

    @property
    def duration(self) -> int:
        return self._player.duration()

    @property
    def volume(self) -> int:
        return self._volume

    # ---- 信号转发 ----
    def _on_state_changed(self, state) -> None:
        self.playingChanged.emit(state == QMediaPlayer.PlayingState)

    def _on_media_status(self, status) -> None:
        if self._pause_on_ready and status in (
            QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia
        ):
            # 保持标志直到用户显式 play()：FFmpeg 后端可能在多次 status 之后才自播。
            # 不在 status 回调里同步改播放器状态（会重入，实测可崩），延后一拍做。
            self._schedule_pause_at_start()
        if status == QMediaPlayer.EndOfMedia:
            self.mediaEnded.emit()

    def _schedule_pause_at_start(self) -> None:
        if self._pause_scheduled:
            return
        self._pause_scheduled = True
        QTimer.singleShot(0, self._pause_at_start)

    def _pause_at_start(self) -> None:
        self._pause_scheduled = False
        if not self._pause_on_ready or self._player.source().isEmpty():
            return
        self._player.pause()
        self._player.setPosition(0)

    def _on_error(self, _error, message: str) -> None:
        self.errorOccurred.emit(message or '播放失败')
