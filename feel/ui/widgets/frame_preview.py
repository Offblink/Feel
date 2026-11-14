"""进度条悬停小浮层：该时刻的帧画面 + 底部时间（音频不弹浮层，避免和进度点抢位置）。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .seek_bar import format_time

POPUP_W, POPUP_H = 180, 132
TIME_BAR_H = 24


class FramePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(POPUP_W, POPUP_H)
        self._image: QImage | None = None
        self._time_ms = 0
        self.hide()

    def set_content(self, image: QImage | None, ms: int = 0) -> None:
        self._image = image
        self._time_ms = max(0, int(ms))
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

        # 圆角裁切：底部时间条要贴着圆角走，不能从四角戳出去
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        painter.setClipPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(24, 24, 24, 235))
        painter.drawRect(self.rect())

        if self._image is not None:
            img_h = self.height() - TIME_BAR_H
            scaled = self._image.scaled(
                self.width() - 16, img_h - 16,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (img_h - scaled.height()) // 2
            painter.drawImage(x, y, scaled)

        # 底部时间条：该时刻的播放进度（几分几秒；超过 1 小时带小时）
        bar = QRectF(0, self.height() - TIME_BAR_H, self.width(), TIME_BAR_H)
        painter.fillRect(bar, QColor(0, 0, 0, 110))
        painter.setClipping(False)
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)

        font = painter.font()
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(235, 235, 235, 240))
        painter.drawText(bar, Qt.AlignCenter, format_time(self._time_ms))
