"""进度条：qfluentwidgets Slider + 时间标签 + 书签刻度（FR-12/FR-14）。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, Slider, qconfig
from qfluentwidgets.common.color import autoFallbackThemeColor
from qfluentwidgets.components.widgets.slider import SliderHandle

HANDLE_MARGIN = 10


class _DotHandle(SliderHandle):
    """只画当前进度点：不带悬停/按压时放大的白色光圈。

    用户明确要求进度条上始终只有一个点，鼠标经过不留任何绘制。
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._radius = 5

    def enterEvent(self, event):
        pass

    def leaveEvent(self, event):
        pass

    def mousePressEvent(self, event):
        self.pressed.emit()

    def mouseReleaseEvent(self, event):
        self.released.emit()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(autoFallbackThemeColor(self.lightHandleColor, self.darkHandleColor))
        painter.drawEllipse(QPoint(11, 11), self._radius, self._radius)


def format_time(ms: int) -> str:
    """毫秒 → 00:00 / 1:02:03。"""
    if ms is None or ms < 0:
        ms = 0
    total = int(ms // 1000)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{seconds:02d}'
    return f'{minutes:02d}:{seconds:02d}'


def _accent() -> QColor:
    color = qconfig.themeColor.value
    return QColor(color) if color is not None else QColor('#009faa')


class BookmarkSlider(Slider):
    """带书签刻度的进度滑条：点击刻度跳转，悬停发位置（FR-12）。"""

    bookmarkClicked = Signal(int)
    hovered = Signal(int, QPoint)
    hoverLeft = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOrientation(Qt.Horizontal)
        self.setFixedHeight(28)
        self.setMouseTracking(True)
        self._marks: list[int] = []
        # 换掉 fluent 默认手柄：悬停会放大成白色光圈并“留痕”，只要一个进度点
        self.handle.hide()
        self.handle.setParent(None)
        self.handle.deleteLater()
        self.handle = _DotHandle(self)
        self.handle.pressed.connect(self.sliderPressed)
        self.handle.released.connect(self.sliderReleased)
        self._adjustHandlePos()

    def set_marks(self, positions: list[int]) -> None:
        self._marks = [int(p) for p in positions]
        self.update()

    def _x_to_ms(self, x: float) -> int:
        maximum = max(1, self.maximum())
        usable = max(1, self.width() - 2 * HANDLE_MARGIN)
        ratio = (x - HANDLE_MARGIN) / usable
        return int(min(1.0, max(0.0, ratio)) * maximum)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if not self.isSliderDown():
            self.hovered.emit(self._x_to_ms(event.position().x()),
                              self.mapToGlobal(event.position().toPoint()))

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hoverLeft.emit()

    def _ms_to_x(self, ms: int) -> float:
        maximum = max(1, self.maximum())
        usable = max(1, self.width() - 2 * HANDLE_MARGIN)
        ratio = min(1.0, max(0.0, ms / maximum))
        return HANDLE_MARGIN + usable * ratio

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._marks:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_accent())
        for mark in self._marks:
            x = self._ms_to_x(mark)
            painter.drawRoundedRect(QRectF(x - 1.5, 6, 3, 9), 1.5, 1.5)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().x()
            for mark in self._marks:
                if abs(self._ms_to_x(mark) - pos) <= 6:
                    self.bookmarkClicked.emit(mark)
                    event.accept()
                    return
        super().mousePressEvent(event)


class SeekBar(QWidget):
    """进度条 + 时间 + 书签刻度。拖动中不跟随播放位置刷新，释放时才 seek。"""

    seekRequested = Signal(int)
    bookmarkClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._duration = 0

        self.currentLabel = CaptionLabel('00:00', self)
        self.slider = BookmarkSlider(self)
        self.slider.setRange(0, 0)
        self.totalLabel = CaptionLabel('00:00', self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.currentLabel)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.totalLabel)

        self.slider.sliderPressed.connect(self._on_pressed)
        self.slider.sliderReleased.connect(self._on_released)
        self.slider.valueChanged.connect(self._on_value_changed)
        self.slider.bookmarkClicked.connect(self.bookmarkClicked.emit)

    # ---- 对外 ----
    def reset(self) -> None:
        self._duration = 0
        self._dragging = False
        self.slider.setRange(0, 0)
        self.slider.setValue(0)
        self.currentLabel.setText('00:00')
        self.totalLabel.setText('00:00')

    def set_duration(self, ms: int) -> None:
        self._duration = max(0, int(ms))
        self.slider.setRange(0, self._duration)
        self.totalLabel.setText(format_time(self._duration))

    def set_position(self, ms: int) -> None:
        if self._dragging:
            return
        self.slider.setValue(max(0, min(self._duration, int(ms))))
        self.currentLabel.setText(format_time(ms))

    def set_bookmarks(self, positions: list[int]) -> None:
        self.slider.set_marks(positions)

    # ---- 内部 ----
    def _on_pressed(self) -> None:
        self._dragging = True

    def _on_released(self) -> None:
        self._dragging = False
        self.seekRequested.emit(self.slider.value())

    def _on_value_changed(self, value: int) -> None:
        self.currentLabel.setText(format_time(value))
