"""文件夹卡：资料库子目录的导航与选择（FR-27，2026-11-16 二轮起 = 文件类型）。

当成一种文件类型：与 ShelfCard 同格同高、可涂抹/全选选中（F2 改名、Del 删除、♥ 收藏），
单击进入；无缩略图区。组内顺序由扫描排序决定，卡片墙里恒文件夹在前。
拖拽落点已随三轮调整移除（拖拽移入整体砍掉，移入只走 F7）。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QWidget
from qfluentwidgets import FluentIcon, isDarkTheme

from .heart_icon import heart_pixmap
from .shelf_card import CARD_H, _accent, _tinted_pixmap


class FolderCard(QWidget):
    """当前目录下的一个子目录卡片。"""

    clicked = Signal(object, object)          # (folder, modifiers)
    renameRequested = Signal(object, str)     # (folder, new_stem)
    deleteRequested = Signal(object)          # (folder,)
    favoriteToggled = Signal(object)          # (folder,)

    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.selected = False
        self.favorite = False
        self._hover = False
        self._edit: QLineEdit | None = None
        self._edit_stem = ''
        self.setFixedHeight(CARD_H)
        self.setFixedWidth(184)
        self.setMouseTracking(True)
        self.setToolTip(str(folder))

    @property
    def path(self) -> Path:
        return self.folder

    # ---- 尺寸（与媒体卡同一套均分列宽）----
    def set_card_width(self, width: int) -> None:
        width = max(120, int(width))
        if width != self.width():
            self.setFixedWidth(width)
            if self._edit is not None:
                self._edit.setGeometry(8, CARD_H - 30, width - 16, 24)
            self.update()

    # ---- 选中 / 收藏 ----
    def set_selected(self, selected: bool) -> None:
        if selected != self.selected:
            self.selected = selected
            self.update()

    def set_favorite(self, favorite: bool) -> None:
        if favorite != self.favorite:
            self.favorite = favorite
            self.update()

    def clear_hover(self) -> None:
        self._hover = False
        self.update()

    # ---- 命中区（与 ShelfCard 同坐标）----
    def _heart_rect(self) -> QRectF:
        return QRectF(self.width() - 32, 6, 26, 26)

    def _rename_rect(self) -> QRectF:
        return QRectF(8, 6, 24, 24)

    def _delete_rect(self) -> QRectF:
        return QRectF(34, 6, 24, 24)

    def _shows_actions(self) -> bool:
        return self._hover and self._edit is None

    # ---- 交互 ----
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._edit is not None:
            return
        position = event.position()
        if self._heart_rect().contains(position):
            self.favoriteToggled.emit(self.folder)
            event.accept()
            return
        if self._shows_actions() and self._delete_rect().contains(position):
            self.deleteRequested.emit(self.folder)
            event.accept()
            return
        if self._shows_actions() and self._rename_rect().contains(position):
            self.start_rename()
            event.accept()
            return
        self.clicked.emit(self.folder, event.modifiers())
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            position = event.position()
            on_action = (self._heart_rect().contains(position)
                         or (self._shows_actions()
                             and (self._delete_rect().contains(position)
                                  or self._rename_rect().contains(position))))
            if not on_action:
                self.clicked.emit(self.folder, Qt.NoModifier)
            event.accept()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def contextMenuEvent(self, event):
        from qfluentwidgets import Action, RoundMenu

        menu = RoundMenu(parent=self)
        rename_action = Action('重命名', menu)
        rename_action.triggered.connect(self.start_rename)
        delete_action = Action('删除', menu)
        delete_action.triggered.connect(
            lambda: self.deleteRequested.emit(self.folder))
        menu.addActions([rename_action, delete_action])
        menu.exec(event.globalPos())

    # ---- 内联重命名（与 ShelfCard 同款）----
    def start_rename(self) -> None:
        if self._edit is not None:
            return
        self._edit_stem = self.folder.name
        edit = QLineEdit(self)
        edit.setText(self.folder.name)
        edit.setGeometry(8, CARD_H - 30, self.width() - 16, 24)
        edit.setAlignment(Qt.AlignCenter)
        edit.selectAll()
        edit.returnPressed.connect(self._commit_rename)
        edit.editingFinished.connect(self._commit_rename)
        edit.installEventFilter(self)
        self._edit = edit
        edit.setFocus()
        edit.show()

    def eventFilter(self, obj, event):
        if obj is self._edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._cancel_rename()
                return True
        return super().eventFilter(obj, event)

    def _commit_rename(self) -> None:
        if self._edit is None:
            return
        new_stem = self._edit.text().strip()
        self._cancel_rename()
        if new_stem and new_stem != self._edit_stem:
            self.renameRequested.emit(self.folder, new_stem)

    def _cancel_rename(self) -> None:
        if self._edit is None:
            return
        self._edit.deleteLater()
        self._edit = None
        self.update()

    # ---- 绘制 ----
    def _draw_action_circle(self, painter, rect: QRectF, icon, tint: QColor,
                            background: QColor | None = None) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(background or QColor(0, 0, 0, 70))
        painter.drawEllipse(rect)
        pixmap = _tinted_pixmap(icon, tint, 13)
        painter.drawPixmap(int(rect.center().x() - 6.5),
                           int(rect.center().y() - 6.5), pixmap)

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

        # 悬停操作：重命名 / 删除（左上），收藏（右上）——与媒体卡同一套坐标
        if self._shows_actions():
            circle = QColor(0, 0, 0, 96)
            self._draw_action_circle(painter, self._rename_rect(), FluentIcon.EDIT,
                                     QColor(250, 250, 250, 235), circle)
            self._draw_action_circle(painter, self._delete_rect(), FluentIcon.DELETE,
                                     QColor(255, 150, 150, 245), circle)
        heart = self._heart_rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawEllipse(heart)
        tint = _accent() if self.favorite else (
            QColor(255, 255, 255, 190) if dark else QColor(60, 60, 60, 150))
        pixmap = heart_pixmap(tint, 15, self.favorite)
        painter.drawPixmap(int(heart.center().x() - 7.5),
                           int(heart.center().y() - 7.5), pixmap)

        # 名称（内联改名时让位给输入框）
        if self._edit is None:
            metrics = QFontMetrics(self.font())
            text = metrics.elidedText(self.folder.name, Qt.ElideMiddle, width - 20)
            painter.setPen(QColor(255, 255, 255) if dark else QColor(20, 20, 20))
            painter.setFont(self.font())
            painter.drawText(QRectF(10, CARD_H - 36, width - 20, 28),
                             Qt.AlignCenter, text)

        if self.selected:
            painter.setPen(QPen(_accent(), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(1, 1, width - 2, CARD_H - 2), 8, 8)
