"""帮助页：使用说明 + 快捷键速查，键位从 ActionRegistry 实时取、可点击改绑。

键帽（ShortcutChip）点击进入捕获态：按下的下一个键成为该动作的新主快捷键
（写进 cfg.Shortcuts.Custom 持久化），Esc / 点别处 / 失焦取消；与现有动作
撞键时弹 InfoBar 警告并保持捕获态等下一个键。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    InfoBar,
    ScrollArea,
    SimpleCardWidget,
    StrongBodyLabel,
    TitleLabel,
)

from ...actions import ActionRegistry, display_sequence
from ...config import cfg
from ...logs import logger

log = logger()

# (分组, [(键段, 动作说明, 备注)])
# 键段元素：'@动作id' → 可点击键帽（文本 = 该动作当前全部键位），其余为普通说明文字
SECTIONS: list[tuple[str, list[tuple[tuple[str, ...], str, str]]]] = [
    ('播放与查看', [
        (('@play_pause', '/ 点视频画面'), '播放 / 暂停', '双击画面也可以进全屏'),
        (('@seek_back', '@seek_forward'), '后退 / 前进 N 秒',
         '仅视频；N 在设置页改，默认 5 秒'),
        (('@prev_file', '@next_file'), '上一个 / 下一个文件',
         '非视频里 ←/→ 直接切换；视频里 ←/→ 是快进快退，用 Ctrl+← / Ctrl+→ 切换'),
        (('@volume_up', '@volume_down'), '音量 ±V%', '画面中央有半透明音量提示'),
        (('@play_mode',), '播放模式', '单曲 / 列表循环 / 单曲循环 / 随机'),
        (('@speed_up', '@speed_down'), '倍速 ±档', '0.5×–2×，换文件后保持'),
        (('@bookmark_add',), '添加书签', '输入内容后保存；Esc 放弃本次'),
        (('@drawer_toggle',), '详情抽屉', '播放列表 / 书签 / 文件信息'),
        (('@rotate_ccw', '@rotate_cw'), '逆 / 顺时针旋转 90°', '仅图片与视频'),
        (('滚轮 /', '@zoom_in', '/', '@zoom_out'), '缩放',
         '放大后按住左键可拖动画面'),
        (('@zoom_reset',), '缩放重置为 100%', ''),
        (('@favorite',), '收藏 / 取消收藏', '♥ 实心 = 已收藏'),
        (('@fullscreen',), '全屏', 'Esc 退出全屏'),
    ]),
    ('文件', [
        (('@open_file',), '打开文件', '自动加载同目录的图片 / 音频 / 视频'),
        (('@open_folder',), '打开文件夹', '只加载目录到资料库，不跳页、不自动播放'),
        (('@delete_file',), '删除到回收站', '默认弹确认，设置页「直接删除」可关'),
        (('@rename_selected',), '重命名（资料库单选）', '也可悬停卡片左上角点铅笔'),
        (('点击文件名',), '就地重命名当前文件', 'Enter 提交 / Esc 取消 / 点别处收起'),
    ]),
    ('资料库', [
        (('@select_all',), '全选 / 取消全选', '只作用于当前筛选结果'),
        (('@open_selected',), '打开选中', '双击卡片同样打开'),
        (('@delete_selected',), '删除选中', '选中多个时批量移入回收站'),
        (('@focus_search',), '聚焦图片搜索框', '图片搜索关闭时不可用'),
        (('@rescan_ocr',), '刷新', '重扫当前目录并重跑 OCR'),
        (('鼠标拖拽',), '涂抹多选', '起笔卡片已选 = 这一笔取消'),
    ]),
    ('界面', [
        (('@goto_player', '@goto_shelf', '@goto_settings', '@goto_help'),
         '播放 / 资料库 / 设置 / 帮助', ''),
        (('@toggle_theme',), '深浅主题切换', '径向渐变过渡；设置页图标按钮同效'),
        (('@exit_fullscreen',), '退出全屏 / 关闭浮层', ''),
    ]),
]

TIPS: list[str] = [
    '打开任意媒体文件后，同目录的图片 / 音频 / 视频自动成为浏览队列；资料库以卡片墙展示同一批文件。',
    '卡片右上角 ♥ 常驻（实心=已收藏、描边=未收藏）；悬停时左上角出现重命名与删除。',
    '删除的文件进 Windows 回收站；设置页「文件 → 直接删除」打开后不再弹确认框。',
    '图片搜索开着时后台静默识别图片文字（首次较慢），结果按文件缓存，下次打开秒回。',
    '排序（名称 / 时间）同时作用于资料库与播放队列，切换排序不会打断当前文件。',
    '设置里的快进秒数、音量步长实时生效，播放页按钮文字与浮层提示同步更新。',
    '文件关联：把 run.bat 设为「打开方式」，或命令行 run.bat <文件|目录> 直接打开。',
    '资料库的分类 / 扩展名 / 图片搜索筛选同时决定播放队列；排序决定队列顺序（上一/下一只在筛选结果里走）。',
    '资料库「打开文件夹」只加载目录，不会跳页或自动播放；点卡片才打开文件。',
    '出问题先看设置页「日志」：feel.log 里记录了启动、打开/改名/删除、播放失败与未捕获异常。',
]

CHIP_STYLE = (
    'QLabel{border: 1px solid rgba(120, 120, 120, 110); border-radius: 5px;'
    ' padding: 2px 8px;}'
    'QLabel:hover{border-color: rgba(120, 120, 120, 210);}'
)

# 捕获态里「只按修饰键」不构成键位
MODIFIER_KEYS = {
    Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr,
    Qt.Key_Super_L, Qt.Key_Super_R, Qt.Key_Hyper_L, Qt.Key_Hyper_R,
}


class ShortcutChip(QLabel):
    """可点击键帽：点击进入捕获态，按下的下一个键成为新快捷键。"""

    def __init__(self, action_id: str, page: 'HelpPage'):
        super().__init__(page)
        self.action_id = action_id
        self.page = page
        self._capturing = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        font = self.font()
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(CHIP_STYLE)
        self.setToolTip('点击改绑这个快捷键：按新键提交，Esc 取消')
        self.refresh()

    def refresh(self) -> None:
        """把键帽文本同步成动作的当前键位（捕获提示词不被外部刷新覆盖）。"""
        if self._capturing:
            return
        keys = self.page.action_keys(self.action_id)
        self.setText(keys or '—')

    # ---- 捕获 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            if not self._capturing:
                self._capturing = True
                self.setText('按下新快捷键…')
            event.accept()
            return
        super().mousePressEvent(event)

    def _cancel_capture(self) -> None:
        if self._capturing:
            self._capturing = False
            self.refresh()

    def event(self, ev):
        if self._capturing:
            if ev.type() == QEvent.ShortcutOverride:
                # 别让全局 QShortcut（Esc/F5/Ctrl+…）抢走捕获中的按键
                ev.accept()
                return True
            if ev.type() == QEvent.FocusOut:
                # 点别处 / 切走窗口：放弃本次改键
                self._cancel_capture()
        return super().event(ev)

    def keyPressEvent(self, ev):
        if not self._capturing:
            super().keyPressEvent(ev)
            return
        key = ev.key()
        if key in MODIFIER_KEYS or key == Qt.Key_unknown:
            return  # 只按修饰键：继续等组合键
        if key == Qt.Key_Escape:
            self._cancel_capture()
            return
        sequence = QKeySequence(ev.keyCombination())
        if sequence.isEmpty():
            return
        if self.page.commit_shortcut(self.action_id, sequence.toString()):
            self._capturing = False
            self.refresh()
        # 冲突时 commit_shortcut 已弹警告：保持捕获态让用户重按


class HelpPage(ScrollArea):
    """使用说明书：分组快捷键表（可改键）+ 要点 + 已知限制。

    内容在 `bind_registry` 里构建（键帽要从注册表取键位），FeelWindow
    在动作全部注册后调用一次；改键靠 registry.shortcutsChanged 刷新键帽。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('helpPage')
        self.registry: ActionRegistry | None = None
        self.chips: dict[str, ShortcutChip] = {}
        self.scrollWidget = QWidget()
        self.scrollWidget.setObjectName('helpScrollWidget')
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            self.horizontalScrollBarPolicy().ScrollBarAlwaysOff
        )
        self.setViewportMargins(0, 80, 0, 20)
        self.setStyleSheet('QScrollArea{background: transparent; border: none}')
        self.scrollWidget.setStyleSheet('QWidget{background: transparent}')
        self.settingLabel = TitleLabel('帮助', self)

        self.contentLayout = QVBoxLayout(self.scrollWidget)
        self.contentLayout.setContentsMargins(36, 20, 36, 36)
        self.contentLayout.setSpacing(18)

    # ---- 构建 ----
    def bind_registry(self, registry: ActionRegistry) -> None:
        if self.registry is not None:
            return
        self.registry = registry
        registry.shortcutsChanged.connect(self._on_shortcuts_changed)

        layout = self.contentLayout
        intro = BodyLabel(
            'Feel 是本地图片 / 音频 / 视频查看器。下面按场景列出全部快捷键，'
            '点键帽可以改成你自己的键（冲突会提示）；界面按钮悬停也能看到同样的提示。'
        )
        intro.setWordWrap(True)
        layout.addWidget(_card('快速上手', [intro]))

        for title, rows in SECTIONS:
            layout.addWidget(_card(title, [
                self._shortcut_row(segments, action, note)
                for segments, action, note in rows
            ]))

        tip_labels = []
        for tip in TIPS:
            label = BodyLabel('· ' + tip)
            label.setWordWrap(True)
            tip_labels.append(label)
        layout.addWidget(_card('使用说明', tip_labels))

        limit = CaptionLabel(
            '已知限制：音频播放中切换主题偶发冻屏（qfluentwidgets 组件问题，已决定不规避）。'
        )
        limit.setWordWrap(True)
        layout.addWidget(_card('已知限制', [limit]))
        layout.addStretch(1)

    def _shortcut_row(self, segments: tuple[str, ...], action: str,
                      note: str) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(16)

        keys_box = QWidget()
        keys_lay = QHBoxLayout(keys_box)
        keys_lay.setContentsMargins(0, 0, 0, 0)
        keys_lay.setSpacing(8)
        for segment in segments:
            if segment.startswith('@'):
                chip = ShortcutChip(segment[1:], self)
                self.chips[chip.action_id] = chip
                keys_lay.addWidget(chip)
            else:
                keys_lay.addWidget(StrongBodyLabel(segment))
        keys_lay.addStretch(1)
        keys_box.setMinimumWidth(200)

        act = BodyLabel(action)
        act.setMinimumWidth(190)
        hint = CaptionLabel(note)
        hint.setWordWrap(True)
        lay.addWidget(keys_box, 0)
        lay.addWidget(act, 0)
        lay.addWidget(hint, 1)
        return row

    # ---- 改键 ----
    def action_keys(self, action_id: str) -> str:
        """动作当前全部键位的显示形态（'← / Ctrl+←'）。"""
        action = self.registry.action(action_id)
        return ' / '.join(display_sequence(s) for s in action.shortcuts())

    def commit_shortcut(self, action_id: str, sequence: str) -> bool:
        """键帽捕获到的新键：查冲突 → 改绑 → 持久化。"""
        conflicts = self.registry.conflicts(action_id, sequence)
        if conflicts:
            names = '、'.join(self.registry.action(c).name for c in conflicts)
            InfoBar.warning(
                '快捷键冲突',
                f'{sequence} 已被「{names}」占用，请换一个键',
                duration=3500, parent=self.window(),
            )
            return False
        self.registry.set_shortcut(action_id, sequence)
        overrides = dict(cfg.customShortcuts.value)
        overrides[action_id] = sequence
        cfg.set(cfg.customShortcuts, overrides)
        log.info('快捷键改绑：%s = %s', action_id, sequence)
        return True

    def _on_shortcuts_changed(self, action_id: str) -> None:
        chip = self.chips.get(action_id)
        if chip is not None:
            chip.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.settingLabel.move(36, 30)


def _card(title: str, children: list[QWidget]) -> SimpleCardWidget:
    card = SimpleCardWidget()
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 14, 20, 14)
    lay.setSpacing(2)
    head = StrongBodyLabel(title)
    lay.addWidget(head)
    lay.addSpacing(6)
    for child in children:
        lay.addWidget(child)
    return card
