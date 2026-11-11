"""主题切换的径向渐变揭示过渡（FR-15/SPEC §5.5）。"""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class ThemeTransitionOverlay(QWidget):
    """盖住窗口的旧主题快照，用扩张的圆形镂空揭示新主题。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self._pixmap: QPixmap | None = None
        self._progress = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(360)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_value)
        self._animation.finished.connect(self.deleteLater)
        self.hide()

    def play(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self._animation.start()

    def _on_value(self, value) -> None:
        self._progress = float(value)
        self.update()

    def paintEvent(self, _event):
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        max_radius = math.hypot(self.width() / 2, self.height() / 2)
        radius = max_radius * self._progress
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.drawEllipse(self.rect().center(), int(radius), int(radius))
