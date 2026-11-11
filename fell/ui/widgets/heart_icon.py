"""心形图标：实心/描边两种状态（qfluentwidgets 只带描边 HEART）。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _heart_path(rect: QRectF) -> QPainterPath:
    w, h = rect.width(), rect.height()
    cx = rect.left() + w / 2
    top = rect.top()
    path = QPainterPath()
    path.moveTo(cx, top + h * 0.95)
    path.cubicTo(rect.left() - w * 0.10, top + h * 0.55,
                 rect.left() + w * 0.10, top,
                 cx, top + h * 0.28)
    path.cubicTo(rect.right() - w * 0.10, top,
                 rect.right() + w * 0.10, top + h * 0.55,
                 cx, top + h * 0.95)
    path.closeSubpath()
    return path


def heart_pixmap(color: QColor, size: int = 16, filled: bool = False) -> QPixmap:
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(scale)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    path = _heart_path(QRectF(1.5, 1.0, size - 3.0, size - 2.0))
    if filled:
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
    else:
        painter.setPen(QPen(color, 1.4))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    painter.end()
    return pixmap


def heart_icon(color: QColor, size: int = 16, filled: bool = False) -> QIcon:
    return QIcon(heart_pixmap(color, size, filled))
