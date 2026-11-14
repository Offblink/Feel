"""进度条：qfluentwidgets Slider + 时间标签 + 书签刻度（FR-12/FR-14）。"""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, Slider, qconfig
from qfluentwidgets.common.color import autoFallbackThemeColor
from qfluentwidgets.components.widgets.slider import SliderHandle

# 槽的两端各留半个手柄宽（22/2）：手柄圆心正好在 x = 11 + ratio*(w-22)，
# 与 fluent 的 _adjustHandlePos / 槽绘制保持一致（取 10 会和点/刻度错 1px）
HANDLE_MARGIN = 11


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
        event.accept()
        self.pressed.emit()

    def mouseReleaseEvent(self, event):
        event.accept()
        self.released.emit()

    def mouseMoveEvent(self, event):
        # 按住手柄拖动：手柄自己拿着鼠标抓取，位移要换算到滑条坐标再改值
        slider = self.parentWidget()
        if slider is not None and event.buttons() & Qt.LeftButton:
            x = self.mapToParent(event.position()).x()
            slider.setValue(slider._x_to_ms(x))
            slider.sliderMoved.emit(slider.value())
        event.accept()

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
        self._pressed = False
        # 换掉 fluent 默认手柄：悬停会放大成白色光圈并“留痕”，只要一个进度点
        self.handle.hide()
        self.handle.setParent(None)
        self.handle.deleteLater()
        self.handle = _DotHandle(self)
        self.handle.pressed.connect(self._on_handle_pressed)
        self.handle.released.connect(self._on_handle_released)
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
        # fluent 的 Slider.mouseMoveEvent 无条件 setValue：鼠标只是划过就把进度点
        # 拖到光标处（用户报「悬停时进度点自己跳」）。进度点只跟随真正按住左键的拖动。
        if self._pressed and event.buttons() & Qt.LeftButton:
            self.setValue(self._x_to_ms(event.position().x()))
            self.sliderMoved.emit(self.value())
            event.accept()
            return
        if not self._pressed:
            self.hovered.emit(self._x_to_ms(event.position().x()),
                              self.mapToGlobal(event.position().toPoint()))
        event.accept()

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
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position().x()
        for mark in self._marks:
            if abs(self._ms_to_x(mark) - pos) <= 6:
                self.bookmarkClicked.emit(mark)
                event.accept()
                return
        # fluent 原实现只 setValue、从不发 sliderReleased，而 SeekBar 只在
        # sliderReleased 里发 seekRequested → 点击进度条根本不 seek（播放中的
        # 下一个 positionChanged 又把点弹回去，用户看到「点了不跳」）。
        # 这里自己接管按下/拖动/松开三路，按下即定位，松开必 seek。
        self._pressed = True
        self.setValue(self._x_to_ms(pos))
        self.sliderPressed.emit()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # 手柄自己拿鼠标抓取，它的 pressed/released 只发信号不会走上面的滑条事件
    def _on_handle_pressed(self) -> None:
        self._pressed = True
        self.sliderPressed.emit()

    def _on_handle_released(self) -> None:
        self._pressed = False
        self.sliderReleased.emit()


class SeekBar(QWidget):
    """进度条 + 时间 + 书签刻度。拖动中不跟随播放位置刷新，释放时才 seek。"""

    seekRequested = Signal(int)
    bookmarkClicked = Signal(int)

    # seek 之后引擎是异步的：旧位置还会推几次 positionChanged，若直接跟随，
    # 进度点会被弹回原处（用户报「点了 15s 点不跳」）。这段时间冻结在目标点，
    # 直到引擎报到接近目标（或超时）为止。
    SEEK_SETTLE_MS = 600
    SEEK_TOLERANCE_MS = 250

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._duration = 0
        self._seek_target: int | None = None
        self._seek_deadline = 0.0

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
        self._seek_target = None
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
        if self._seek_target is not None:
            landed = abs(int(ms) - self._seek_target) <= self.SEEK_TOLERANCE_MS
            if landed or time.monotonic() >= self._seek_deadline:
                self._seek_target = None
            else:
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
        target = self.slider.value()
        self._seek_target = target
        self._seek_deadline = time.monotonic() + self.SEEK_SETTLE_MS / 1000.0
        self.seekRequested.emit(target)

    def _on_value_changed(self, value: int) -> None:
        self.currentLabel.setText(format_time(value))
