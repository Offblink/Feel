"""进度条悬停小浮层：只显示该时刻的帧画面（音频不弹浮层，避免和进度点抢位置）。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

POPUP_W, POPUP_H = 180, 108


class FramePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(POPUP_W, POPUP_H)
        self._image: QImage | None = None
        self.hide()

    def set_content(self, image: QImage | None) -> None:
        self._image = image
        self.update()

    def show_at(self, global_pos: QPoint) -> None:
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 10
        self.move(x, y)
        self.show()
        self.raise_()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.setBrush(QColor(24, 24, 24, 235))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)

        if self._image is not None:
            scaled = self._image.scaled(
                self.width() - 16, self.height() - 16,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawImage(x, y, scaled)
