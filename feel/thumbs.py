"""缩略图服务：图片/视频取帧，后台生成并缓存到 %APPDATA%/Feel/thumbs（FR-21）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage, QImageReader

from .config import THUMB_DIR
from .imageio import load_image

THUMB_SIZE = QSize(320, 180)


def cache_path(path: Path) -> Path:
    try:
        stat = path.stat()
        key = hashlib.sha1(
            f'{path}|{stat.st_mtime_ns}|{stat.st_size}|{THUMB_SIZE.width()}x{THUMB_SIZE.height()}'.encode()
        ).hexdigest()
    except OSError:
        key = hashlib.sha1(str(path).encode()).hexdigest()
    return THUMB_DIR / f'{key}.png'


def load_image_thumb(path: Path) -> QImage:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        reader.setScaledSize(size.scaled(THUMB_SIZE, Qt.KeepAspectRatio))
    image = reader.read()
    if not image.isNull():
        return image
    # Qt 解不了的格式（AVIF）走 Pillow 兜底，再缩到缩略图尺寸
    image = load_image(path)
    if image.isNull():
        return image
    return image.scaled(THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def load_video_thumb(path: Path) -> QImage:
    import av

    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            if stream.duration and stream.time_base:
                total = float(stream.duration * stream.time_base)
                target = min(total * 0.1, 1.0)
                try:
                    container.seek(int(target / float(stream.time_base)), stream=stream)
                except Exception:
                    pass
            for frame in container.decode(stream):
                arr = frame.to_ndarray(format='rgb24')
                height, width, _ = arr.shape
                image = QImage(arr.tobytes(), width, height, width * 3,
                               QImage.Format_RGB888).copy()
                return image.scaled(THUMB_SIZE, Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
    except Exception:
        return QImage()
    return QImage()


class _Signals(QObject):
    done = Signal(str, QImage)


class _ThumbTask(QRunnable):
    def __init__(self, path: Path, kind: str, signals: _Signals):
        super().__init__()
        self.path = path
        self.kind = kind
        self.signals = signals

    def run(self) -> None:
        image = QImage()
        try:
            # 缓存命中也在工作线程里读：千张卡片的 PNG 解码不能压在 UI 线程上
            cache = cache_path(self.path)
            if cache.exists():
                image = QImage(str(cache))
            if image.isNull():
                if self.kind == 'image':
                    image = load_image_thumb(self.path)
                elif self.kind == 'video':
                    image = load_video_thumb(self.path)
                if not image.isNull():
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    image.save(str(cache), 'PNG')
        except Exception:
            image = QImage()
        self.signals.done.emit(str(self.path), image)


class ThumbnailService(QObject):
    """按路径请求缩略图，完成时发 ready(path, QImage)。"""

    ready = Signal(str, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(3)
        self._inflight: set[str] = set()
        self._signals: list[_Signals] = []

    def request(self, path: Path, kind: str) -> None:
        key = str(path)
        if kind not in ('image', 'video') or key in self._inflight:
            return
        signals = _Signals(self)
        signals.done.connect(self._on_done)
        self._signals.append(signals)
        self._inflight.add(key)
        self._pool.start(_ThumbTask(path, kind, signals))

    def _on_done(self, key: str, image: QImage) -> None:
        self._inflight.discard(key)
        if not image.isNull():
            self.ready.emit(key, image)

    def wait_idle(self, msec: int = 5000) -> bool:
        return self._pool.waitForDone(msec)
