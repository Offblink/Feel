"""设置页：分组折叠卡片（SPEC §5.1 / FR-15）。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    ExpandLayout,
    FluentIcon,
    OptionsSettingCard,
    RangeSettingCard,
    ScrollArea,
    SettingCard,
    SettingCardGroup,
    SwitchSettingCard,
    TitleLabel,
    TransparentPushButton,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
    setTheme,
    Theme,
)

from ... import logs
from ...config import PLAY_MODE_TEXTS, PLAY_MODES, cfg


class ThemeSettingCard(SettingCard):
    """主题卡片：右侧是深浅主题图标按钮（主题不是开关，不给 Off/On 文案）。

    点击走窗口的渐变过渡（Ctrl+T 同一条路径）；图标显示当前主题，
    tooltip 说明点击后的结果。
    """

    def __init__(self, parent=None):
        super().__init__(FluentIcon.BRIGHTNESS, '主题', '深浅主题切换（Ctrl+T）', parent)
        self.themeButton = TransparentToolButton(self)
        self.themeButton.setFixedSize(36, 36)
        self.themeButton.setFocusPolicy(Qt.NoFocus)
        self.themeButton.clicked.connect(self._on_clicked)
        self.hBoxLayout.addWidget(self.themeButton, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        qconfig.themeChangedFinished.connect(self._sync)
        self._sync()

    def _sync(self, *args) -> None:
        dark = isDarkTheme()
        self.themeButton.setIcon(
            FluentIcon.QUIET_HOURS if dark else FluentIcon.BRIGHTNESS
        )
        registry = getattr(self.window(), 'registry', None)
        if registry is not None and 'toggle_theme' in registry.actions:
            sequences = registry.action('toggle_theme').shortcuts()
            toggle_key = ' / '.join(sequences) or 'Ctrl+T'
        else:
            toggle_key = 'Ctrl+T'
        self.themeButton.setToolTip(
            f'深色主题（点击切到浅色，{toggle_key}）' if dark
            else f'浅色主题（点击切到深色，{toggle_key}）'
        )

    def _on_clicked(self) -> None:
        window = self.window()
        toggle = getattr(window, 'toggle_theme', None)
        if toggle is not None:
            toggle()
        else:
            setTheme(Theme.LIGHT if isDarkTheme() else Theme.DARK, save=True)


class LogSettingCard(SettingCard):
    """运行日志入口：左侧说明，右侧「打开日志 / 打开目录」两个按钮。"""

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.DOCUMENT,
            '运行日志',
            f'{logs.LOG_PATH}（启动、打开/改名/删除、播放失败、未捕获异常都写入）',
            parent,
        )
        self.openBtn = TransparentPushButton('打开日志', self)
        self.openBtn.setIcon(FluentIcon.DOCUMENT)
        self.openFolderBtn = TransparentPushButton('打开目录', self)
        self.openFolderBtn.setIcon(FluentIcon.FOLDER)
        self.openBtn.clicked.connect(logs.open_log_file)
        self.openFolderBtn.clicked.connect(logs.open_log_folder)
        self.hBoxLayout.addWidget(self.openBtn, 0, Qt.AlignRight)
        self.hBoxLayout.addWidget(self.openFolderBtn, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class SettingsPage(ScrollArea):
    """设置页。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('settingsPage')
        self.scrollWidget = QWidget()
        self.scrollWidget.setObjectName('settingsScrollWidget')
        self.expandLayout = ExpandLayout(self.scrollWidget)

        self.settingLabel = TitleLabel('设置', self)

        self.playGroup = SettingCardGroup('播放', self.scrollWidget)
        self.seekCard = RangeSettingCard(
            cfg.seekStep,
            FluentIcon.SYNC,
            '快进/快退时长',
            '← / → 每次跳转的秒数',
            self.playGroup,
        )
        self.volumeCard = RangeSettingCard(
            cfg.volumeStep,
            FluentIcon.SPEAKERS,
            '音量步长',
            '↑ / ↓ 每次调整的百分比',
            self.playGroup,
        )
        self.modeCard = OptionsSettingCard(
            cfg.playMode,
            FluentIcon.ALBUM,
            '默认播放模式',
            '音视频播放结束后的行为',
            texts=[PLAY_MODE_TEXTS[m] for m in PLAY_MODES],
            parent=self.playGroup,
        )
        self.playGroup.addSettingCard(self.seekCard)
        self.playGroup.addSettingCard(self.volumeCard)
        self.playGroup.addSettingCard(self.modeCard)

        self.uiGroup = SettingCardGroup('界面', self.scrollWidget)
        self.themeCard = ThemeSettingCard(self.uiGroup)
        self.uiGroup.addSettingCard(self.themeCard)

        self.libraryGroup = SettingCardGroup('资料库', self.scrollWidget)
        self.searchCard = SwitchSettingCard(
            FluentIcon.SEARCH,
            '图片搜索',
            '按图片里的文字搜索：开着才显示资料库搜索框（识别在后台静默进行）',
            cfg.ocrEnabled,
            self.libraryGroup,
        )
        self.libraryGroup.addSettingCard(self.searchCard)

        self.fileGroup = SettingCardGroup('文件', self.scrollWidget)
        self.deleteCard = SwitchSettingCard(
            FluentIcon.DELETE,
            '直接删除',
            '删除时直接移入回收站，不再弹确认框（默认关，避免误删）',
            cfg.directDelete,
            self.fileGroup,
        )
        self.fileGroup.addSettingCard(self.deleteCard)

        self.logGroup = SettingCardGroup('日志', self.scrollWidget)
        self.logCard = LogSettingCard(self.logGroup)
        self.logGroup.addSettingCard(self.logCard)

        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 20, 36, 36)
        self.expandLayout.addWidget(self.playGroup)
        self.expandLayout.addWidget(self.uiGroup)
        self.expandLayout.addWidget(self.libraryGroup)
        self.expandLayout.addWidget(self.fileGroup)
        self.expandLayout.addWidget(self.logGroup)

        self.setHorizontalScrollBarPolicy(
            self.horizontalScrollBarPolicy().ScrollBarAlwaysOff
        )
        self.setViewportMargins(0, 80, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setStyleSheet('QScrollArea{background: transparent; border: none}')
        self.scrollWidget.setStyleSheet('QWidget{background: transparent}')

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.settingLabel.move(36, 30)
