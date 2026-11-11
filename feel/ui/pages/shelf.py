"""资料库页：卡片网格 + 分类/扩展名筛选 + 选择模式涂抹多选 + 逐卡重命名/删除。

FR-18 分类过滤 / FR-19 涂抹多选 / FR-20 删除重命名 / FR-21 卡片 / FR-22 点击打开。

顶栏收敛为「刷新 + 选择」：进入选择模式后才出现 全选 / 删除 / 取消。
重命名与删除是卡片悬停操作（左上角），不再占顶栏。
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    IndeterminateProgressRing,
    InfoBar,
    PillPushButton,
    SearchLineEdit,
    StrongBodyLabel,
    TransparentPushButton,
)

from ...config import SORT_MODE_TEXTS, SORT_MODES, cfg
from ...scanner import MediaEntry
from ...thumbs import ThumbnailService
from ..widgets.shelf_card import CARD_H, CARD_W, ShelfCard

CATEGORIES = [('all', '全部'), ('image', '图片'), ('video', '视频'), ('audio', '音频'),
              ('favorite', '收藏')]

# 大目录分批建卡：每 tick 建这么多张，加载动画才有机会转动
BUILD_CHUNK = 60
THUMB_MEMORY = 256


class _PaintOverlay(QWidget):
    """涂抹多选：覆盖在网格视口上，拖拽扫过的卡片即选中。"""

    def __init__(self, page: 'ShelfPage'):
        super().__init__(page.scroll.viewport())
        self._page = page
        self._painting = False
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._painting = True
            self._page.begin_paint(event.position().toPoint())

    def mouseMoveEvent(self, event):
        if self._painting:
            self._page.paint_to(event.position().toPoint())

    def mouseReleaseEvent(self, event):
        self._painting = False
        self._page.end_paint()


class ShelfPage(QWidget):
    """同目录媒体卡片墙。"""

    openRequested = Signal(str)
    deleteRequested = Signal(list)
    openFolderRequested = Signal()
    renameRequested = Signal(object, str)
    favoriteToggled = Signal(object)
    refreshRequested = Signal()
    sortModeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('shelfPage')
        self.entries: list[MediaEntry] = []
        self.selected: set[Path] = set()
        self.cards: dict[Path, ShelfCard] = {}
        self._ordered_cards: list[ShelfCard] = []
        self._category = 'all'
        self._ext = ''
        self._ext_options: list[str] = ['']
        self._paint_mode = False
        self._search = ''
        self._folder: Path | None = None
        self._entries_key: tuple | None = None
        self.ocr_texts: dict[Path, str] = {}
        self.favorites: set[Path] = set()
        self._paint_anchor: int | None = None
        self._paint_remove = False
        self._paint_base: set[Path] = set()
        self._paint_last: int | None = None

        self._thumb_images: OrderedDict[Path, QImage] = OrderedDict()
        self._build_token = 0
        self._pending_entries: list[MediaEntry] = []
        self._pending_pos = 0
        self._pending_rebuild = False
        self._deferred_layout = False
        self._pending_relayout = False

        self.thumbs = ThumbnailService(self)
        self.thumbs.ready.connect(self._on_thumb_ready)
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 18, 36, 12)
        root.setSpacing(10)

        # 顶栏：标题 + 计数 │ 刷新 │ 选择；选择模式追加 已选N/全选/删除/取消
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.titleLabel = StrongBodyLabel('资料库', self)
        self.countLabel = CaptionLabel('', self)
        self.selLabel = CaptionLabel('', self)
        self.refreshBtn = TransparentPushButton('刷新', self)
        self.refreshBtn.setIcon(FluentIcon.SYNC)
        self.openFolderBtn = TransparentPushButton('打开文件夹', self)
        self.openFolderBtn.setIcon(FluentIcon.FOLDER)
        self.paintBtn = PillPushButton(self)
        self.paintBtn.setText('选择')
        self.paintBtn.setCheckable(True)
        self.selectAllBtn = TransparentPushButton('全选', self)
        self.deleteBtn = TransparentPushButton('删除', self)
        self.cancelSelectBtn = TransparentPushButton('取消', self)
        title_row.addWidget(self.titleLabel)
        title_row.addWidget(self.countLabel)
        title_row.addStretch(1)
        title_row.addWidget(self.selLabel)
        title_row.addWidget(self.openFolderBtn)
        title_row.addWidget(self.refreshBtn)
        title_row.addWidget(self.paintBtn)
        title_row.addWidget(self.selectAllBtn)
        title_row.addWidget(self.deleteBtn)
        title_row.addWidget(self.cancelSelectBtn)
        for widget in (self.selLabel, self.selectAllBtn, self.deleteBtn,
                       self.cancelSelectBtn):
            widget.hide()

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.chips: dict[str, PillPushButton] = {}
        for key, text in CATEGORIES:
            chip = PillPushButton(self)
            chip.setText(text)
            chip.setCheckable(True)
            chip.setChecked(key == 'all')
            chip.clicked.connect(lambda _c=False, k=key: self._on_category(k))
            filter_row.addWidget(chip)
            self.chips[key] = chip
        filter_row.addSpacing(12)
        # 排序：名称（自然序）/ 时间新→旧 / 时间旧→新，改变后整队列重排（FR-18）
        self.sortCombo = ComboBox(self)
        self.sortCombo.setMinimumWidth(136)
        for mode in SORT_MODES:
            self.sortCombo.addItem(SORT_MODE_TEXTS[mode])
        self.sortCombo.setCurrentIndex(self._mode_index(cfg.sortMode.value))
        self.sortCombo.setToolTip('排序方式（资料库与播放队列共用同一顺序）')
        filter_row.addWidget(self.sortCombo)
        self.extCombo = ComboBox(self)
        self.extCombo.setMinimumWidth(140)
        filter_row.addWidget(self.extCombo)
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText('搜索图片文字')
        self.searchEdit.setMinimumWidth(240)
        filter_row.addWidget(self.searchEdit, 1)
        # 搜索框隐藏时用它吃住剩余宽度，避免 chips/下拉被拉宽（搜索关掉就整行收起）
        self.filterSpacer = QWidget(self)
        self.filterSpacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.filterSpacer.setFixedHeight(0)
        filter_row.addWidget(self.filterSpacer)
        self.filterSpacer.hide()

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet('QScrollArea{background: transparent; border: none}')
        self.gridContainer = QWidget(self.scroll)
        self.gridContainer.setStyleSheet('QWidget{background: transparent}')
        self.grid = QGridLayout(self.gridContainer)
        self.grid.setContentsMargins(0, 6, 0, 12)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.gridContainer)

        # 空态：直接挂在视口上并铺满，保证文本真正居中（不进网格，避免被列宽带偏）
        self.emptyLabel = BodyLabel(
            '打开文件后，同目录的图片 / 音频 / 视频会以卡片形式出现在这里',
            self.scroll.viewport(),
        )
        self.emptyLabel.setAlignment(Qt.AlignCenter)
        self.emptyLabel.setWordWrap(True)
        self.emptyLabel.hide()

        self.busy = IndeterminateProgressRing(self.scroll.viewport())
        self.busy.setFixedSize(48, 48)
        self.busy.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.busy.hide()

        self.overlay = _PaintOverlay(self)
        self.overlay.hide()

        root.addLayout(title_row)
        root.addLayout(filter_row)
        root.addWidget(self.scroll, 1)

        # 启动时还没打开任何文件：空态文案直接可见（一旦建卡 _rebuild_grid 会隐藏它）
        self._show_empty()

        self.extCombo.currentIndexChanged.connect(self._on_ext_changed)
        self.sortCombo.currentIndexChanged.connect(self._on_sort_changed)
        self.refreshBtn.clicked.connect(self.refreshRequested.emit)
        self.openFolderBtn.clicked.connect(self.openFolderRequested.emit)
        self.selectAllBtn.clicked.connect(self.select_all)
        self.deleteBtn.clicked.connect(self.delete_selected)
        self.cancelSelectBtn.clicked.connect(lambda: self._set_paint_mode(False))
        self.paintBtn.clicked.connect(self.toggle_paint_mode)
        self.searchEdit.textChanged.connect(self._on_search_changed)
        self.scroll.viewport().installEventFilter(self)

    # ---------------- 数据 ----------------
    def set_entries(self, entries: list[MediaEntry]) -> None:
        folder = Path(entries[0].path).parent if entries else None
        if folder != self._folder:
            self._folder = folder
            self.ocr_texts = {}
            self._search = ''
            self.searchEdit.clear()
            self._entries_key = None
        self.entries = list(entries)
        known = {e.path for e in self.entries}
        self.selected &= known
        # 同一目录同一文件集合（例如只是切了当前文件/刷新）：不重建网格，
        # 否则千级目录每次点卡片都会全量重建。
        key = tuple((e.path, e.kind) for e in self.entries)
        if key == self._entries_key:
            self.countLabel.setText(f'{len(self._visible_entries())} 项')
            return
        self._entries_key = key
        self._rebuild_ext_options()
        if self.isVisible():
            self._rebuild_grid()
        else:
            # 打开文件时资料库多半不在前台：先记账，切到本页再建卡，打开文件不卡
            self._pending_rebuild = True
            self.countLabel.setText(f'{len(self._visible_entries())} 项')

    def _visible_entries(self) -> list[MediaEntry]:
        items = self.entries
        if self._category == 'favorite':
            items = [e for e in items if e.path in self.favorites]
        elif self._category != 'all':
            items = [e for e in items if e.kind == self._category]
        if self._ext:
            items = [e for e in items if e.path.suffix.lower() == self._ext]
        if self._search:
            needle = self._search.lower()
            items = [e for e in items
                     if e.kind == 'image'
                     and needle in self.ocr_texts.get(e.path, '').lower()]
        return items

    def _rebuild_ext_options(self) -> None:
        exts = sorted({e.path.suffix.lower() for e in self.entries})
        self._ext_options = [''] + exts
        self.extCombo.blockSignals(True)
        self.extCombo.clear()
        for ext in self._ext_options:
            self.extCombo.addItem('全部扩展名' if not ext else ext)
        self._ext = ''
        self.extCombo.setCurrentIndex(0)
        self.extCombo.blockSignals(False)

    # ---------------- 网格构建（分批，带加载动画） ----------------
    def _rebuild_grid(self) -> None:
        self._pending_rebuild = False
        self._build_token += 1
        self._deferred_layout = False
        self.gridContainer.show()
        for card in self._ordered_cards:
            # 先 hide 再脱离父级：可见控件 setParent(None) 会短暂变成顶层窗口
            # （PySide 下表现为闪出若干子窗口，大目录重建时非常明显）
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self._ordered_cards.clear()
        self.cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)

        visible = self._visible_entries()
        self.countLabel.setText(f'{len(visible)} 项')
        self._refresh_selection()
        if not visible:
            self._pending_entries = []
            self.busy.hide()
            self._show_empty()
            return
        self.emptyLabel.hide()

        if len(visible) <= BUILD_CHUNK:
            self._create_batch(visible, 0)
            self._finish_build()
            return
        self._pending_entries = visible
        self._pending_pos = 0
        self._deferred_layout = True
        self.gridContainer.hide()
        self.busy.show()
        self.busy.raise_()
        self._position_busy()
        self._pump_build(self._build_token)

    def _pump_build(self, token: int) -> None:
        if token != self._build_token:
            return
        chunk = self._pending_entries[self._pending_pos:self._pending_pos + BUILD_CHUNK]
        if chunk:
            self._create_batch(chunk, self._pending_pos)
            self._pending_pos += len(chunk)
        if self._pending_pos < len(self._pending_entries):
            QTimer.singleShot(0, lambda: self._pump_build(token))
        else:
            self._pending_entries = []
            self._finish_build()

    def _create_batch(self, entries: list[MediaEntry], start: int) -> None:
        cols = 1 if self._deferred_layout else self._cols()
        for offset, entry in enumerate(entries):
            index = start + offset
            card = ShelfCard(entry, self.gridContainer)
            card.clicked.connect(self._on_card_clicked)
            card.openRequested.connect(lambda e: self.openRequested.emit(str(e.path)))
            card.renameRequested.connect(self.renameRequested.emit)
            card.deleteRequested.connect(lambda e: self.deleteRequested.emit([e.path]))
            card.favoriteToggled.connect(self.favoriteToggled.emit)
            card.set_favorite(entry.path in self.favorites)
            card.set_selected(entry.path in self.selected)
            image = self._thumb_images.get(entry.path)
            if image is not None:
                card.set_thumbnail(image)
            self.cards[entry.path] = card
            self._ordered_cards.append(card)
            if not self._deferred_layout:
                self.grid.addWidget(card, index // cols, index % cols)
            if image is None:
                self.thumbs.request(entry.path, entry.kind)

    def _finish_build(self) -> None:
        deferred = self._deferred_layout
        self._deferred_layout = False
        self._relayout()
        if deferred:
            # 网格容器构建期间隐藏，收尾一次性显示（避免逐卡 show 触发千次布局）
            self.gridContainer.show()
        self.busy.hide()
        if not self.isVisible():
            # 建卡时页面被切走了：等下次显示再重排一次，避免按旧/零尺寸算出的位置
            self._pending_relayout = True

    def _grid_metrics(self) -> tuple[int, list[int]]:
        """列数由视口宽度决定，卡片宽度均分整行（最后不留空）。

        列数 = 宽度能容纳几个 CARD_W（含间距）；确定列数后把可用宽度按列均分，
        整除余数逐列 +1px，保证所有列宽之和恰好等于视口宽度。
        """
        viewport_width = max(1, self.scroll.viewport().width())
        spacing = self.grid.spacing()
        margins = self.grid.contentsMargins()
        usable = viewport_width - margins.left() - margins.right()
        columns = max(1, (usable + spacing) // (CARD_W + spacing))
        usable -= spacing * (columns - 1)
        base, remainder = divmod(max(usable, columns), columns)
        widths = [max(140, base + (1 if index < remainder else 0))
                  for index in range(columns)]
        return columns, widths

    def _cols(self) -> int:
        return self._grid_metrics()[0]

    def _relayout(self) -> None:
        self._position_empty()
        self._position_busy()
        if self._deferred_layout:
            return
        if not self._ordered_cards:
            self._set_content_height(0)
            return
        cols, widths = self._grid_metrics()
        for index, card in enumerate(self._ordered_cards):
            card.set_card_width(widths[index % cols])
            self.grid.addWidget(card, index // cols, index % cols)
        rows = (len(self._ordered_cards) - 1) // cols + 1
        self.grid.setRowStretch(rows, 1)
        self._set_content_height(rows)

    def _set_content_height(self, rows: int) -> None:
        """把内容高度写进容器最小高度，别让 QScrollArea 把行压扁。

        widgetResizable 会把容器缩到视口大小；卡片是固定高度，行一旦被压缩
        就会全部叠在一起（打开大目录后 300 张卡挤在 600px 高度里）。
        """
        margins = self.grid.contentsMargins()
        spacing = self.grid.spacing()
        height = (rows * CARD_H + max(0, rows - 1) * spacing
                  + margins.top() + margins.bottom()) if rows > 0 else 0
        if self.gridContainer.minimumHeight() != height:
            self.gridContainer.setMinimumHeight(height)
            self.grid.invalidate()

    def _position_empty(self) -> None:
        self.emptyLabel.setGeometry(self.scroll.viewport().rect())

    def _position_busy(self) -> None:
        viewport = self.scroll.viewport()
        self.busy.move((viewport.width() - self.busy.width()) // 2,
                       (viewport.height() - self.busy.height()) // 2)

    def _show_empty(self) -> None:
        self._position_empty()
        self.emptyLabel.show()
        self.emptyLabel.raise_()
        self.overlay.raise_()

    def _on_thumb_ready(self, path: str, image) -> None:
        key = Path(path)
        if not image.isNull():
            self._thumb_images[key] = image
            self._thumb_images.move_to_end(key)
            while len(self._thumb_images) > THUMB_MEMORY:
                self._thumb_images.popitem(last=False)
        card = self.cards.get(key)
        if card is not None:
            card.set_thumbnail(image)

    # ---------------- 过滤 ----------------
    def _on_category(self, key: str) -> None:
        self._category = key
        for chip_key, chip in self.chips.items():
            chip.setChecked(chip_key == key)
        self._rebuild_grid()

    def _on_search_changed(self, text: str) -> None:
        self._search = text.strip()
        self._rebuild_grid()

    # ---------------- OCR 状态 ----------------
    def set_favorites(self, paths) -> None:
        self.favorites = {Path(p) for p in paths}
        for path, card in self.cards.items():
            card.set_favorite(path in self.favorites)
        if self._category == 'favorite':
            if self.isVisible():
                self._rebuild_grid()
            else:
                self._pending_rebuild = True

    def set_ocr_text(self, path: str, text: str) -> None:
        self.ocr_texts[Path(path)] = text
        if self._search and self.isVisible():
            self._rebuild_grid()

    def focus_search(self) -> None:
        self.searchEdit.setFocus()
        self.searchEdit.selectAll()

    def set_search_visible(self, visible: bool) -> None:
        """设置页「图片搜索」开关：关掉时整个搜索框收起，不占筛选行。"""
        self.searchEdit.setVisible(bool(visible))
        self.filterSpacer.setVisible(not visible)
        if not visible and self._search:
            self.searchEdit.clear()
            self._search = ''
            self._rebuild_grid()

    def _on_ext_changed(self, index: int) -> None:
        self._ext = self._ext_options[index] if 0 <= index < len(self._ext_options) else ''
        self._rebuild_grid()

    # ---------------- 排序（FR-18） ----------------
    @staticmethod
    def _mode_index(mode: str) -> int:
        try:
            return SORT_MODES.index(mode)
        except ValueError:
            return 0

    def set_sort_mode(self, mode: str) -> None:
        """外部改排序（例如 cfg 被别处写入）时同步下拉，不重复发信号。"""
        self.sortCombo.blockSignals(True)
        self.sortCombo.setCurrentIndex(self._mode_index(mode))
        self.sortCombo.blockSignals(False)

    def _on_sort_changed(self, index: int) -> None:
        mode = SORT_MODES[index] if 0 <= index < len(SORT_MODES) else SORT_MODES[0]
        if mode == cfg.sortMode.value:
            return
        cfg.set(cfg.sortMode, mode)
        cfg.save()
        self.sortModeChanged.emit(mode)

    # ---------------- 选择 ----------------
    def _refresh_selection(self) -> None:
        for path, card in self.cards.items():
            card.set_selected(path in self.selected)
        self.selLabel.setText(f'已选 {len(self.selected)}')
        visible = {e.path for e in self._visible_entries()}
        all_selected = bool(visible) and visible <= self.selected
        self.selectAllBtn.setText('取消全选' if all_selected else '全选')

    def _on_card_clicked(self, entry: MediaEntry, modifiers) -> None:
        if modifiers & Qt.ControlModifier:
            if entry.path in self.selected:
                self.selected.discard(entry.path)
            else:
                self.selected.add(entry.path)
            self._refresh_selection()
            return
        self.selected = {entry.path}
        self._refresh_selection()
        self.openRequested.emit(str(entry.path))

    # ---- 涂抹多选（按一维顺序的范围选择，支持反选）----
    def index_at(self, viewport_pos: QPoint) -> int | None:
        if not self._ordered_cards:
            return None
        container_pos = self.gridContainer.mapFrom(self.scroll.viewport(), viewport_pos)
        for index, card in enumerate(self._ordered_cards):
            if card.geometry().contains(container_pos):
                return index
        # 落在间隙/空白：取最近的卡片，拖过空白仍能确定起终点
        best_index = 0
        best_distance = None
        for index, card in enumerate(self._ordered_cards):
            rect = card.geometry()
            dx = max(rect.left() - container_pos.x(), 0, container_pos.x() - rect.right())
            dy = max(rect.top() - container_pos.y(), 0, container_pos.y() - rect.bottom())
            distance = dx * dx + dy * dy
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_index = index
        return best_index

    def begin_paint(self, viewport_pos: QPoint) -> None:
        """起笔：锚点决定整笔方向（锚点已选=取消笔，否则=加选笔），并记下笔前选区。"""
        index = self.index_at(viewport_pos)
        if index is None:
            self._paint_anchor = None
            return
        self._paint_anchor = index
        self._paint_last = None
        self._paint_base = set(self.selected)
        self._paint_remove = self._ordered_cards[index].entry.path in self.selected
        self._apply_paint_range(index)

    def paint_to(self, viewport_pos: QPoint) -> None:
        if getattr(self, '_paint_anchor', None) is None:
            return
        index = self.index_at(viewport_pos)
        if index is None or index == self._paint_last:
            return
        self._paint_last = index
        self._apply_paint_range(index)

    def end_paint(self) -> None:
        self._paint_anchor = None
        self._paint_last = None
        self._paint_base = set()

    def _apply_paint_range(self, current_index: int) -> None:
        """一维范围裁决：加选笔 = 笔前选区 ∪ 区间；取消笔 = 笔前选区 − 区间。

        区间随手指回拖收缩，落在区间外的卡片自动回到笔前状态（撤销本笔涂抹）。
        """
        low, high = sorted((self._paint_anchor, current_index))
        range_paths = {card.entry.path for card in self._ordered_cards[low:high + 1]}
        if self._paint_remove:
            self.selected = self._paint_base - range_paths
        else:
            self.selected = self._paint_base | range_paths
        self._refresh_selection()

    def toggle_paint_mode(self) -> None:
        self._set_paint_mode(not self._paint_mode)

    def _set_paint_mode(self, enabled: bool) -> None:
        self._paint_mode = enabled
        self.paintBtn.setChecked(enabled)
        self.overlay.setGeometry(self.scroll.viewport().rect())
        self.overlay.setVisible(enabled)
        for widget in (self.selLabel, self.selectAllBtn, self.deleteBtn,
                       self.cancelSelectBtn):
            widget.setVisible(enabled)
        if enabled:
            self.overlay.raise_()
        else:
            for card in self._ordered_cards:
                card.clear_hover()
            self.selected.clear()
            self._refresh_selection()

    def select_all(self) -> None:
        """全选 / 再点一次取消全选（只作用于当前筛选结果）。"""
        visible = {e.path for e in self._visible_entries()}
        if visible and visible <= self.selected:
            self.selected -= visible
        else:
            self.selected |= visible
        self._refresh_selection()

    def queue_for(self, path) -> list[MediaEntry] | None:
        """点卡片时的播放队列：当前筛选结果（分类 + 扩展名 + 搜索，按排序）。

        path 不在筛选结果里（例如 CLI 打开被筛掉的项）时返回 None，由播放页退回全目录。
        """
        target = Path(path)
        visible = self._visible_entries()
        if any(entry.path == target for entry in visible):
            return visible
        return None

    def open_selected(self) -> None:
        visible = {e.path for e in self._visible_entries()}
        chosen = [p for p in self.selected if p in visible]
        if chosen:
            self.openRequested.emit(str(chosen[0]))

    def rename_selected(self) -> None:
        visible = [p for p in self.selected if p in self.cards]
        if len(visible) != 1:
            InfoBar.warning('重命名', '请先选中一个文件（多选只支持删除）', duration=2500,
                            parent=self)
            return
        self.cards[visible[0]].start_rename()

    def delete_selected(self) -> None:
        visible = {e.path for e in self._visible_entries()}
        paths = [p for p in self.selected if p in visible]
        if not paths:
            InfoBar.warning('删除', '请先选中文件', duration=2500, parent=self)
            return
        self.deleteRequested.emit(paths)

    # ---------------- 布局事件 ----------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_rebuild:
            self._rebuild_grid()
        elif self._pending_relayout:
            self._pending_relayout = False
            self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(self.scroll.viewport().rect())
        self._position_empty()
        self._position_busy()
        self._relayout()

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == event.Type.Resize:
            self.overlay.setGeometry(self.scroll.viewport().rect())
            self._position_empty()
            self._position_busy()
            self._relayout()
        return super().eventFilter(obj, event)
