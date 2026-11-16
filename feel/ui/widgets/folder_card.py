"""文件夹卡：资料库子目录的导航与拖拽落点（FR-27 / FR-32）。

与 ShelfCard 同格同高（进同一网格、参与均分列宽），但纯导航：
单击进入、无 ♥、无悬停改名/删除、不参与涂抹选择。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon, isDarkTheme

from .shelf_card import CARD_H, _accent


class FolderCard(QWidget):
    """当前目录下的一个子目录卡片。"""

    clicked = Signal()

    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.folder = folder
        self._hover = False
        self._drop_active = False
        self.setFixedHeight(CARD_H)
        self.setFixedWidth(184)
        self.setMouseTracking(True)
        self.setToolTip(str(folder))

    # ---- 尺寸（与媒体卡同一套均分列宽）----
    def set_card_width(self, width: int) -> None:
        width = max(120, int(width))
        if width != self.width():
            self.setFixedWidth(width)
            self.update()

    # ---- 拖拽落点高亮 ----
    def set_drop_active(self, active: bool) -> None:
        if active != self._drop_active:
            self._drop_active = active
            self.update()

    # ---- 交互：单击即进入（与媒体卡单击打开同节奏，忽略修饰键）----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dark = isDarkTheme()

        bg = QColor(255, 255, 255, 14) if dark else QColor(255, 255, 255)
        border = QColor(255, 255, 255, 24) if dark else QColor(0, 0, 0, 16)
        if self._hover:
            bg = QColor(255, 255, 255, 22) if dark else QColor(250, 250, 250)
        width = self.width()
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1, CARD_H - 1), 8, 8)

        # 文件夹图标（.icon() 走 Theme.AUTO，深浅主题自动取色）
        icon = FluentIcon.FOLDER.icon().pixmap(44, 44)
        painter.drawPixmap(int(width / 2 - 22), int((CARD_H - 36) / 2 - 22), icon)

        # 名称（与媒体卡同位置，省略号居中裁剪）
        metrics = QFontMetrics(self.font())
        text = metrics.elidedText(self.folder.name, Qt.ElideMiddle, width - 20)
        painter.setPen(QColor(255, 255, 255) if dark else QColor(20, 20, 20))
        painter.setFont(self.font())
        painter.drawText(QRectF(10, CARD_H - 36, width - 20, 28),
                         Qt.AlignCenter, text)

        if self._drop_active:
            painter.setPen(QPen(_accent(), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(1, 1, width - 2, CARD_H - 2), 8, 8)
