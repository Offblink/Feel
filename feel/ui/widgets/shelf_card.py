"""资料库卡片：缩略图/音频占位 + 文件名 + 选中态 + 内联重命名（FR-21/22/20）。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLineEdit, QWidget
from qfluentwidgets import FluentIcon, isDarkTheme, qconfig
from ...actions import display_sequence
from .heart_icon import heart_pixmap

CARD_W, CARD_H = 184, 168
THUMB_H = 116


def _accent() -> QColor:
    color = qconfig.themeColor.value
    return QColor(color) if color is not None else QColor('#009faa')


def _tinted_pixmap(icon, color: QColor, size: int) -> QPixmap:
    """FluentIcon.icon(color) 对部分图标忽略颜色（实测 EDIT/DELETE 恒为黑），
    这里用 SourceIn 自己染色，深色主题下才有浅色图标。"""
    base = icon.icon().pixmap(size, size)
    tinted = QPixmap(base.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, base)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return tinted


class ShelfCard(QWidget):
    """一个媒体文件卡片。"""

    clicked = Signal(object, object)  # (entry, modifiers)
    openRequested = Signal(object)
    renameRequested = Signal(object, str)
    deleteRequested = Signal(object)
    favoriteToggled = Signal(object)

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.selected = False
        self.favorite = False
        self._thumb: QPixmap | None = None
        self._hover = False
        self._edit: QLineEdit | None = None
        self.setFixedHeight(CARD_H)
        self.setFixedWidth(CARD_W)
        self.setMouseTracking(True)
        self.setToolTip(str(entry.path))

    # ---- 尺寸（资料库按窗口宽度均分）----
    def set_card_width(self, width: int) -> None:
        width = max(120, int(width))
        if width == self.width():
            return
        self.setFixedWidth(width)
        if self._edit is not None:
            self._edit.setGeometry(8, CARD_H - 30, width - 16, 24)
        self.update()

    # ---- 缩略图 ----
    def set_thumbnail(self, image: QImage) -> None:
        self._thumb = QPixmap.fromImage(image)
        self.update()

    @property
    def has_thumbnail(self) -> bool:
        return self._thumb is not None

    def set_favorite(self, favorite: bool) -> None:
        if favorite != self.favorite:
            self.favorite = favorite
            self.update()

    def _heart_rect(self) -> QRectF:
        return QRectF(self.width() - 32, 6, 26, 26)

    def _rename_rect(self) -> QRectF:
        return QRectF(8, 6, 24, 24)

    def _delete_rect(self) -> QRectF:
        return QRectF(34, 6, 24, 24)

    def _shows_actions(self) -> bool:
        return self._hover and self._edit is None

    def clear_hover(self) -> None:
        self._hover = False
        self.update()

    def set_selected(self, selected: bool) -> None:
        if selected != self.selected:
            self.selected = selected
            self.update()

    # ---- 交互 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._edit is None:
            position = event.position()
            if self._heart_rect().contains(position):
                self.favoriteToggled.emit(self.entry)
                event.accept()
                return
            if self._shows_actions() and self._delete_rect().contains(position):
                self.deleteRequested.emit(self.entry)
                event.accept()
                return
            if self._shows_actions() and self._rename_rect().contains(position):
                self.start_rename()
                event.accept()
                return
            self.clicked.emit(self.entry, event.modifiers())
            event.accept()

    def _action_key(self, action_id: str, default: str) -> str:
        """动作当前键位（帮助页改过键就显示新键）；窗口没建好时退回默认。"""
        registry = getattr(self.window(), 'registry', None)
        if registry is not None and action_id in registry.actions:
            sequences = registry.action(action_id).shortcuts()
            if sequences:
                return ' / '.join(display_sequence(s) for s in sequences)
        return default

    def mouseMoveEvent(self, event):
        position = event.position()
        if self._shows_actions() and self._delete_rect().contains(position):
            self.setToolTip('移入回收站')
        elif self._shows_actions() and self._rename_rect().contains(position):
            self.setToolTip(f'重命名（{self._action_key("rename_selected", "F2")}）')
        elif self._heart_rect().contains(position):
            self.setToolTip(
                f'收藏 / 取消收藏（{self._action_key("favorite", "E")}）'
            )
        else:
            self.setToolTip(str(self.entry.path))
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            position = event.position()
            on_action = (self._heart_rect().contains(position)
                         or (self._shows_actions()
                             and (self._delete_rect().contains(position)
                                  or self._rename_rect().contains(position))))
            if not on_action:
                self.openRequested.emit(self.entry)
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
        open_action = Action('打开', menu)
        open_action.triggered.connect(lambda: self.openRequested.emit(self.entry))
        rename_action = Action('重命名', menu)
        rename_action.triggered.connect(self.start_rename)
        delete_action = Action('删除', menu)
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(self.entry))
        menu.addActions([open_action, rename_action, delete_action])
        menu.exec(event.globalPos())

    # ---- 内联重命名 ----
    def start_rename(self) -> None:
        if self._edit is not None:
            return
        self._edit_stem = self.entry.path.stem
        edit = QLineEdit(self)
        edit.setText(self.entry.path.stem)
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
            self.renameRequested.emit(self.entry, new_stem)

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
        painter.drawPixmap(int(rect.center().x() - 6.5), int(rect.center().y() - 6.5),
                           pixmap)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dark = isDarkTheme()

        bg = QColor(255, 255, 255, 14) if dark else QColor(255, 255, 255)
        border = QColor(255, 255, 255, 24) if dark else QColor(0, 0, 0, 16)
        if self._hover:
            bg = QColor(255, 255, 255, 22) if dark else QColor(250, 250, 250)
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        width = self.width()
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1, CARD_H - 1), 8, 8)

        # 缩略图区
        thumb_rect = QRectF(8, 8, width - 16, THUMB_H - 8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 26) if dark else QColor(0, 0, 0, 12))
        painter.drawRoundedRect(thumb_rect, 6, 6)

        if self._thumb is not None:
            scaled = self._thumb.scaled(
                int(thumb_rect.width()) - 4, int(thumb_rect.height()) - 4,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = thumb_rect.center().x() - scaled.width() / 2
            y = thumb_rect.center().y() - scaled.height() / 2
            painter.drawPixmap(int(x), int(y), scaled)
        elif self.entry.kind == 'audio':
            icon = FluentIcon.MUSIC.icon().pixmap(48, 48)
            painter.drawPixmap(
                int(thumb_rect.center().x() - 24), int(thumb_rect.center().y() - 24), icon
            )
        else:
            icon = FluentIcon.PHOTO.icon().pixmap(40, 40)
            painter.drawPixmap(
                int(thumb_rect.center().x() - 20), int(thumb_rect.center().y() - 20), icon
            )

        # 悬停操作：重命名 / 删除（左上），收藏（右上）
        if self._shows_actions():
            # 两个主题都用深色半透明圆底 + 浅色图标：深色模式不再出现黑图标黑圆底
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
            QColor(255, 255, 255, 190) if dark else QColor(60, 60, 60, 150)
        )
        pixmap = heart_pixmap(tint, 15, self.favorite)
        painter.drawPixmap(int(heart.center().x() - 7.5),
                           int(heart.center().y() - 7.5), pixmap)

        # 文件名
        if self._edit is None:
            metrics = QFontMetrics(self.font())
            text = metrics.elidedText(
                self.entry.path.name, Qt.ElideMiddle, width - 20
            )
            painter.setPen(QColor(255, 255, 255) if dark else QColor(20, 20, 20))
            painter.setFont(self.font())
            painter.drawText(
                QRectF(10, CARD_H - 36, width - 20, 28),
                Qt.AlignCenter, text,
            )

        # 选中描边
        if self.selected:
            painter.setPen(QPen(_accent(), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(1, 1, width - 2, CARD_H - 2), 8, 8)
