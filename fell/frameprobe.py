"""视频取帧：cv2 定位到指定毫秒并读出画面（FR-12 悬停预览）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

PREVIEW_W, PREVIEW_H = 160, 90


class FrameGrabber:
    """复用同一个 VideoCapture，按毫秒取帧。"""

    def __init__(self):
        self._cap = None
        self._path: str | None = None

    def frame_at(self, path: str | Path, ms: int) -> QImage | None:
        import cv2

        target = str(path)
        if target != self._path:
            self.release()
            cap = cv2.VideoCapture(target)
            if not cap.isOpened():
                cap.release()
                return None
            self._cap = cap
            self._path = target
        cap = self._cap
        if cap is None:
            return None
        cap.set(cv2.CAP_PROP_POS_MSEC, float(max(0, ms)))
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, _ = rgb.shape
        image = QImage(rgb.data, width, height, rgb.strides[0],
                       QImage.Format_RGB888).copy()
        return image.scaled(PREVIEW_W, PREVIEW_H, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._path = None
