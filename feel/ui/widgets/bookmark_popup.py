"""书签输入浮层（FR-14）：播放页右侧弹出，输入内容后保存（时间 + 内容）。

点「保存」→ `submitted(label)`；点「取消」/Esc → `cancelled()`，这次书签不落库。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)

from .seek_bar import format_time

POPUP_W = 300


class BookmarkPopup(QWidget):
    """右侧书签输入框：携带触发时的播放位置，保存/取消后关闭。"""

    submitted = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pos_ms = 0
        self.setFixedWidth(POPUP_W)
        self._build_ui()
        self.setFixedHeight(self.sizeHint().height())
        self.hide()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.titleLabel = StrongBodyLabel('添加书签', self)
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.setFixedSize(24, 24)
        head.addWidget(self.titleLabel, 1)
        head.addWidget(self.closeBtn)

        self.timeLabel = CaptionLabel('00:00', self)
        self.timeLabel.setToolTip('书签位置（打开输入框时的播放时间）')

        self.edit = LineEdit(self)
        self.edit.setPlaceholderText('书签内容，例如：副歌 / 关键帧')
        self.edit.setClearButtonEnabled(True)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.cancelBtn = PushButton('取消', self)
        self.saveBtn = PrimaryPushButton('保存', self)
        buttons.addWidget(self.cancelBtn)
        buttons.addWidget(self.saveBtn)

        root.addLayout(head)
        root.addWidget(self.timeLabel)
        root.addWidget(self.edit)
        root.addLayout(buttons)

        self.edit.returnPressed.connect(self.submit)
        self.edit.installEventFilter(self)
        self.closeBtn.clicked.connect(self.cancel)
        self.cancelBtn.clicked.connect(self.cancel)
        self.saveBtn.clicked.connect(self.submit)

    # ---- 状态 ----
    @property
    def position_ms(self) -> int:
        return self._pos_ms

    def prompt(self, pos_ms: int) -> None:
        """在右侧弹出输入框，绑定当前播放位置。"""
        self._pos_ms = max(0, int(pos_ms))
        self.timeLabel.setText(format_time(self._pos_ms))
        self.edit.clear()
        self.place()
        self.show()
        self.raise_()
        self.edit.setFocus()

    def place(self) -> None:
        page = self.parentWidget()
        if page is None:
            return
        stage = getattr(page, 'stageStack', None)
        top = stage.y() if stage is not None else 0
        self.move(max(0, page.width() - self.width() - 24), top + 20)

    # ---- 动作 ----
    def submit(self) -> None:
        label = self.edit.text().strip()
        self.hide()
        self.submitted.emit(label)

    def cancel(self) -> None:
        self.hide()
        self.cancelled.emit()

    # ---- 事件 ----
    def eventFilter(self, obj, event):
        if obj is self.edit:
            # Esc 不归 QLineEdit 处理，会被全局「退出全屏」QShortcut 抢走；
            # 这里先接受 ShortcutOverride，让 Esc 落回输入框并关闭本浮层。
            if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Escape:
                event.accept()
                return True
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.cancel()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dark = isDarkTheme()
        painter.setPen(QPen(QColor(255, 255, 255, 34) if dark else QColor(0, 0, 0, 20), 1))
        painter.setBrush(QColor(38, 38, 38, 250) if dark else QColor(252, 252, 252, 252))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
