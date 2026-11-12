"""播放页右侧抽屉：播放列表 / 书签 / 文件信息（FR-14，I 键开关）。"""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    RoundMenu,
    SegmentedWidget,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
)

DRAWER_WIDTH = 300


class Drawer(QWidget):
    """滑入式详情抽屉。"""

    openIndexRequested = Signal(int)
    bookmarkSelected = Signal(int)
    bookmarkDeleteRequested = Signal(int)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(DRAWER_WIDTH)
        self._target_visible = False
        self._animation = QPropertyAnimation(self, b'geometry', self)
        self._animation.setDuration(180)
        self._animation.finished.connect(self._on_animation_finished)
        self._build_ui()
        self.hide()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        self.titleLabel = StrongBodyLabel('详情', self)
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.setFixedSize(28, 28)
        head.addWidget(self.titleLabel, 1)
        head.addWidget(self.closeBtn)

        self.tabs = SegmentedWidget(self)
        self.tabs.addItem('playlist', '播放列表')
        self.tabs.addItem('bookmarks', '书签')
        self.tabs.addItem('info', '文件信息')
        self.tabs.setCurrentItem('playlist')

        self.stack = QStackedWidget(self)
        self.playlist = QListWidget(self)
        self.bookmarks = QListWidget(self)
        self.bookmarks.setContextMenuPolicy(Qt.CustomContextMenu)
        self.info = QWidget(self)
        self.infoLayout = QVBoxLayout(self.info)
        self.infoLayout.setContentsMargins(0, 4, 0, 0)
        self.infoLayout.setSpacing(12)
        self.infoLayout.setAlignment(Qt.AlignTop)
        for widget in (self.playlist, self.bookmarks):
            widget.setStyleSheet(
                'QListWidget{background:transparent;border:none}'
                'QListWidget::item{padding:6px 4px;border-radius:4px}'
            )
        self._apply_list_style()
        qconfig.themeChangedFinished.connect(self._apply_list_style)
        self.stack.addWidget(self.playlist)
        self.stack.addWidget(self.bookmarks)
        self.stack.addWidget(self.info)

        root.addLayout(head)
        root.addWidget(self.tabs)
        root.addWidget(self.stack, 1)

        self.tabs.currentItemChanged.connect(self._on_tab_changed)
        self.closeBtn.clicked.connect(self.hide_drawer)
        self.playlist.itemClicked.connect(self._on_playlist_clicked)
        self.bookmarks.itemClicked.connect(self._on_bookmark_clicked)
        self.bookmarks.customContextMenuRequested.connect(self._on_bookmark_menu)

    # ---------------- 数据 ----------------
    def set_playlist(self, entries, current_index: int) -> None:
        key = (
            len(entries),
            entries[0].path if entries else None,
            entries[-1].path if entries else None,
        )
        current = current_index if 0 <= current_index < len(entries) else -1
        self.playlist.setCurrentRow(-1)
        self.playlist.clearSelection()
        if key != getattr(self, '_playlist_key', None):
            self._playlist_key = key
            self._playlist_entries = list(entries)
            self._playlist_current = -1
            self.playlist.clear()
            for index in range(len(entries)):
                item = QListWidgetItem('')
                item.setData(Qt.UserRole, index)
                self.playlist.addItem(item)
            for index in range(len(entries)):
                self._style_playlist_item(index, index == current)
            self._playlist_current = current
            if self.isVisible():
                # 列表被重建会把滚动位置清零：开着抽屉时补滚回当前文件
                self._scroll_to_current()
            return
        previous = getattr(self, '_playlist_current', -1)
        if current != previous:
            for index in (previous, current):
                if 0 <= index < self.playlist.count():
                    self._style_playlist_item(index, index == current)
            self._playlist_current = current

    def _style_playlist_item(self, index: int, current: bool) -> None:
        """当前项用「▶ + 加粗」标识，不靠文字颜色。

        QListWidget 的当前项配色在浅色主题下会把文字刷成白色（看不见）、
        深色主题下只有当前项亮——两个主题都不可读，所以干脆不用 current 高亮。
        """
        item = self.playlist.item(index)
        name = self._playlist_entries[index].path.name
        item.setText(f'{"▶" if current else "  "} {index + 1:>3}   {name}')
        item.setForeground(self._text_color())
        font = item.font()
        font.setBold(current)
        item.setFont(font)

    # ---------------- 主题配色 ----------------
    def _text_color(self) -> QColor:
        """列表文字按主题显式着色。

        QListWidget 默认按 palette 画字；抽屉是自绘背景的浮动层，浅色 palette
        落到深色抽屉上就成了「深底深字」。显式配色后两个主题都可读。
        """
        return QColor(232, 232, 232) if isDarkTheme() else QColor(32, 32, 32)

    def _apply_list_style(self, *args) -> None:
        color = self._text_color().name()
        style = (
            'QListWidget{background:transparent;border:none}'
            f'QListWidget::item{{padding:6px 4px;border-radius:4px;color:{color}}}'
            f'QListWidget::item:selected{{background:transparent;color:{color}}}'
        )
        for widget in (self.playlist, self.bookmarks):
            widget.setStyleSheet(style)
            for row in range(widget.count()):
                widget.item(row).setForeground(self._text_color())

    def set_bookmarks(self, marks: list[tuple[int, int, str]], formatter) -> None:
        self.bookmarks.clear()
        for bookmark_id, pos_ms, label in marks:
            text = formatter(pos_ms) + (f'   {label}' if label else '')
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, (bookmark_id, pos_ms))
            item.setForeground(self._text_color())
            self.bookmarks.addItem(item)

    def set_info(self, lines: list[tuple[str, str]]) -> None:
        """两列信息表：左列小号右对齐弱化标签，右列值（加重/可选中/自动换行）。

        原来是「标签一行、值一行」上下堆叠，四组挤在一起没有层次；文件名与路径
        这类长串靠 wordWrap 断行，值可鼠标选中复制（路径最需要）。
        """
        while self.infoLayout.count():
            item = self.infoLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for key, value in lines:
            row = QWidget(self.info)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            caption = CaptionLabel(key, row)
            caption.setFixedWidth(44)
            caption.setAlignment(Qt.AlignRight | Qt.AlignTop)
            value_label = (StrongBodyLabel(value, row) if key == '文件名'
                           else BodyLabel(value, row))
            value_label.setWordWrap(True)
            value_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row_layout.addWidget(caption, 0)
            row_layout.addWidget(value_label, 1)
            self.infoLayout.addWidget(row)

    # ---------------- 动画 ----------------
    def target_rect(self) -> QRect:
        page = self.parentWidget()
        if page is None:
            return QRect()
        stage = getattr(page, 'stageStack', None)
        y = stage.y() if stage is not None else 0
        height = stage.height() if stage is not None else page.height()
        return QRect(page.width() - DRAWER_WIDTH, y, DRAWER_WIDTH, height)

    def reposition(self) -> None:
        if self.isVisible():
            self.setGeometry(self.target_rect())

    def show_drawer(self) -> None:
        rect = self.target_rect()
        start = rect.translated(DRAWER_WIDTH, 0)
        self.setGeometry(start)
        self._target_visible = True
        self.show()
        self.raise_()
        # 打开时预先滚到当前文件（切换文件不重滚，别打断用户自己翻列表）
        self._scroll_to_current()
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(rect)
        self._animation.start()

    def _scroll_to_current(self) -> None:
        index = getattr(self, '_playlist_current', -1)
        if 0 <= index < self.playlist.count():
            self.playlist.scrollToItem(
                self.playlist.item(index), QAbstractItemView.PositionAtCenter
            )

    def hide_drawer(self) -> None:
        if not self.isVisible():
            return
        rect = self.geometry()
        end = rect.translated(DRAWER_WIDTH, 0)
        self._target_visible = False
        self._animation.stop()
        self._animation.setStartValue(rect)
        self._animation.setEndValue(end)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if not self._target_visible:
            self.hide()
            self.closed.emit()

    # ---------------- 交互 ----------------
    def _on_tab_changed(self, route_key: str) -> None:
        index = {'playlist': 0, 'bookmarks': 1, 'info': 2}.get(route_key, 0)
        self.stack.setCurrentIndex(index)

    def _on_playlist_clicked(self, item: QListWidgetItem) -> None:
        self.openIndexRequested.emit(int(item.data(Qt.UserRole)))

    def _on_bookmark_clicked(self, item: QListWidgetItem) -> None:
        _, pos_ms = item.data(Qt.UserRole)
        self.bookmarkSelected.emit(int(pos_ms))

    def _on_bookmark_menu(self, pos) -> None:
        item = self.bookmarks.itemAt(pos)
        if item is None:
            return
        bookmark_id, _ = item.data(Qt.UserRole)
        menu = RoundMenu(parent=self)
        delete_action = Action('删除书签', menu)
        delete_action.triggered.connect(
            lambda: self.bookmarkDeleteRequested.emit(int(bookmark_id))
        )
        menu.addAction(delete_action)
        menu.exec(self.bookmarks.viewport().mapToGlobal(pos))

    # ---------------- 绘制 ----------------
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dark = isDarkTheme()
        painter.setPen(QPen(QColor(255, 255, 255, 30) if dark else QColor(0, 0, 0, 18), 1))
        painter.setBrush(QColor(32, 32, 32, 248) if dark else QColor(250, 250, 250, 250))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
