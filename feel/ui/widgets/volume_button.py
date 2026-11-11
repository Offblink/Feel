"""音量按钮：悬停弹出垂直滑块，滚轮调音量（FR-06）。

qfluentwidgets 的 TransparentToolButton 使用重载构造器，子类化会触发递归，
因此这里用组合：外层 QWidget 持有按钮，事件过滤转发悬停/滚轮。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, TransparentToolButton, isDarkTheme, qconfig


def _accent() -> QColor:
    color = qconfig.themeColor.value
    return QColor(color) if color is not None else QColor('#009faa')


class VerticalVolumeSlider(QWidget):
    """自绘垂直音量滑条（0-100）。"""

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 50
        self.setFixedSize(30, 120)
        self.setCursor(Qt.PointingHandCursor)

    def value(self) -> int:
        return self._value

    def set_value(self, value: int, emit: bool = True) -> None:
        value = max(0, min(100, int(value)))
        if value == self._value:
            return
        self._value = value
        self.update()
        if emit:
            self.valueChanged.emit(value)

    def _track_rect(self) -> QRectF:
        return QRectF(self.width() / 2 - 2, 8, 4, self.height() - 16)

    def _value_to_y(self, value: int) -> float:
        track = self._track_rect()
        return track.bottom() - (track.height() * value / 100.0)

    def _y_to_value(self, y: float) -> int:
        track = self._track_rect()
        ratio = (track.bottom() - y) / track.height()
        return round(max(0.0, min(1.0, ratio)) * 100)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.set_value(self._y_to_value(event.position().y()))

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.set_value(self._y_to_value(event.position().y()))

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.set_value(self._value + (5 if delta > 0 else -5))
            event.accept()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = self._track_rect()
        dark = isDarkTheme()

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 45) if dark else QColor(0, 0, 0, 35))
        painter.drawRoundedRect(track, 2, 2)

        y = self._value_to_y(self._value)
        filled = QRectF(track.left(), y, track.width(), track.bottom() - y)
        painter.setBrush(_accent())
        painter.drawRoundedRect(filled, 2, 2)

        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(QPen(_accent(), 2))
        painter.drawEllipse(QPointF(track.center().x(), y), 6, 6)


class VolumePopup(QWidget):
    """悬停弹层：圆角卡片 + 垂直滑条。"""

    def __init__(self, owner: 'VolumeButton'):
        # 不用 Qt.Popup：Popup 会抢鼠标抓取，悬停出弹层后滚轮落在音量按钮上会被
        # 重定向丢弃（用户实测「只有在上方圆框里滚才管用」）。Tool 窗口不抢抓取，
        # 再用既有的 leave/定时器负责收起。
        super().__init__(owner.window(),
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._owner = owner
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(4)
        self.slider = VerticalVolumeSlider(self)
        layout.addWidget(self.slider, 0, Qt.AlignCenter)
        self.slider.valueChanged.connect(self._owner._apply_volume)
        self.setFixedSize(48, 168)

    def set_value(self, value: int) -> None:
        self.slider.set_value(value, emit=False)
        self.update()

    def wheelEvent(self, event):
        # Qt.Popup 会抓走鼠标：悬停出弹层后，滚轮落在音量按钮上也到不了按钮，
        # 统一在这里转给 owner（弹层本身、按钮位置都能滚）。
        self._owner._handle_wheel(event)

    def enterEvent(self, event):
        self._owner.cancel_hide()

    def leaveEvent(self, event):
        self._owner.schedule_hide()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dark = isDarkTheme()
        painter.setPen(QPen(QColor(255, 255, 255, 28) if dark else QColor(0, 0, 0, 18), 1))
        painter.setBrush(QColor(40, 40, 40, 235) if dark else QColor(252, 252, 252, 240))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)

        # 音量数字（0~100）：颜色跟主题走，画在滑条下方
        painter.setPen(QColor(255, 255, 255, 235) if dark else QColor(30, 30, 30, 235))
        font = painter.font()
        font.setPointSizeF(9.5)
        painter.setFont(font)
        painter.drawText(
            QRectF(2, self.height() - 24, self.width() - 4, 18),
            Qt.AlignCenter, str(self.slider.value()),
        )


class VolumeButton(QWidget):
    """音量按钮（组合式）：内层 Fluent 按钮 + 悬停弹层 + 滚轮。"""

    volumeChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._volume = 80
        self._step = 5
        self.setFixedSize(40, 40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._button = TransparentToolButton(FluentIcon.VOLUME, self)
        self._button.setFixedSize(40, 40)
        layout.addWidget(self._button)
        self._button.installEventFilter(self)

        self._popup = VolumePopup(self)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(300)
        self._hide_timer.timeout.connect(self._maybe_hide)
        self._update_tooltip()

    # ---- 数值 ----
    @property
    def volume(self) -> int:
        return self._volume

    def set_step(self, step: int) -> None:
        self._step = max(1, int(step))
        self._update_tooltip()

    def set_volume(self, volume: int) -> None:
        """外部同步音量（不触发 volumeChanged）。"""
        self._volume = max(0, min(100, int(volume)))
        self._popup.set_value(self._volume)
        self._update_tooltip()

    def _apply_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        if volume == self._volume:
            return
        self._volume = volume
        self._popup.set_value(self._volume)
        self._update_tooltip()
        self.volumeChanged.emit(self._volume)

    def _update_tooltip(self) -> None:
        text = f'音量 {self._volume}%（悬停拖动 / 滚轮 / ↑↓）'
        self.setToolTip(text)
        self._button.setToolTip(text)

    # ---- 事件 ----
    def eventFilter(self, obj, event):
        if obj is self._button:
            if event.type() == QEvent.Enter:
                if self.isEnabled():
                    self._show_popup()
            elif event.type() == QEvent.Leave:
                self.schedule_hide()
            elif event.type() == QEvent.Wheel:
                self._handle_wheel(event)
                return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        self._handle_wheel(event)

    def _handle_wheel(self, event) -> None:
        if not self.isEnabled():
            return
        delta = event.angleDelta().y()
        if delta:
            self._apply_volume(self._volume + (self._step if delta > 0 else -self._step))
            event.accept()

    def enterEvent(self, event):
        if self.isEnabled():
            self._show_popup()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.schedule_hide()
        super().leaveEvent(event)

    def _show_popup(self) -> None:
        self.cancel_hide()
        size = self._popup.size()
        pos = self.mapToGlobal(QPoint(self.width() // 2 - size.width() // 2,
                                      -size.height() - 6))
        self._popup.move(pos)
        self._popup.show()
        self._popup.raise_()

    def schedule_hide(self) -> None:
        self._hide_timer.start()

    def cancel_hide(self) -> None:
        self._hide_timer.stop()

    def _maybe_hide(self) -> None:
        if self.underMouse() or self._popup.underMouse():
            return
        self._popup.hide()

    def hideEvent(self, event):
        self._popup.hide()
        super().hideEvent(event)
