"""Fell 主窗口：FluentWindow + 三页导航 + 动作注册（SPEC §5.1 / FR-16）。"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from qfluentwidgets import (
    FluentWindow,
    FluentIcon,
    InfoBar,
    MessageBox,
    NavigationItemPosition,
    Theme,
    qconfig,
)
from qfluentwidgets.common.style_sheet import updateStyleSheet

from .actions import Action, ActionRegistry, GLOBAL, PLAYER, SHELF, SETTINGS
from .config import cfg
from .filedel import move_to_recycle_bin
from .logs import logger
from .ocr import OcrService
from .scanner import MEDIA_FILTER, scan_directory, scan_folder, sort_entries
from .store import Store
from .ui.pages.player import PlayerPage
from .ui.pages.help import HelpPage
from .ui.pages.settings import SettingsPage
from .ui.pages.shelf import ShelfPage
from .ui.widgets.theme_transition import ThemeTransitionOverlay

PAGE_CONTEXT = {}
log = logger()


class FellWindow(FluentWindow):
    """Fell 主窗口。"""

    def __init__(self):
        super().__init__()
        self.setObjectName('FellWindow')
        self.setWindowTitle('未打开文件')
        self.resize(1180, 780)

        self.playerPage = PlayerPage(self)
        self.shelfPage = ShelfPage(self)
        self.settingsPage = SettingsPage(self)
        self.helpPage = HelpPage(self)

        self.playerPage.setObjectName('playerPage')
        self.shelfPage.setObjectName('shelfPage')
        self.settingsPage.setObjectName('settingsPage')
        self.helpPage.setObjectName('helpPage')

        self.registry = ActionRegistry(self)
        self._nav: dict[str, object] = {}
        self._skip_theme_refresh = 0

        self._nav['goto_player'] = self.addSubInterface(
            self.playerPage, FluentIcon.PLAY, '播放', NavigationItemPosition.TOP
        )
        self._nav['goto_shelf'] = self.addSubInterface(
            self.shelfPage, FluentIcon.PHOTO, '资料库', NavigationItemPosition.TOP
        )
        self._nav['goto_settings'] = self.addSubInterface(
            self.settingsPage, FluentIcon.SETTING, '设置', NavigationItemPosition.SCROLL
        )
        self._nav['goto_help'] = self.addSubInterface(
            self.helpPage, FluentIcon.HELP, '帮助', NavigationItemPosition.SCROLL
        )

        PAGE_CONTEXT.update(
            {
                self.playerPage: PLAYER,
                self.shelfPage: SHELF,
                self.settingsPage: SETTINGS,
            }
        )

        # 页面联动：播放页队列变化 -> 资料库刷新；资料库动作 -> 播放页/窗口
        self.store = Store()
        self.ocr = OcrService(self.store, self)
        self._ocr_signature = None
        self.ocr.textReady.connect(self.shelfPage.set_ocr_text)
        self.playerPage.queueChanged.connect(self._on_entries_changed)
        self.playerPage.store = self.store
        self.shelfPage.set_favorites(self.store.favorite_paths())
        self.playerPage.favoriteChanged.connect(
            lambda: self.shelfPage.set_favorites(self.store.favorite_paths())
        )
        self.shelfPage.favoriteToggled.connect(
            lambda entry: self.toggle_favorite(entry.path)
        )
        self.shelfPage.openRequested.connect(self.open_path)
        self.shelfPage.deleteRequested.connect(self.delete_paths)
        self.shelfPage.openFolderRequested.connect(self.open_folder)
        self.shelfPage.renameRequested.connect(self.rename_file)
        self.shelfPage.refreshRequested.connect(self.refresh_library)
        self.shelfPage.sortModeChanged.connect(self._apply_sort)
        cfg.ocrEnabled.valueChanged.connect(self.shelfPage.set_search_visible)
        self.shelfPage.set_search_visible(cfg.ocrEnabled.value)

        self._build_actions()
        # 主题卡片等直接改 cfg.themeMode 的路径：主题翻转后重刷 QSS。
        # 重刷前先暂停正在播放的媒体：Qt6 FFmpeg 下音频播放中做全局 QSS 重刷
        # 会死锁（本机稳定复现，见 SPEC 已知问题），暂停到位后再刷，刷完恢复。
        # 用队列连接：刷新放到当前信号栈退栈之后，避免在 qconfig 发信号期间
        # 再跑嵌套事件循环（会打乱 SwitchButton/动画状态）。
        qconfig.themeChanged.connect(self._on_theme_changed, Qt.QueuedConnection)
        self.stackedWidget.currentChanged.connect(self._on_page_changed)
        self.switchTo(self.playerPage)
        self._on_page_changed(self.stackedWidget.currentIndex())  # 初始页可能不发信号

        # 设置变更 → 按钮悬停提示 / 步长实时生效（FR-04/05）
        cfg.seekStep.valueChanged.connect(lambda _v: self.playerPage.refresh_shortcut_tooltips())
        cfg.volumeStep.valueChanged.connect(self._on_volume_step_changed)
        self._on_volume_step_changed(cfg.volumeStep.value)
        self.playerPage.refresh_shortcut_tooltips()
        log.info('窗口初始化完成：%d 个动作', len(self.registry.actions))

    # ---- 动作 ----
    def _build_actions(self) -> None:
        page = self.playerPage
        r = self.registry

        r.register(
            Action('open_file', '打开文件', 'Ctrl+O', FluentIcon.FOLDER, handler=self.open_file)
        )
        r.register(
            Action('open_folder', '打开文件夹', 'Ctrl+Shift+O', FluentIcon.FOLDER_ADD,
                   context=SHELF, handler=self.open_folder)
        )
        r.register(
            Action('play_pause', '播放/暂停', 'Space', FluentIcon.PLAY_SOLID,
                   context=PLAYER, handler=page.toggle_play,
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('prev_file', '上一个文件', 'Ctrl+Left', FluentIcon.LEFT_ARROW,
                   context=PLAYER, handler=page.prev_file,
                   enabled_when=lambda: len(page.entries) > 1)
        )
        r.register(
            Action('next_file', '下一个文件', 'Ctrl+Right', FluentIcon.RIGHT_ARROW,
                   context=PLAYER, handler=page.next_file,
                   enabled_when=lambda: len(page.entries) > 1)
        )
        r.register(
            Action('seek_back', '后退', 'Left', FluentIcon.CARE_LEFT_SOLID,
                   context=PLAYER, handler=lambda: page.step_seek(-cfg.seekStep.value),
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('seek_forward', '前进', 'Right', FluentIcon.CARE_RIGHT_SOLID,
                   context=PLAYER, handler=lambda: page.step_seek(cfg.seekStep.value),
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('volume_up', '音量+', 'Up', FluentIcon.VOLUME,
                   context=PLAYER, handler=lambda: page.step_volume(cfg.volumeStep.value),
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('volume_down', '音量-', 'Down', FluentIcon.VOLUME,
                   context=PLAYER, handler=lambda: page.step_volume(-cfg.volumeStep.value),
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('play_mode', '播放模式', 'M', FluentIcon.ALBUM,
                   context=PLAYER, handler=page.cycle_mode)
        )
        r.register(
            Action('speed_up', '加快播放速度', ']', FluentIcon.SPEED_HIGH,
                   context=PLAYER, handler=lambda: page.cycle_speed(1),
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('speed_down', '减慢播放速度', '[', FluentIcon.SPEED_OFF,
                   context=PLAYER, handler=lambda: page.cycle_speed(-1),
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('favorite', '收藏/取消收藏', 'E', FluentIcon.HEART,
                   context=PLAYER, handler=page.toggle_favorite,
                   enabled_when=lambda: page.current_path is not None)
        )
        r.register(
            Action('bookmark_add', '添加书签', 'B', FluentIcon.QUICK_NOTE,
                   context=PLAYER, handler=page.add_bookmark,
                   enabled_when=lambda: page.has_media)
        )
        r.register(
            Action('drawer_toggle', '详情抽屉', 'I', FluentIcon.MENU,
                   context=PLAYER, handler=page.toggle_drawer)
        )
        r.register(
            Action('delete_file', '删除', 'Del', FluentIcon.DELETE,
                   context=PLAYER, handler=page.delete_current,
                   enabled_when=lambda: page.current_kind is not None)
        )
        r.register(
            Action('rotate_ccw', '逆时针旋转', 'Ctrl+L', FluentIcon.ROTATE,
                   context=PLAYER, handler=lambda: page.rotate(-90),
                   enabled_when=lambda: page.has_view)
        )
        r.register(
            Action('rotate_cw', '顺时针旋转', 'Ctrl+R', FluentIcon.ROTATE,
                   context=PLAYER, handler=lambda: page.rotate(90),
                   enabled_when=lambda: page.has_view)
        )
        r.register(
            Action('zoom_in', '放大', '=', FluentIcon.ZOOM_IN,
                   context=PLAYER, handler=lambda: page.zoom_by(1.1),
                   enabled_when=lambda: page.has_view)
        )
        r.register(
            Action('zoom_out', '缩小', '-', FluentIcon.ZOOM_OUT,
                   context=PLAYER, handler=lambda: page.zoom_by(1 / 1.1),
                   enabled_when=lambda: page.has_view)
        )
        r.register(
            Action('zoom_reset', '缩放重置', 'Ctrl+0', FluentIcon.FIT_PAGE,
                   context=PLAYER, handler=page.reset_zoom,
                   enabled_when=lambda: page.has_view)
        )
        r.register(
            Action('fullscreen', '全屏', 'F', FluentIcon.FULL_SCREEN,
                   context=PLAYER, handler=page.toggle_fullscreen)
        )
        r.register(
            Action('exit_fullscreen', '退出全屏', 'Esc', FluentIcon.BACK_TO_WINDOW,
                   handler=page.exit_fullscreen,
                   enabled_when=lambda: page.is_fullscreen)
        )
        shelf = self.shelfPage
        r.register(
            Action('rescan_ocr', '刷新', 'F5', FluentIcon.SYNC,
                   context=SHELF, handler=self.refresh_library)
        )
        r.register(
            Action('focus_search', '搜索图片文字', 'Ctrl+F', FluentIcon.SEARCH,
                   context=SHELF, handler=shelf.focus_search,
                   enabled_when=lambda: bool(cfg.ocrEnabled.value))
        )
        r.register(
            Action('open_selected', '打开选中', 'Enter', FluentIcon.PLAY,
                   context=SHELF, handler=shelf.open_selected,
                   enabled_when=lambda: bool(shelf.selected))
        )
        r.register(
            Action('select_all', '全选', 'Ctrl+A', FluentIcon.ACCEPT_MEDIUM,
                   context=SHELF, handler=shelf.select_all)
        )
        r.register(
            Action('rename_selected', '重命名', 'F2', FluentIcon.EDIT,
                   context=SHELF, handler=shelf.rename_selected,
                   enabled_when=lambda: bool(shelf.selected))
        )
        r.register(
            Action('delete_selected', '删除选中', 'Del', FluentIcon.DELETE,
                   context=SHELF, handler=shelf.delete_selected,
                   enabled_when=lambda: bool(shelf.selected))
        )
        r.register(
            Action('toggle_paint', '涂抹选择', None, FluentIcon.BRUSH,
                   context=SHELF, handler=shelf.toggle_paint_mode)
        )
        for action_id, text in (
            ('goto_player', '播放页'),
            ('goto_shelf', '资料库'),
            ('goto_settings', '设置'),
            ('goto_help', '帮助'),
        ):
            r.register(Action(action_id, text, {'goto_player': 'Ctrl+1',
                                                'goto_shelf': 'Ctrl+2',
                                                'goto_settings': 'Ctrl+3',
                                                'goto_help': 'Ctrl+4'}[action_id],
                              handler=lambda aid=action_id: self._goto(aid)))
        r.register(
            Action('toggle_theme', '切换深浅主题', 'Ctrl+T', FluentIcon.BRIGHTNESS,
                   handler=self.toggle_theme)
        )

        # 控件绑定（FR-16：每个动作都有可见控件）
        for action_id, nav_item in self._nav.items():
            r.bind_widget(action_id, nav_item)
        r.bind_widget('open_file', page.openBtn)
        r.bind_widget('play_pause', page.playBtn)
        r.bind_widget('prev_file', page.prevBtn)
        r.bind_widget('next_file', page.nextBtn)
        r.bind_widget('seek_back', page.seekBackBtn)
        r.bind_widget('seek_forward', page.seekFwdBtn)
        r.bind_widget('volume_up', page.volumeBtn)
        r.bind_widget('volume_down', page.volumeBtn)
        r.bind_widget('play_mode', page.modeBtn)
        r.bind_widget('speed_up', page.speedBtn,
                      tooltip='播放速度（点击选档；] 加快 / [ 减慢）')
        r.bind_widget('speed_down', page.speedBtn,
                      tooltip='播放速度（点击选档；] 加快 / [ 减慢）')
        r.bind_widget('delete_file', page.deleteBtn)
        r.bind_widget('favorite', page.favoriteBtn)
        r.bind_widget('bookmark_add', page.bookmarkBtn)
        r.bind_widget('drawer_toggle', page.drawerBtn)
        r.bind_widget('rotate_ccw', page.rotateCCWBtn)
        r.bind_widget('rotate_cw', page.rotateCWBtn)
        r.bind_widget('zoom_in', page.zoomInBtn)
        r.bind_widget('zoom_out', page.zoomOutBtn)
        r.bind_widget('zoom_reset', page.zoomLabelBtn)
        r.bind_widget('fullscreen', page.fullscreenBtn)
        r.bind_widget('exit_fullscreen', page.fullscreenBtn,
                      tooltip='退出全屏（Esc / F）')
        r.bind_widget('open_selected', self.shelfPage.gridContainer,
                      tooltip='打开选中（Enter / 双击卡片）')
        r.bind_widget('open_folder', self.shelfPage.openFolderBtn)
        r.bind_widget('select_all', self.shelfPage.selectAllBtn)
        r.bind_widget('rename_selected', self.shelfPage.gridContainer,
                      tooltip='重命名（F2，单选；也可悬停卡片左上角铅笔）')
        r.bind_widget('delete_selected', self.shelfPage.deleteBtn)
        r.bind_widget('toggle_paint', self.shelfPage.paintBtn)
        r.bind_widget('rescan_ocr', self.shelfPage.refreshBtn)
        r.bind_widget('focus_search', self.shelfPage.searchEdit,
                      tooltip='搜索图片文字（Ctrl+F）')
        r.bind_widget('toggle_theme', self.settingsPage.themeCard)

        # 顶栏图标按钮此前只挂了 tooltip 没接 clicked（点了没反应）：统一走 registry
        for action_id, widget in (
            ('favorite', page.favoriteBtn),
            ('delete_file', page.deleteBtn),
            ('open_file', page.openBtn),
            ('drawer_toggle', page.drawerBtn),
        ):
            widget.clicked.connect(lambda _checked=False, aid=action_id:
                                   self.registry.trigger(aid))

    def _goto(self, action_id: str) -> None:
        target = {
            'goto_player': self.playerPage,
            'goto_shelf': self.shelfPage,
            'goto_settings': self.settingsPage,
            'goto_help': self.helpPage,
        }[action_id]
        self.switchTo(target)

    # ---- 行为 ----
    def open_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, '打开文件', '', MEDIA_FILTER)
        if path:
            self.open_path(path)

    def open_folder(self) -> None:
        """资料库「打开文件夹」：只把目录装进队列与卡片墙，不跳页、不自动播放。"""
        from PySide6.QtWidgets import QFileDialog

        path = QFileDialog.getExistingDirectory(self, '打开文件夹', '')
        if not path:
            return
        folder = Path(path)
        entries = scan_folder(folder, cfg.sortMode.value)
        if not entries:
            log.warning('打开文件夹：%s 没有可读媒体', folder)
            InfoBar.warning('无法打开', '该目录没有可读的图片 / 音频 / 视频',
                            duration=3000, parent=self)
            return
        page = self.playerPage
        if page.has_media:
            page.engine.release()
        page.entries = entries
        page.directory_entries = entries
        page.index = -1
        page._clear_stage()
        page.queueChanged.emit()
        log.info('加载文件夹 %s（%d 个文件）', folder, len(entries))
        InfoBar.success(
            '已加载文件夹',
            f'{folder.name or folder} · {len(entries)} 个文件（点卡片打开）',
            duration=1800,
            parent=self,
        )

    def open_path(self, path: str | Path) -> None:
        """打开文件：播放页装载，并切换到播放页。

        队列取资料库当前筛选结果（分类/扩展名/搜索 + 排序）；没有匹配时退回全目录。
        """
        log.info('打开文件 %s', path)
        queue = self.shelfPage.queue_for(path)
        if queue is not None:
            log.info('播放队列 = 资料库筛选结果（%d 项）', len(queue))
        self.playerPage.open_path(path, queue=queue)
        self.switchTo(self.playerPage)

    def open_argument(self, path: str | Path) -> bool:
        """命令行/文件关联入口：文件直接打开；目录打开排序后的第一项。

        返回是否真的装载了媒体（目录为空时给提示并返回 False）。
        """
        path = Path(path)
        if not path.exists():
            return False
        if path.is_dir():
            entries = scan_folder(path, cfg.sortMode.value)
            if not entries:
                log.warning('打开目录：%s 没有可读媒体', path)
                InfoBar.warning('无法打开', '该目录没有可读的图片 / 音频 / 视频',
                                duration=3000, parent=self)
                return False
            page = self.playerPage
            page.entries = entries
            page.directory_entries = entries
            page.index = 0
            page._show_current()
            page.queueChanged.emit()
            self.switchTo(page)
            log.info('命令行打开目录 %s（%d 个文件）', path, len(entries))
            return True
        self.open_path(path)
        return self.playerPage.current_path is not None

    # ---- 目录联动 / OCR ----
    def _on_entries_changed(self) -> None:
        page = self.playerPage
        directory = page.directory_entries or page.entries
        self.shelfPage.set_entries(directory)
        images = [e.path for e in directory if e.kind == 'image']
        if not images or not cfg.ocrEnabled.value:
            return
        # 同目录 + 同图片集合只扫一次，避免反复打开时取消在飞任务
        folder = images[0].parent
        signature = (str(folder), frozenset(str(p) for p in images))
        if signature == self._ocr_signature:
            return
        self._ocr_signature = signature
        self.ocr.scan(images)

    def toggle_favorite(self, path) -> bool:
        path = Path(path)
        state = self.store.toggle_favorite(path)
        self.playerPage._refresh_favorite()
        self.playerPage._refresh_drawer()
        self.shelfPage.set_favorites(self.store.favorite_paths())
        # 收藏没有显眼的状态回执（♥ 变色太细）：给一条轻提示
        if state:
            InfoBar.success('已收藏', path.name, duration=1600, parent=self)
        else:
            InfoBar.info('已取消收藏', path.name, duration=1600, parent=self)
        return state

    def refresh_library(self) -> None:
        """刷新：重新扫描当前目录（新增/改名/删除的文件立刻反映）+ 强制重跑 OCR。"""
        page = self.playerPage
        anchor = page.current_path
        if anchor is None and self.shelfPage.entries:
            anchor = self.shelfPage.entries[0].path
        if anchor is None:
            InfoBar.warning('刷新', '还没有打开文件', duration=2500, parent=self)
            return
        entries, _index = scan_directory(anchor, cfg.sortMode.value)
        if not entries:
            InfoBar.warning('刷新', '该目录没有可读的图片 / 音频 / 视频', duration=2500,
                            parent=self)
            return
        current = page.current_path
        membership = {e.path for e in page.entries}
        page.directory_entries = entries
        page.entries = ([e for e in entries if e.path in membership]
                        if membership else list(entries))
        if current is None:
            # 资料库「打开文件夹」只加载不出当前项：刷新后继续保持这种状态
            page.index = -1
        else:
            index = next((i for i, e in enumerate(page.entries) if e.path == current), -1)
            if index >= 0:
                page.index = index
            else:
                # 当前文件被外部删除/改名（或已不在筛选结果里）：退回全目录定位
                page.entries = list(entries)
                page.index = min(max(page.index, 0), len(entries) - 1)
                page._show_current()
        log.info('刷新资料库 %s：%d 个文件', entries[0].path.parent, len(entries))
        self._ocr_signature = None
        if cfg.ocrEnabled.value:
            images = [e.path for e in entries if e.kind == 'image']
            if images:
                self.ocr.scan(images, force=True)
        page.queueChanged.emit()
        InfoBar.success('刷新', f'已重新扫描 {len(entries)} 个文件', duration=1800,
                        parent=self)

    def _apply_sort(self, _mode: str | None = None) -> None:
        """排序变更：资料库与播放队列共用同一顺序，当前文件保持不变。"""
        page = self.playerPage
        if not page.entries:
            return
        current = page.current_path
        membership = {e.path for e in page.entries}
        page.directory_entries = sort_entries(
            page.directory_entries or page.entries, cfg.sortMode.value
        )
        if membership:
            page.entries = [e for e in page.directory_entries
                            if e.path in membership]
        if current is None:
            page.index = -1
        else:
            page.index = next(
                (i for i, entry in enumerate(page.entries) if entry.path == current), -1
            )
            if page.index < 0:
                page.entries = list(page.directory_entries)
                page.index = next(
                    (i for i, entry in enumerate(page.entries)
                     if entry.path == current), 0
                )
        page._refresh_drawer(force=page.drawer.isVisible())
        page.queueChanged.emit()

    # OCR 全程静默：结果逐张写缓存，未完成的图片下次打开目录时自动续跑

    # ---- 文件操作（资料库与播放页共用）----
    def delete_paths(self, paths, confirm: bool = True) -> bool:
        paths = [Path(p) for p in paths]
        if not paths:
            return False
        if confirm and not cfg.directDelete.value:
            preview = '、'.join(p.name for p in paths[:3])
            if len(paths) > 3:
                preview += ' …'
            box = MessageBox(
                '删除文件',
                f'将 {len(paths)} 个文件移入回收站？\n{preview}',
                self,
            )
            box.yesButton.setText('移入回收站')
            box.cancelButton.setText('取消')
            if not box.exec():
                return False

        page = self.playerPage
        current = page.current_path
        if current in paths and page.has_media:
            page.engine.release()

        deleted: set[Path] = set()
        failed: list[tuple[Path, str]] = []
        for path in paths:
            ok, error = move_to_recycle_bin(path)
            if ok:
                deleted.add(path)
            else:
                failed.append((path, error))
        log.info('删除到回收站：%d 个（%s）', len(deleted),
                 '、'.join(p.name for p in list(deleted)[:5]))
        if deleted:
            page.remove_paths(deleted)
            self.shelfPage.set_entries(page.directory_entries)
        if failed:
            log.warning('删除失败：%s', '；'.join(f'{p}: {e}' for p, e in failed))
            InfoBar.error(
                '部分删除失败',
                '；'.join(f'{p.name}: {e}' for p, e in failed[:3]),
                duration=4000,
                parent=self,
            )
        return bool(deleted) and not failed

    def rename_file(self, entry, new_stem: str) -> bool:
        path = Path(entry.path)
        new_path = path.with_name(f'{new_stem}{path.suffix}')
        if new_path == path:
            return True
        if new_path.exists():
            log.warning('重命名失败（同名已存在）：%s', new_path)
            InfoBar.warning('重命名失败', f'同名文件已存在：{new_path.name}', duration=3000,
                            parent=self)
            return False
        page = self.playerPage
        current = page.current_path
        membership = {e.path for e in page.entries}
        if path in membership:
            membership.discard(path)
            membership.add(new_path)
        released = current == path and page.has_media
        if released:
            # 改的是当前音视频：先让后端放开文件句柄，否则 Windows 上 rename 会因占用失败
            page.engine.release()
        try:
            os.rename(path, new_path)
        except OSError as error:
            log.warning('重命名失败：%s -> %s（%s）', path, new_path, error)
            InfoBar.error('重命名失败', str(error), duration=4000, parent=self)
            if released:
                page.open_path(path)  # 句柄已释放，把原文件重新装上，别停在黑屏
            return False
        self.store.rename_path(path, new_path)
        log.info('重命名 %s -> %s', path.name, new_path.name)
        anchor = new_path if current == path else (current or new_path)
        entries, _index = scan_directory(anchor, cfg.sortMode.value)
        if not entries:
            return True
        page.directory_entries = entries
        if membership:
            # 保持原来的筛选队列成员，只把路径换掉（全目录队列 = membership 覆盖全部）
            page.entries = [e for e in entries if e.path in membership]
        else:
            page.entries = []
        if current == path:
            page.index = next(
                (i for i, e in enumerate(page.entries) if e.path == new_path), -1
            )
            page._show_current()
        elif current is not None:
            # 改名的不是当前文件：只更新队列，不重载正在播放的文件
            page.index = next(
                (i for i, e in enumerate(page.entries) if e.path == current), -1
            )
            if page.index < 0:
                page.entries = list(entries)
                page.index = next(
                    (i for i, e in enumerate(entries) if e.path == current), 0
                )
        else:
            # 资料库只加载了目录（没有当前文件）：改名后刷新队列，不自动打开
            page.index = -1
        page.queueChanged.emit()
        return True

    def toggle_theme(self) -> None:
        # 先抓旧主题快照，再换肤，用径向渐变揭示新主题（SPEC §5.5）
        snapshot = self.grab()
        current = cfg.themeMode.value
        # 不用 setTheme()（它内部会再 updateStyleSheet 一次，双重重刷）；
        # 同步刷一次再放动画，并记账让 themeChanged 的队列刷新跳过这一轮。
        self._skip_theme_refresh += 1
        cfg.set(cfg.themeMode, Theme.LIGHT if current == Theme.DARK else Theme.DARK)
        cfg.save()
        self._apply_theme_styles()
        # setTheme() 会替我们发这个信号（设置页开关靠它同步状态），这里手动补
        qconfig.themeChangedFinished.emit()
        overlay = ThemeTransitionOverlay(self)
        overlay.play(snapshot)
        self._theme_overlay = overlay
        log.info('主题切换：%s -> %s', current, cfg.themeMode.value)

    def _on_theme_changed(self, _theme) -> None:
        if self._skip_theme_refresh:
            self._skip_theme_refresh -= 1
            return
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        """全局 QSS 重刷（只刷一次：setTheme 内部还会刷一次，故不走 setTheme）。

        已知限制：fluent 组件在音频播放中做全局 QSS 偶发冻屏（Qt6 FFmpeg +
        qfluentwidgets，最小复现已确认），按用户决定不规避，见 SPEC §9。
        """
        updateStyleSheet()

    def _on_volume_step_changed(self, step: int) -> None:
        self.playerPage.volumeBtn.set_step(step)

    def closeEvent(self, event):
        log.info('关闭窗口')
        shutdown = getattr(self.ocr, 'shutdown', None)
        if shutdown is not None:
            shutdown()
        super().closeEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and hasattr(self, 'playerPage'):
            self.playerPage.update_fullscreen_button()
        super().changeEvent(event)

    def _on_page_changed(self, _index: int) -> None:
        page = self.stackedWidget.currentWidget()
        self.registry.set_context(PAGE_CONTEXT.get(page, GLOBAL))
