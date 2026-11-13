"""图片舞台：居中显示 + 放大后拖动平移（FR-08）。

拖动只改绘制原点并裁剪到视口，不重新缩放位图 —— 放大后平移不掉画质。
`pixmap()` 仍是缩放后的完整位图，缩放/旋转逻辑与旧 QLabel 行为一致。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel


class ImageStage(QLabel):
    """可拖动的图片舞台。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(1, 1)
        self._pan = QPointF(0.0, 0.0)
        self._drag_origin: QPointF | None = None
        self._drag_pan = QPointF(0.0, 0.0)

    # ---- 平移状态 ----
    @property
    def pan(self) -> QPointF:
        return QPointF(self._pan)

    def pan_limits(self) -> tuple[float, float]:
        """当前位图相对视口在 x/y 上可平移的最大绝对值（<=0 表示方向已铺满）。"""
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return 0.0, 0.0
        return (max(0.0, (pixmap.width() - self.width()) / 2),
                max(0.0, (pixmap.height() - self.height()) / 2))

    def reset_pan(self) -> None:
        self._pan = QPointF(0.0, 0.0)
        self.sync_cursor()
        self.update()

    def set_pan(self, x: float, y: float) -> None:
        self._pan = QPointF(x, y)
        self.clamp_pan()
        # 必须无条件重绘：clamp_pan 只在「钳位改变值」时 update，
        # 边界内拖动会改 _pan 却不刷新 → 画面冻结（表现为只能沿贴边那轴拖）
        self.update()

    def clamp_pan(self) -> None:
        """边界约束：放大后的图最多拖到边缘贴住视口，不能拖出空白。"""
        limit_x, limit_y = self.pan_limits()
        x = min(max(self._pan.x(), -limit_x), limit_x)
        y = min(max(self._pan.y(), -limit_y), limit_y)
        if x != self._pan.x() or y != self._pan.y():
            self._pan = QPointF(x, y)
            self.update()

    def sync_cursor(self) -> None:
        can_pan = self.pan_limits()[0] > 0.5 or self.pan_limits()[1] > 0.5
        self.setCursor(Qt.OpenHandCursor if can_pan else Qt.ArrowCursor)

    # ---- 拖动 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._can_pan():
            self._drag_origin = event.position()
            self._drag_pan = QPointF(self._pan)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            delta = event.position() - self._drag_origin
            self.set_pan(self._drag_pan.x() + delta.x(),
                         self._drag_pan.y() + delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_origin is not None and event.button() == Qt.LeftButton:
            self._drag_origin = None
            self.sync_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _can_pan(self) -> bool:
        limit_x, limit_y = self.pan_limits()
        return limit_x > 0.5 or limit_y > 0.5

    # ---- 绘制 ----
    def paintEvent(self, event):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        x = (self.width() - pixmap.width()) / 2 + self._pan.x()
        y = (self.height() - pixmap.height()) / 2 + self._pan.y()
        painter.drawPixmap(QPointF(x, y), pixmap)
