"""音量 OSD：画面中央的半透明轻提示（↑/↓ 或滚轮调音量时闪现，约 1 秒后淡出）。

不是 InfoBar：不占窗口顶部、不挡操作，鼠标穿透，只在媒体画面上短暂出现。
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget
from qfluentwidgets import FluentIcon, isDarkTheme, qconfig


def _accent() -> QColor:
    color = qconfig.themeColor.value
    return QColor(color) if color is not None else QColor('#009faa')


class VolumeOsd(QWidget):
    """中央音量提示：图标 + 「音量 N%」+ 细进度条，半透明圆角，自动淡出。"""

    HOLD_MS = 750

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(176, 80)
        self._level = 50
        self._muted = False

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._fade = QPropertyAnimation(self._effect, b'opacity', self)
        self._fade.finished.connect(self._on_fade_finished)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self.hide()

    # ---- 显示 ----
    def show_level(self, level: int, muted: bool = False) -> None:
        self._level = max(0, min(100, int(level)))
        self._muted = bool(muted)
        self.reposition()
        self.update()
        self.show()
        self.raise_()
        self._hide_timer.stop()
        self._hide_timer.start(self.HOLD_MS)
        self._fade.stop()
        self._fade.setDuration(120)
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.start()

    def reposition(self) -> None:
        """居中在画面（stageStack）上；stage 不存在时退回父控件中心。"""
        parent = self.parentWidget()
        if parent is None:
            return
        stage = getattr(parent, 'stageStack', None)
        rect = stage.geometry() if stage is not None else parent.rect()
        self.move(rect.center().x() - self.width() // 2,
                  rect.center().y() - self.height() // 2)

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setDuration(240)
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.InCubic)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()

    # ---- 绘制 ----
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dark = isDarkTheme()

        painter.setPen(Qt.NoPen)
        # 半透明底：深色主题用近黑，浅色主题用近白，不遮住画面细节
        painter.setBrush(QColor(18, 18, 18, 170) if dark else QColor(250, 250, 250, 214))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 14, 14)

        fg = QColor(245, 245, 245) if dark else QColor(28, 28, 28)
        icon = (FluentIcon.MUTE if self._muted else FluentIcon.VOLUME).icon(fg)
        painter.drawPixmap(18, (self.height() - 30) // 2 - 6, icon.pixmap(30, 30))

        font = painter.font()
        font.setPixelSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(fg)
        text = '静音' if self._muted or self._level == 0 else f'音量 {self._level}%'
        painter.drawText(QRect(58, 6, self.width() - 70, 30),
                         Qt.AlignVCenter | Qt.AlignLeft, text)

        # 细音量条（0-100）
        track = QRectF(58, self.height() - 22, self.width() - 76, 5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 46) if dark else QColor(0, 0, 0, 30))
        painter.drawRoundedRect(track, 2.5, 2.5)
        level = 0 if self._muted else self._level
        filled = QRectF(track.left(), track.top(),
                        track.width() * level / 100.0, track.height())
        painter.setBrush(_accent())
        painter.drawRoundedRect(filled, 2.5, 2.5)
