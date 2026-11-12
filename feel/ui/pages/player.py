"""播放页：图片 / 视频 / 音频查看与播放（FR-02/03/04/05/06/07/08/09/10/11/18）。

Phase 4：缩放（滚轮/按钮/100%）、旋转 ±90°（图片/视频）、全屏、
图像工具组按媒体类型显隐。收藏/书签在 Phase 7。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMovie, QPixmap, QTransform
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    DropDownPushButton,
    FluentIcon,
    IconWidget,
    IndeterminateProgressRing,
    InfoBar,
    RoundMenu,
    SplitPushButton,
    StrongBodyLabel,
    TransparentPushButton,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
)

from ...config import PLAY_MODE_TEXTS, PLAY_MODES, SPEEDS, cfg
from ...frameprobe import FrameGrabber
from ...logs import logger
from ...player import MediaEngine
from ...actions import display_sequence
from ...queue import auto_index, step_index
from ...scanner import AUDIO, IMAGE, VIDEO, MediaEntry, scan_directory
from ...ui.widgets.bookmark_popup import BookmarkPopup
from ...ui.widgets.drawer import Drawer
from ...ui.widgets.frame_preview import FramePreview
from ...ui.widgets.heart_icon import heart_icon
from ...ui.widgets.image_stage import ImageStage
from ...ui.widgets.seek_bar import SeekBar, format_time
from ...ui.widgets.volume_button import VolumeButton
from ...ui.widgets.volume_osd import VolumeOsd

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.1, 8.0, 1.1


class _VideoView(QGraphicsView):
    """视频舞台：视口尺寸变化时同步 scene 与 videoItem。"""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setInteractive(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = self.viewport().size()
        self.scene().setSceneRect(0, 0, size.width(), size.height())
        for item in self.scene().items():
            item.setSize(size)


class PlayerPage(QWidget):
    """播放 / 查看页。"""

    queueChanged = Signal()
    favoriteChanged = Signal()
    # 当前媒体种类（图片/音频/视频/未打开）变了：左右键归属要重算（FeelWindow 接 registry）
    kindChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('playerPage')
        self.store = None
        self.registry = None
        self._synced_kind = None

        self.entries: list[MediaEntry] = []
        # 目录全量列表（资料库展示用）；self.entries 是播放队列，可能只是它的筛选子集
        self.directory_entries: list[MediaEntry] = []
        self.index = -1
        self._image_pixmap: QPixmap | None = None
        self._movie: QMovie | None = None
        self._zoom = 1.0
        self._rotation = 0
        self._render_token = 0
        self._hold_active = False
        self._hold_image = None
        self._skip_video_click = False
        self._speed_btn_pressed = False  # speedBtn 点击配对（见 eventFilter）
        self._speed_menu_was_open = False    # 本次点击是在「关菜单」
        self._speed_menu_hide_recent = False  # 菜单刚被关（aboutToHide 余温）
        self.zoomChanged = None  # 保持类型提示友好；实际用 _update_zoom_label

        self.engine = MediaEngine(self)
        self._build_ui()
        self._wire_engine()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶栏：文件名（FR-10）+ 全屏 + 删除 + 打开
        self.topBar = QWidget(self)
        self.topBar.setFixedHeight(60)
        top = QHBoxLayout(self.topBar)
        top.setContentsMargins(24, 10, 24, 0)
        top.setSpacing(8)
        self.titleLabel = StrongBodyLabel('未打开文件', self.topBar)
        self.titleLabel.setCursor(Qt.PointingHandCursor)
        self.titleLabel.installEventFilter(self)
        # 点标题就地改名：同一行放一个隐藏的 LineEdit，进入编辑时互换
        self.titleEdit = QLineEdit(self.topBar)
        self.titleEdit.setObjectName('titleEdit')
        self.titleEdit.setMaxLength(200)
        self.titleEdit.hide()
        self.titleEdit.installEventFilter(self)
        self.titleEdit.returnPressed.connect(self._commit_title_rename)
        self.titleEdit.editingFinished.connect(self._commit_title_rename)
        self._title_renaming = False
        self._rename_stem = ''
        self.favoriteBtn = TransparentToolButton(FluentIcon.HEART, self.topBar)
        self.fullscreenBtn = TransparentToolButton(FluentIcon.FULL_SCREEN, self.topBar)
        self.deleteBtn = TransparentToolButton(FluentIcon.DELETE, self.topBar)
        self.openBtn = TransparentToolButton(FluentIcon.FOLDER, self.topBar)
        self.drawerBtn = TransparentToolButton(FluentIcon.MENU, self.topBar)
        top.addWidget(self.titleLabel, 1)
        top.addWidget(self.titleEdit, 1)
        top.addWidget(self.favoriteBtn)
        top.addWidget(self.fullscreenBtn)
        top.addWidget(self.deleteBtn)
        top.addWidget(self.openBtn)
        top.addWidget(self.drawerBtn)

        # 舞台：图片 / 视频 / 音频三态
        self.stageStack = QStackedWidget(self)
        self.stageStack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.imageLabel = ImageStage(self.stageStack)

        self.videoView = _VideoView(None, self.stageStack)
        self.videoView.setFrameShape(QFrame.NoFrame)
        self.videoView.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.videoView.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.videoView.setStyleSheet('QGraphicsView{background:#000}')
        self.scene = QGraphicsScene(self.videoView)
        self.videoItem = QGraphicsVideoItem()
        self.videoItem.setAspectRatioMode(Qt.KeepAspectRatio)
        self.scene.addItem(self.videoItem)
        self.videoView.setScene(self.scene)
        # 单曲播完复位时 FFmpeg 后端不出首帧（黑屏），用取帧快照顶住画面
        self.frameHold = QLabel(self.videoView.viewport())
        self.frameHold.setAlignment(Qt.AlignCenter)
        self.frameHold.setStyleSheet('background: #000')
        # 快照只顶画面，点击要穿透到视频视口（点视频=播放/暂停）
        self.frameHold.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.frameHold.hide()
        # 视频输出按媒体类型挂/摘：纯音频时保持 video sink 会让全局 QSS 刷新卡死
        # （Qt6 FFmpeg + QGraphicsVideoItem 实测），只有视频才挂。

        self.audioStage = QWidget(self.stageStack)
        audio_layout = QVBoxLayout(self.audioStage)
        audio_layout.setAlignment(Qt.AlignCenter)
        audio_layout.setSpacing(12)
        self.audioIcon = IconWidget(FluentIcon.HEADPHONE, self.audioStage)
        self.audioIcon.setFixedSize(72, 72)
        self.audioName = BodyLabel('', self.audioStage)
        self.audioName.setAlignment(Qt.AlignCenter)
        self.audioHint = CaptionLabel('正在播放音频', self.audioStage)
        audio_layout.addWidget(self.audioIcon, 0, Qt.AlignCenter)
        audio_layout.addWidget(self.audioName, 0, Qt.AlignCenter)
        audio_layout.addWidget(self.audioHint, 0, Qt.AlignCenter)

        self.emptyStage = QWidget(self.stageStack)
        empty_layout = QVBoxLayout(self.emptyStage)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(12)
        self.emptyIcon = IconWidget(FluentIcon.PLAY, self.emptyStage)
        self.emptyIcon.setFixedSize(64, 64)
        self.emptyLabel = BodyLabel(
            '按 Ctrl+O 打开文件，自动加载同目录的图片 / 音频 / 视频', self.emptyStage
        )
        self.emptyLabel.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.emptyIcon, 0, Qt.AlignCenter)
        empty_layout.addWidget(self.emptyLabel, 0, Qt.AlignCenter)

        self.stageStack.addWidget(self.emptyStage)
        self.stageStack.addWidget(self.imageLabel)
        self.stageStack.addWidget(self.videoView)
        self.stageStack.addWidget(self.audioStage)

        # 打开文件/换源期间的中性加载动画（不拦截鼠标）
        self.busy = IndeterminateProgressRing(self.stageStack)
        self.busy.setFixedSize(48, 48)
        self.busy.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.busy.hide()

        # 音量画中提示：↑/↓ 或滚轮改音量时在画面中央闪现半透明提示（不是 InfoBar）
        self.volumeOsd = VolumeOsd(self)

        # 图像工具组（FR-07/08，仅图片/视频出现，可折叠）
        self.imageTools = QWidget(self)
        tools_outer = QHBoxLayout(self.imageTools)
        tools_outer.setContentsMargins(24, 2, 24, 2)
        tools_outer.setSpacing(6)
        self.imageToolsInner = QWidget(self.imageTools)
        inner = QHBoxLayout(self.imageToolsInner)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(4)
        self.rotateCCWBtn = TransparentPushButton('⟲', self.imageToolsInner)
        self.rotateCWBtn = TransparentPushButton('⟳', self.imageToolsInner)
        self.zoomOutBtn = TransparentPushButton('−', self.imageToolsInner)
        self.zoomLabelBtn = TransparentPushButton('100%', self.imageToolsInner)
        self.zoomInBtn = TransparentPushButton('+', self.imageToolsInner)
        for button in (self.rotateCCWBtn, self.rotateCWBtn, self.zoomOutBtn,
                       self.zoomLabelBtn, self.zoomInBtn):
            button.setFixedHeight(30)
            button.setFocusPolicy(Qt.NoFocus)
        self.zoomLabelBtn.setMinimumWidth(64)
        inner.addWidget(self.rotateCCWBtn)
        inner.addWidget(self.rotateCWBtn)
        inner.addSpacing(12)
        inner.addWidget(self.zoomOutBtn)
        inner.addWidget(self.zoomLabelBtn)
        inner.addWidget(self.zoomInBtn)
        inner.addStretch(1)
        self.imageToolsToggle = TransparentToolButton(
            FluentIcon.CHEVRON_DOWN_MED, self.imageTools
        )
        self.imageToolsToggle.setFixedSize(30, 30)
        self.imageToolsToggle.setToolTip('收起/展开图像工具')
        self.imageToolsToggle.setFocusPolicy(Qt.NoFocus)
        tools_outer.addWidget(self.imageToolsInner, 1)
        tools_outer.addWidget(self.imageToolsToggle)

        # 底部 transport
        self.transport = QWidget(self)
        transport_layout = QVBoxLayout(self.transport)
        transport_layout.setContentsMargins(24, 8, 24, 16)
        transport_layout.setSpacing(6)

        self.seekBar = SeekBar(self.transport)
        transport_layout.addWidget(self.seekBar)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.prevBtn = TransparentToolButton(FluentIcon.LEFT_ARROW, self.transport)
        self.seekBackBtn = TransparentPushButton('−5s', self.transport)
        self.playBtn = TransparentToolButton(FluentIcon.PLAY_SOLID, self.transport)
        self.seekFwdBtn = TransparentPushButton('+5s', self.transport)
        self.nextBtn = TransparentToolButton(FluentIcon.RIGHT_ARROW, self.transport)
        self.modeBtn = SplitPushButton(self.transport)
        # 倍速按钮：文字短（1×）时 SplitPushButton 的两半在深色下会像两个按钮，
        # 改用一体式下拉按钮（箭头画在按钮内部）。
        self.speedBtn = DropDownPushButton('1×', self.transport)
        self.bookmarkBtn = TransparentToolButton(FluentIcon.QUICK_NOTE, self.transport)
        self.imageInfoLabel = CaptionLabel('', self.transport)
        self.imageInfoLabel.hide()
        self.playBtn.setFixedSize(44, 44)
        self.playBtn.setIconSize(QSize(20, 20))
        for button in (self.prevBtn, self.nextBtn):
            button.setFixedSize(40, 40)
        for button in (self.seekBackBtn, self.seekFwdBtn):
            button.setFixedHeight(32)
            button.setMinimumWidth(52)
        self.modeBtn.setFixedHeight(32)
        self.modeBtn.setMinimumWidth(96)
        self._update_mode_button()
        self.speedBtn.setFixedHeight(32)
        self.speedBtn.setMinimumWidth(86)
        # 再点一下关闭菜单：吃掉「菜单吃掉 press、只剩 release 回落到按钮」那半拍
        self.speedBtn.installEventFilter(self)
        self._update_speed_button()

        self.volumeBtn = VolumeButton(self.transport)

        controls.addWidget(self.prevBtn)
        controls.addWidget(self.seekBackBtn)
        controls.addWidget(self.playBtn)
        controls.addWidget(self.seekFwdBtn)
        controls.addWidget(self.nextBtn)
        controls.addSpacing(8)
        controls.addWidget(self.modeBtn)
        controls.addWidget(self.speedBtn)
        controls.addWidget(self.bookmarkBtn)
        controls.addWidget(self.imageInfoLabel)
        controls.addStretch(1)
        controls.addWidget(self.volumeBtn)
        transport_layout.addLayout(controls)

        root.addWidget(self.topBar)
        root.addWidget(self.stageStack, 1)
        root.addWidget(self.imageTools)
        root.addWidget(self.transport)

        for widget in (self.prevBtn, self.seekBackBtn, self.playBtn, self.seekFwdBtn,
                       self.nextBtn, self.modeBtn, self.speedBtn, self.volumeBtn,
                       self.deleteBtn, self.openBtn, self.fullscreenBtn,
                       self.favoriteBtn, self.bookmarkBtn, self.drawerBtn):
            widget.setFocusPolicy(Qt.NoFocus)
        self.seekBar.slider.setFocusPolicy(Qt.NoFocus)

        self.seekBar.seekRequested.connect(self._on_seek_requested)
        self.volumeBtn.volumeChanged.connect(self._on_volume_changed)
        # transport 按钮此前只经 ActionRegistry 绑了 tooltip（快捷键能触发、鼠标点了没反应）
        self.playBtn.clicked.connect(self.toggle_play)
        self.prevBtn.clicked.connect(self.prev_file)
        self.nextBtn.clicked.connect(self.next_file)
        self.seekBackBtn.clicked.connect(lambda: self.step_seek(-cfg.seekStep.value))
        self.seekFwdBtn.clicked.connect(lambda: self.step_seek(cfg.seekStep.value))
        self.bookmarkBtn.clicked.connect(self.add_bookmark)
        self.modeBtn.clicked.connect(self.cycle_mode)
        self.modeBtn.dropDownClicked.connect(self._show_mode_menu)
        self.speedBtn.clicked.connect(self._sync_speed_menu_checks)
        self.rotateCCWBtn.clicked.connect(lambda: self.rotate(-90))
        self.rotateCWBtn.clicked.connect(lambda: self.rotate(90))
        self.zoomOutBtn.clicked.connect(lambda: self.zoom_by(1 / ZOOM_STEP))
        self.zoomInBtn.clicked.connect(lambda: self.zoom_by(ZOOM_STEP))
        self.zoomLabelBtn.clicked.connect(self.reset_zoom)
        self.imageToolsToggle.clicked.connect(self._toggle_image_tools)
        self.fullscreenBtn.clicked.connect(self.toggle_fullscreen)

        self._build_mode_menu()
        self._build_speed_menu()

        # 进度条悬停帧预览（FR-12）
        self.preview = FramePreview(self)
        self._frame_grabber = FrameGrabber()
        self._hover_ms = 0
        self._hover_pos = QPoint()
        self._hover_active = False
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(70)
        self._hover_timer.timeout.connect(self._update_hover_preview)
        self.seekBar.slider.hovered.connect(self._on_seek_hover)
        self.seekBar.slider.hoverLeft.connect(self._on_seek_hover_leave)

        # 右侧详情抽屉（I 开关）
        self.drawer = Drawer(self)
        self.drawer.openIndexRequested.connect(self._open_index)
        self.drawer.bookmarkSelected.connect(lambda ms: self.engine.seek(ms))
        self.drawer.bookmarkDeleteRequested.connect(self._delete_bookmark)
        self.seekBar.bookmarkClicked.connect(lambda ms: self.engine.seek(ms))

        # 右侧书签输入浮层：点保存才落库，取消放弃这次书签（FR-14）
        self.bookmarkPopup = BookmarkPopup(self)
        self.bookmarkPopup.submitted.connect(self._save_bookmark)

        # 媒体区滚轮缩放 / 双击全屏
        for target in (self.imageLabel, self.videoView.viewport()):
            target.installEventFilter(self)

    def _build_mode_menu(self) -> None:
        self.modeMenu = RoundMenu(parent=self)
        self.modeMenuActions: list[Action] = []
        for mode in PLAY_MODES:
            action = Action(PLAY_MODE_TEXTS[mode], self.modeMenu, checkable=True)
            action.triggered.connect(lambda _checked=False, m=mode: self.set_mode(m))
            self.modeMenu.addAction(action)
            self.modeMenuActions.append(action)

    def _show_mode_menu(self) -> None:
        current = cfg.playMode.value
        for action, mode in zip(self.modeMenuActions, PLAY_MODES):
            action.setChecked(mode == current)
        self.modeMenu.exec(self.modeBtn.mapToGlobal(QPoint(0, self.modeBtn.height())))

    # ---- 倍速（FR-02 扩展）----
    def _build_speed_menu(self) -> None:
        self.speedMenu = RoundMenu(parent=self)
        self.speedMenuActions: list[Action] = []
        for speed in SPEEDS:
            action = Action(f'{speed:g}×', self.speedMenu, checkable=True)
            action.triggered.connect(lambda _checked=False, s=speed: self.set_speed(s))
            self.speedMenu.addAction(action)
            self.speedMenuActions.append(action)
        # 下拉按钮在 mouseRelease 里自己弹菜单（clicked 先发，用来同步勾选）
        self.speedBtn.setMenu(self.speedMenu)
        # 「点一下开、再点一下关」：RoundMenu.exec 非模态（= show + 动画），
        # 而 DropDownPushButton.mouseReleaseEvent 无条件 _showMenu()，第二次点击
        # 的 release 会把刚关的菜单当场重开。包一层：本次点击是「关」就跳过重开。
        real_show = self.speedBtn._showMenu

        def guarded_show():
            if self._speed_menu_was_open:
                self._speed_menu_was_open = False
                return
            real_show()

        self.speedBtn._showMenu = guarded_show
        self.speedMenu.aboutToHide.connect(self._on_speed_menu_hide)

    def _on_speed_menu_hide(self, *args) -> None:
        # 100ms：只覆盖「弹层在 press 投递前就关了」这种同一事件内的先后差；
        # 拉太长会把紧接着的「再打开」误判成关闭点击
        self._speed_menu_hide_recent = True
        QTimer.singleShot(100, self._clear_speed_hide_recent)

    def _clear_speed_hide_recent(self) -> None:
        self._speed_menu_hide_recent = False

    def _sync_speed_menu_checks(self) -> None:
        current = float(cfg.speed.value)
        for action, speed in zip(self.speedMenuActions, SPEEDS):
            action.setChecked(abs(speed - current) < 1e-6)

    def set_speed(self, rate: float) -> None:
        rate = min(SPEEDS, key=lambda option: abs(option - float(rate)))
        cfg.set(cfg.speed, rate)
        cfg.save()
        self.engine.set_playback_rate(rate)
        self._update_speed_button()

    def cycle_speed(self, direction: int = 1) -> None:
        current = float(cfg.speed.value)
        index = min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - current))
        self.set_speed(SPEEDS[(index + direction) % len(SPEEDS)])

    def _update_speed_button(self) -> None:
        rate = float(cfg.speed.value)
        self.speedBtn.setText(f'{rate:g}×')
        self.speedBtn.setToolTip(
            f'播放速度：{rate:g}×（点击选档，'
            f'{self._action_keys("speed_up", "]")} 加快 / '
            f'{self._action_keys("speed_down", "[")} 减慢）'
        )

    def _wire_engine(self) -> None:
        self.engine.positionChanged.connect(self.seekBar.set_position)
        self.engine.durationChanged.connect(self.seekBar.set_duration)
        self.engine.playingChanged.connect(self._on_playing_changed)
        self.engine.errorOccurred.connect(self._on_error)
        self.engine.mediaEnded.connect(self._on_media_ended)
        self.engine.set_volume(self.volumeBtn.volume)

    # ---------------- 事件 ----------------
    def eventFilter(self, obj, event):
        if obj is self.speedBtn:
            # 倍速下拉「点一下开、再点一下关」：菜单开着时第二次点击，press 与
            # release 都会落到按钮上（RoundMenu 非模态、不占鼠标），release 又无条件
            # _showMenu() 重开 → 看起来只能开不能关。按下时菜单还开着就当场关掉并
            # 记账（无论弹层机制在 press 前后哪一刻关，都由我们这侧兜底）；记账由
            # _showMenu 包装层消费——那一次 release 跳过重开。
            if event.type() == QEvent.MouseButtonPress:
                self._speed_btn_pressed = True
                if self.speedMenu.isVisible():
                    self.speedMenu.close()
                    self._speed_menu_was_open = True
                else:
                    # 弹层抢在 press 投递前就关了（aboutToHide 余温内）：同样算「关」；
                    # 250ms 过期，避免菜单在别处被关掉后误吞下一次正常点击
                    self._speed_menu_was_open = self._speed_menu_hide_recent
            elif event.type() == QEvent.MouseButtonRelease:
                if not self._speed_btn_pressed:
                    return True  # 按钮没收到 press（被弹层吃掉）：吞掉，别重开
                self._speed_btn_pressed = False
        if self._title_renaming and event.type() == QEvent.MouseButtonPress:
            # 编辑期间装的是应用级过滤器：点别处（画面/按钮/标题栏）即收起并提交。
            # 只靠 editingFinished 不管用——舞台控件都是 NoFocus，点了焦点也不转移。
            target = obj if isinstance(obj, QWidget) else None
            inside = target is self.titleEdit or (
                target is not None and self.titleEdit.isAncestorOf(target)
            )
            if not inside:
                self._commit_title_rename()
        if obj is self.titleEdit and self._title_renaming:
            # 全局 QShortcut 绑了 Esc（exit_fullscreen），QLineEdit 不会自己接住
            # ShortcutOverride → 必须先 accept，Esc 才轮得到下面的 KeyPress。
            if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Escape:
                event.accept()
                return True
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self._cancel_title_rename()
                event.accept()
                return True
        if obj is self.titleLabel:
            # 点文件名 = 就地改名（播放页 FR-10 / FR-20）
            if (event.type() == QEvent.MouseButtonRelease
                    and event.button() == Qt.LeftButton):
                self.start_title_rename()
                event.accept()
                return True
        if obj in (self.imageLabel, self.videoView.viewport()):
            if event.type() == QEvent.Wheel:
                if self.current_kind in (IMAGE, VIDEO):
                    delta = event.angleDelta().y()
                    if delta:
                        self.zoom_by(ZOOM_STEP if delta > 0 else 1 / ZOOM_STEP)
                    event.accept()
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                # 点视频画面 = 播放/暂停（双击的第二次 release 由 dblclick 标记吃掉）
                if (obj is self.videoView.viewport()
                        and event.button() == Qt.LeftButton
                        and self.current_kind == VIDEO):
                    if self._skip_video_click:
                        self._skip_video_click = False
                    else:
                        self.toggle_play()
                    event.accept()
                    return True
            elif event.type() == QEvent.MouseButtonDblClick:
                if self.current_kind in (IMAGE, VIDEO):
                    if obj is self.videoView.viewport():
                        self._skip_video_click = True
                    self.toggle_fullscreen()
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    # ---------------- 顶栏标题就地重命名（FR-10 / FR-20） ----------------
    def start_title_rename(self) -> None:
        if self._title_renaming or not (0 <= self.index < len(self.entries)):
            return
        self._rename_stem = self.entries[self.index].path.stem
        self._title_renaming = True
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.titleEdit.setText(self._rename_stem)
        self.titleEdit.selectAll()
        self.titleLabel.hide()
        self.titleEdit.show()
        self.titleEdit.setFocus()

    def _commit_title_rename(self) -> None:
        if not self._title_renaming:
            return
        text = self.titleEdit.text().strip()
        entry = self.entries[self.index] if 0 <= self.index < len(self.entries) else None
        self._end_title_rename()
        if entry is None or not text or text == self._rename_stem:
            return
        rename = getattr(self.window(), 'rename_file', None)
        if rename is not None:
            rename(entry, text)

    def _cancel_title_rename(self) -> None:
        if self._title_renaming:
            self._end_title_rename()

    def _end_title_rename(self) -> None:
        # 先落标志再 hide：hide/clearFocus 会再触发 editingFinished，别二次提交
        self._title_renaming = False
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.titleEdit.hide()
        self.titleEdit.clearFocus()
        self.titleLabel.show()

    # ---------------- 打开 ----------------
    def open_path(self, path: str | Path,
                  queue: list[MediaEntry] | None = None) -> None:
        """打开文件。queue = 资料库当前筛选结果（可选），决定队列成员与顺序。"""
        path = Path(path)
        entries, index = scan_directory(path, cfg.sortMode.value)
        if not entries:
            InfoBar.warning('无法打开', '该目录没有可读的图片 / 音频 / 视频', duration=3000,
                            parent=self.window())
            return
        self.directory_entries = entries
        if queue:
            queue = list(queue)
            queue_index = next(
                (i for i, entry in enumerate(queue) if entry.path == path), -1
            )
        else:
            queue, queue_index = [], -1
        if queue_index < 0:
            # 筛选队列里没有这个文件（例如 CLI 打开的是被筛掉的项）：退回全目录
            queue, queue_index = entries, index
        self.entries = queue
        self.index = queue_index
        self._show_current()
        self.queueChanged.emit()

    def _show_current(self) -> None:
        if not (0 <= self.index < len(self.entries)):
            self._clear_stage()
            return
        entry = self.entries[self.index]
        self._render_token += 1
        token = self._render_token
        self.frameHold.hide()
        self._prepare_current(entry)
        # 标题/工具状态先同步落地；解码/换源放到下一拍，让加载动画先画出来
        self.busy.show()
        self.busy.raise_()
        self._position_busy()
        QTimer.singleShot(0, lambda: self._render_current(token))

    def _prepare_current(self, entry: MediaEntry) -> None:
        self._cancel_title_rename()
        name = entry.path.name
        self.titleLabel.setText(name)
        self.titleLabel.setToolTip(f'{entry.path}\n点击文件名重命名')
        window = self.window()
        if window is not None:
            window.setWindowTitle(name)

        self._zoom = 1.0
        self._rotation = self._load_rotation(entry.path)
        self.imageLabel.reset_pan()

        self.seekBar.reset()
        self._stop_movie()
        self._hover_active = False
        self._hover_timer.stop()
        self.preview.hide()
        self.bookmarkPopup.hide()
        self._sync_controls()
        self._refresh_favorite()
        self._refresh_bookmarks()
        self._refresh_drawer()

    def _render_current(self, token: int) -> None:
        if token != self._render_token or not (0 <= self.index < len(self.entries)):
            return
        entry = self.entries[self.index]
        rate = float(cfg.speed.value)
        try:
            if entry.kind == IMAGE:
                self.engine.set_video_output(None)
                self.engine.stop()
                self._show_image(entry.path)
            elif entry.kind == VIDEO:
                self.engine.set_video_output(self.videoItem)
                self.stageStack.setCurrentWidget(self.videoView)
                self.engine.load(entry.path)
                self.engine.set_playback_rate(rate)
                self.engine.play()
            else:
                self.engine.set_video_output(None)
                self.audioName.setText(entry.path.name)
                self.stageStack.setCurrentWidget(self.audioStage)
                self.engine.load(entry.path)
                self.engine.set_playback_rate(rate)
                self.engine.play()
        finally:
            if token == self._render_token:
                self.busy.hide()
        self._frame_grabber.release()

    def _position_busy(self) -> None:
        hold = getattr(self, 'frameHold', None)
        if hold is not None and hold.isVisible():
            area = self.videoView.viewport().size()
            hold.setGeometry(0, 0, area.width(), area.height())
        area = self.stageStack.size()
        self.busy.move((area.width() - self.busy.width()) // 2,
                       (area.height() - self.busy.height()) // 2)

    def _clear_stage(self) -> None:
        self._render_token += 1
        self.busy.hide()
        self.frameHold.hide()
        self.index = -1
        self._cancel_title_rename()
        self.titleLabel.setText('未打开文件')
        self.titleLabel.setToolTip('')
        self._stop_movie()
        self.stageStack.setCurrentWidget(self.emptyStage)
        self.seekBar.reset()
        window = self.window()
        if window is not None:
            window.setWindowTitle('未打开文件')
        self._sync_controls()

    # ---------------- 图片 ----------------
    def _show_image(self, path: Path) -> None:
        self._stop_movie()
        if path.suffix.lower() == '.gif':
            movie = QMovie(str(path), parent=self)
            movie.frameChanged.connect(self._apply_image_transform)
            self._movie = movie
            movie.start()
        else:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self._on_error(f'无法解码图片：{path.name}')
                return
            self._image_pixmap = pixmap
        self.stageStack.setCurrentWidget(self.imageLabel)
        self._apply_image_transform()

    def _stop_movie(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None

    def _apply_image_transform(self) -> None:
        label_size = self.imageLabel.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            return
        if self._movie is not None:
            pixmap = self._movie.currentPixmap()
        else:
            pixmap = self._image_pixmap
        if pixmap is None or pixmap.isNull():
            return
        if self._rotation % 360:
            pixmap = pixmap.transformed(
                QTransform().rotate(self._rotation), Qt.SmoothTransformation
            )
        fitted = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        target = QSize(max(1, int(fitted.width() * self._zoom)),
                       max(1, int(fitted.height() * self._zoom)))
        self.imageLabel.setPixmap(pixmap.scaled(target, Qt.IgnoreAspectRatio,
                                                Qt.SmoothTransformation))
        # 缩放/旋转/窗口变化后重新约束平移边界（缩回 100% 时自动回到居中）
        self.imageLabel.clamp_pan()
        self.imageLabel.sync_cursor()

    def _apply_video_transform(self) -> None:
        rect = self.videoItem.boundingRect()
        self.videoItem.setTransformOriginPoint(rect.center())
        self.videoItem.setRotation(self._rotation)
        self.videoItem.setScale(self._zoom)

    # ---------------- 缩放 / 旋转（FR-07/08）----------------
    def zoom_by(self, factor: float) -> None:
        if self.current_kind not in (IMAGE, VIDEO):
            return
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * factor))
        self._apply_zoom()

    def reset_zoom(self) -> None:
        if self.current_kind not in (IMAGE, VIDEO):
            return
        self._zoom = 1.0
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        if self.current_kind == IMAGE:
            self._apply_image_transform()
        elif self.current_kind == VIDEO:
            self._apply_video_transform()
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        self.zoomLabelBtn.setText(f'{int(round(self._zoom * 100))}%')

    def rotate(self, degrees: int) -> None:
        if self.current_kind not in (IMAGE, VIDEO):
            return
        self._rotation = (self._rotation + degrees) % 360
        if self.current_kind == IMAGE:
            self._apply_image_transform()
        else:
            self._apply_video_transform()
        self._persist_rotation()

    def _load_rotation(self, path) -> int:
        if self.store is None:
            return 0
        return self.store.get_rotation(path)

    def _persist_rotation(self) -> None:
        if self.store is None or self.current_path is None:
            return
        self.store.set_rotation(self.current_path, self._rotation)

    def _toggle_image_tools(self) -> None:
        self.imageToolsInner.setVisible(not self.imageToolsInner.isVisible())
        icon = (FluentIcon.CHEVRON_DOWN_MED if self.imageToolsInner.isVisible()
                else FluentIcon.CHEVRON_RIGHT_MED)
        self.imageToolsToggle.setIcon(icon)

    # ---------------- 全屏 ----------------
    def toggle_fullscreen(self) -> None:
        window = self.window()
        if window is None:
            return
        if window.isFullScreen():
            window.showNormal()
        else:
            window.showFullScreen()
        self.update_fullscreen_button()

    def exit_fullscreen(self) -> None:
        window = self.window()
        if window is not None and window.isFullScreen():
            window.showNormal()
            self.update_fullscreen_button()

    def update_fullscreen_button(self) -> None:
        """全屏时图标箭头朝内（恢复大小），窗口态朝外（进入全屏）。"""
        full = self.is_fullscreen
        self.fullscreenBtn.setIcon(
            FluentIcon.BACK_TO_WINDOW if full else FluentIcon.FULL_SCREEN
        )
        escape = self._action_keys('exit_fullscreen', 'Esc')
        enter = self._action_keys('fullscreen', 'F')
        self.fullscreenBtn.setToolTip(
            f'退出全屏（{escape} / {enter}）' if full
            else f'全屏（{enter} / 双击画面）'
        )

    @property
    def is_fullscreen(self) -> bool:
        window = self.window()
        return bool(window and window.isFullScreen())

    # ---------------- 控制 ----------------
    @property
    def current_path(self) -> Path | None:
        if 0 <= self.index < len(self.entries):
            return self.entries[self.index].path
        return None

    @property
    def current_kind(self) -> str | None:
        if 0 <= self.index < len(self.entries):
            return self.entries[self.index].kind
        return None

    @property
    def has_media(self) -> bool:
        return self.current_kind in (VIDEO, AUDIO)

    @property
    def has_view(self) -> bool:
        return self.current_kind in (IMAGE, VIDEO)

    def toggle_play(self) -> None:
        if not self.has_media:
            return
        self._release_frame_hold()
        self.engine.toggle()

    def step_seek(self, seconds: int) -> None:
        if not self.has_media:
            return
        self._release_frame_hold()
        duration = self.engine.duration
        if duration <= 0:
            return
        target = self.engine.position + seconds * 1000
        self.engine.seek(max(0, min(duration, target)))

    def step_volume(self, delta: int) -> None:
        self.engine.set_volume(self.engine.volume + delta)
        self.volumeBtn.set_volume(self.engine.volume)
        self.volumeOsd.show_level(self.engine.volume)

    def next_file(self) -> None:
        target = step_index(len(self.entries), self.index, cfg.playMode.value, +1)
        if target is None or target == self.index:
            return
        self.index = target
        self._show_current()

    def prev_file(self) -> None:
        target = step_index(len(self.entries), self.index, cfg.playMode.value, -1)
        if target is None or target == self.index:
            return
        self.index = target
        self._show_current()

    # ---- 播放模式（FR-11）----
    def set_mode(self, mode: str) -> None:
        cfg.set(cfg.playMode, mode)
        cfg.save()
        self._update_mode_button()

    def cycle_mode(self) -> None:
        try:
            current = PLAY_MODES.index(cfg.playMode.value)
        except ValueError:
            current = 1
        self.set_mode(PLAY_MODES[(current + 1) % len(PLAY_MODES)])

    def _update_mode_button(self) -> None:
        mode = cfg.playMode.value
        self.modeBtn.setText(PLAY_MODE_TEXTS.get(mode, '列表循环'))
        self.modeBtn.setToolTip(
            f'播放模式：{PLAY_MODE_TEXTS.get(mode, mode)}'
            f'（{self._action_keys("play_mode", "M")} 切换，箭头直选）'
        )

    def _on_media_ended(self) -> None:
        if not self.has_media:
            return
        target = auto_index(len(self.entries), self.index, cfg.playMode.value)
        if target is None:
            # 单曲播放：回到 0:00 并暂停（停在结尾会黑屏）。
            # FFmpeg 后端在 EndOfMedia 上偶发把 setPosition(0) 当成续播，
            # 80ms 后再压一次暂停并复位，保证停在首帧。
            self._reset_playback_to_start()
            return
        self.index = target
        self._show_current()

    # ---- 悬停帧预览（FR-12）----
    def _reset_playback_to_start(self) -> None:
        """单曲播完回到 0:00 并暂停。

        EndOfMedia 上直接 setPosition(0) 会被 FFmpeg 后端当成续播（实测必现），
        改为重新装载并在就绪时暂停（MediaEngine.load_paused）；该后端暂停在 0
        时不出首帧，画面用 cv2 取帧快照顶住，按播放时再撤掉。
        """
        path = self.current_path
        if path is not None:
            self.engine.load_paused(path)
            self._show_first_frame_hold(path)
        self.seekBar.set_position(0)
        self.seekBar.slider.setValue(0)

    def _show_first_frame_hold(self, path) -> None:
        image = self._frame_grabber.frame_at(path, 0)
        if image is None or image.isNull():
            self._release_frame_hold()
            return
        self._hold_image = image
        self._hold_active = True
        self._apply_frame_hold()
        # 换源过程中后端可能短暂发 Playing/状态事件，150ms 后再钉一次快照
        QTimer.singleShot(150, self._reassert_frame_hold)

    def _apply_frame_hold(self) -> None:
        if self._hold_image is None:
            return
        area = self.videoView.viewport().size()
        scaled = self._hold_image.scaled(area, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
        self.frameHold.setPixmap(QPixmap.fromImage(scaled))
        self.frameHold.setGeometry(0, 0, area.width(), area.height())
        self.frameHold.show()
        self.frameHold.raise_()

    def _reassert_frame_hold(self) -> None:
        if self._hold_active and not self.engine.is_playing:
            self._apply_frame_hold()

    def _release_frame_hold(self) -> None:
        self._hold_active = False
        if self.frameHold.isVisible():
            self.frameHold.hide()

    def _on_seek_hover(self, ms: int, global_pos: QPoint) -> None:
        if not self.has_media:
            return
        self._hover_ms = ms
        self._hover_pos = global_pos
        self._hover_active = True
        self._hover_timer.start()

    def _on_seek_hover_leave(self) -> None:
        """离开进度条：先停掉待发的延迟预览，再隐藏。

        不停 timer 的话，最后一帧 hover 事件后的 70ms 定时器仍会把浮层
        重新弹出来（此时鼠标已经移走，也就再不会有 hoverLeft 来收它）。
        """
        self._hover_active = False
        self._hover_timer.stop()
        self.preview.hide()

    def _update_hover_preview(self) -> None:
        if not self._hover_active:
            return
        if not self.has_media or self.current_path is None:
            return
        if self.current_kind != VIDEO:
            # 音频没有画面：不弹浮层，免得时间码盖住进度点
            self.preview.hide()
            return
        image = self._frame_grabber.frame_at(self.current_path, self._hover_ms)
        if image is None or image.isNull():
            self.preview.hide()
            return
        self.preview.set_content(image)
        self.preview.show_at(self._hover_pos)

    # ---- 收藏 / 书签 / 抽屉（FR-13/14）----
    def toggle_favorite(self) -> None:
        if self.store is None or self.current_path is None:
            return
        window = self.window()
        handler = getattr(window, 'toggle_favorite', None)
        if handler is not None:
            # 统一走窗口层：卡片 ♥ 与顶栏 ♥ 都要同一条提示/刷新路径
            handler(self.current_path)
            self.favoriteChanged.emit()
            return
        self.store.toggle_favorite(self.current_path)
        self._refresh_favorite()
        self.favoriteChanged.emit()
        self._refresh_drawer()

    def _refresh_favorite(self) -> None:
        favorite = bool(
            self.store and self.current_path and self.store.is_favorite(self.current_path)
        )
        accent = qconfig.themeColor.value
        accent = QColor(accent) if accent is not None else QColor('#009faa')
        ink = QColor(255, 255, 255, 230) if isDarkTheme() else QColor(55, 55, 55, 220)
        # 实心 = 已收藏，描边 = 未收藏（颜色只是辅助）
        self.favoriteBtn.setIcon(heart_icon(accent if favorite else ink, 18, favorite))
        favorite_key = self._action_keys('favorite', 'E')
        self.favoriteBtn.setToolTip(
            f'取消收藏（{favorite_key}）' if favorite else f'收藏（{favorite_key}）'
        )

    def add_bookmark(self) -> None:
        """点一下弹出输入框，再点一下关闭（丢弃这次输入）；保存才写库。"""
        if self.store is None or not self.has_media or self.current_path is None:
            return
        if self.bookmarkPopup.isVisible():
            self.bookmarkPopup.cancel()
            return
        if self.engine.duration <= 0:
            return
        self.bookmarkPopup.prompt(self.engine.position)

    def _save_bookmark(self, label: str) -> None:
        path = self.current_path
        if self.store is None or path is None:
            return
        pos = self.bookmarkPopup.position_ms
        self.store.add_bookmark(path, pos, label)
        self._refresh_bookmarks()
        self._refresh_drawer()
        text = format_time(pos) + (f'  {label}' if label else '')
        InfoBar.success('已保存书签', text, duration=1800, parent=self.window())

    def _delete_bookmark(self, bookmark_id: int) -> None:
        if self.store is None:
            return
        self.store.delete_bookmark(bookmark_id)
        self._refresh_bookmarks()
        self._refresh_drawer()

    def _refresh_bookmarks(self) -> None:
        marks = []
        if self.store is not None and self.current_path is not None:
            marks = [pos for _, pos, _ in self.store.bookmarks(self.current_path)]
        self.seekBar.set_bookmarks(marks)

    def _refresh_drawer(self, force: bool = False) -> None:
        if self.store is None:
            return
        # 播放列表是 O(文件数) 的 QListWidget 填充：抽屉没开就不建
        if force or self.drawer.isVisible():
            self.drawer.set_playlist(self.entries, self.index)
        marks = (self.store.bookmarks(self.current_path)
                 if self.current_path is not None else [])
        self.drawer.set_bookmarks(marks, format_time)
        self.drawer.set_info(self._info_lines())

    def _info_lines(self) -> list[tuple[str, str]]:
        path = self.current_path
        if path is None:
            return [('状态', '未打开文件')]
        kind_text = {IMAGE: '图片', VIDEO: '视频', AUDIO: '音频'}.get(
            self.current_kind or '', '未知'
        )
        try:
            size = path.stat().st_size
            size_text = f'{size / 1024:.1f} KB' if size < 1024 * 1024 \
                else f'{size / 1024 / 1024:.2f} MB'
        except OSError:
            size_text = '未知'
        lines = [
            ('文件名', path.name),
            ('类型', kind_text),
            ('大小', size_text),
            ('路径', str(path)),
        ]
        if self.has_media and self.engine.duration > 0:
            lines.append(('时长', format_time(self.engine.duration)))
        return lines

    def toggle_drawer(self) -> None:
        if self.drawer.isVisible() and getattr(self.drawer, '_target_visible', False):
            self.drawer.hide_drawer()
        else:
            self._refresh_drawer(force=True)
            self.drawer.show_drawer()

    def _open_index(self, index: int) -> None:
        if 0 <= index < len(self.entries):
            self.index = index
            self._show_current()

    # ---- 删除（FR-09）----
    def delete_current(self, confirm: bool = True) -> bool:
        if not (0 <= self.index < len(self.entries)):
            return False
        window = self.window()
        delete_paths = getattr(window, 'delete_paths', None)
        if delete_paths is None:
            return False
        return delete_paths([self.entries[self.index].path], confirm)

    def remove_paths(self, paths: set[Path]) -> None:
        """从队列中移除已删除的文件并切到相邻项（由窗口在回收站删除成功后调用）。"""
        if not paths:
            return
        self.directory_entries = [e for e in self.directory_entries
                                  if e.path not in paths]
        if not self.entries:
            return
        current_path = (self.entries[self.index].path
                        if 0 <= self.index < len(self.entries) else None)
        self.entries = [e for e in self.entries if e.path not in paths]
        if not self.entries:
            self._clear_stage()
            self.queueChanged.emit()
            return
        if current_path in paths or current_path is None:
            self.index = min(self.index, len(self.entries) - 1)
        else:
            self.index = next(
                (i for i, e in enumerate(self.entries) if e.path == current_path), 0
            )
        self._show_current()
        self.queueChanged.emit()

    # ---------------- 同步 ----------------
    def _sync_controls(self) -> None:
        kind = self.current_kind
        if kind != self._synced_kind:
            self._synced_kind = kind
            self.kindChanged.emit()
        media = self.has_media
        image = self.current_kind == IMAGE
        for button in (self.playBtn, self.seekBackBtn, self.seekFwdBtn, self.volumeBtn,
                       self.speedBtn):
            button.setEnabled(media)
        multi = len(self.entries) > 1
        self.prevBtn.setEnabled(multi)
        self.nextBtn.setEnabled(multi)
        self.deleteBtn.setEnabled(self.current_kind is not None)
        self.imageTools.setVisible(self.current_kind in (IMAGE, VIDEO))
        self.bookmarkBtn.setEnabled(media)

        # 图片没有时间轴：底栏换成「上一张 / 序号 / 下一张」，不摆一排禁用控件
        self.seekBar.setVisible(not image)
        for widget in (self.seekBackBtn, self.playBtn, self.seekFwdBtn, self.modeBtn,
                       self.speedBtn, self.bookmarkBtn, self.volumeBtn):
            widget.setVisible(not image)
        self.imageInfoLabel.setVisible(image)
        if image and 0 <= self.index < len(self.entries):
            self.imageInfoLabel.setText(f'{self.index + 1} / {len(self.entries)}')

        self._update_zoom_label()
        if media:
            self.playBtn.setIcon(
                FluentIcon.PAUSE_BOLD if self.engine.is_playing else FluentIcon.PLAY_SOLID
            )

    def _on_playing_changed(self, playing: bool) -> None:
        self.playBtn.setIcon(FluentIcon.PAUSE_BOLD if playing else FluentIcon.PLAY_SOLID)

    def _on_seek_requested(self, ms: int) -> None:
        self._release_frame_hold()
        self.engine.seek(ms)

    def _on_volume_changed(self, volume: int) -> None:
        self.engine.set_volume(volume)
        self.volumeOsd.show_level(volume)

    def _action_keys(self, action_id: str, default: str = '') -> str:
        """动作当前键位的显示形态（含帮助页自定义改绑），用于 tooltip/文案。"""
        registry = self.registry
        if registry is not None and action_id in registry.actions:
            sequences = registry.action(action_id).shortcuts()
            if sequences:
                return ' / '.join(display_sequence(s) for s in sequences)
        return default

    def refresh_shortcut_tooltips(self) -> None:
        """步长 / 自定义键位变更后同步按钮文字与 tooltip（FR-16）。"""
        n = cfg.seekStep.value
        self.seekBackBtn.setText(f'−{n}s')
        self.seekFwdBtn.setText(f'+{n}s')
        self.seekBackBtn.setToolTip(
            f'后退 {n} 秒（{self._action_keys("seek_back", "←")}）')
        self.seekFwdBtn.setToolTip(
            f'前进 {n} 秒（{self._action_keys("seek_forward", "→")}）')
        self.prevBtn.setToolTip(
            f'上一个文件（{self._action_keys("prev_file", "← / Ctrl+←")}）')
        self.nextBtn.setToolTip(
            f'下一个文件（{self._action_keys("next_file", "→ / Ctrl+→")}）')
        self.playBtn.setToolTip(
            f'播放/暂停（{self._action_keys("play_pause", "Space")}）')
        self.rotateCCWBtn.setToolTip(
            f'逆时针旋转 90°（{self._action_keys("rotate_ccw", "Ctrl+L")}）')
        self.rotateCWBtn.setToolTip(
            f'顺时针旋转 90°（{self._action_keys("rotate_cw", "Ctrl+R")}）')
        self.zoomInBtn.setToolTip(
            f'放大（滚轮上 / {self._action_keys("zoom_in", "=")}）')
        self.zoomOutBtn.setToolTip(
            f'缩小（滚轮下 / {self._action_keys("zoom_out", "-")}）')
        self.zoomLabelBtn.setToolTip(
            f'缩放重置为 100%（{self._action_keys("zoom_reset", "Ctrl+0")}）')
        self.update_fullscreen_button()
        self.bookmarkBtn.setToolTip(
            f'添加书签（{self._action_keys("bookmark_add", "B")}，输入内容后保存）')
        self.drawerBtn.setToolTip(
            f'详情抽屉（{self._action_keys("drawer_toggle", "I")}）')
        self.emptyLabel.setText(
            f'按 {self._action_keys("open_file", "Ctrl+O")} 打开文件，'
            '自动加载同目录的图片 / 音频 / 视频'
        )

    def _on_error(self, message: str) -> None:
        logger().warning('播放失败：%s（%s）', message, self.current_path)
        InfoBar.warning('播放失败', message, duration=4000, parent=self.window())

    # ---------------- 布局 ----------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_busy()
        self.volumeOsd.reposition()
        self._apply_image_transform()
        if self.current_kind == VIDEO:
            self._apply_video_transform()
        self.drawer.reposition()
        if self.bookmarkPopup.isVisible():
            self.bookmarkPopup.place()
