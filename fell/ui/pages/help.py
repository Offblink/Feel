"""帮助页：使用说明 + 快捷键速查（重点在快捷键，内容与 ActionRegistry 保持一致）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ScrollArea,
    SimpleCardWidget,
    StrongBodyLabel,
    TitleLabel,
)

# (分组, [(快捷键, 动作, 备注)])
SECTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('播放与查看', [
        ('Space / 点视频画面', '播放 / 暂停', '双击画面也可以进全屏'),
        ('← / →', '后退 / 前进 N 秒', 'N 在设置页改，默认 5 秒'),
        ('Ctrl+← / Ctrl+→', '上一个 / 下一个文件', ''),
        ('↑ / ↓', '音量 ±V%', '画面中央有半透明音量提示'),
        ('M', '播放模式', '单曲 / 列表循环 / 单曲循环 / 随机'),
        ('] / [', '倍速 ±档', '0.5×–2×，换文件后保持'),
        ('B', '添加书签', '输入内容后保存；Esc 放弃本次'),
        ('I', '详情抽屉', '播放列表 / 书签 / 文件信息'),
        ('Ctrl+L / Ctrl+R', '逆 / 顺时针旋转 90°', '仅图片与视频'),
        ('滚轮 / = / -', '缩放', '放大后按住左键可拖动画面'),
        ('Ctrl+0', '缩放重置为 100%', ''),
        ('E', '收藏 / 取消收藏', '♥ 实心 = 已收藏'),
        ('F', '全屏', 'Esc 退出全屏'),
    ]),
    ('文件', [
        ('Ctrl+O', '打开文件', '自动加载同目录的图片 / 音频 / 视频'),
        ('Ctrl+Shift+O', '打开文件夹', '只加载目录到资料库，不跳页、不自动播放'),
        ('Del', '删除到回收站', '默认弹确认，设置页「直接删除」可关'),
        ('F2', '重命名（资料库单选）', '也可悬停卡片左上角点铅笔'),
        ('点击文件名', '就地重命名当前文件', 'Enter 提交 / Esc 取消 / 点别处收起'),
    ]),
    ('资料库', [
        ('Ctrl+A', '全选 / 取消全选', '只作用于当前筛选结果'),
        ('Enter', '打开选中', '双击卡片同样打开'),
        ('Ctrl+F', '聚焦图片搜索框', '图片搜索关闭时不可用'),
        ('F5', '刷新', '重扫当前目录并重跑 OCR'),
        ('鼠标拖拽', '涂抹多选', '起笔卡片已选 = 这一笔取消'),
    ]),
    ('界面', [
        ('Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4', '播放 / 资料库 / 设置 / 帮助', ''),
        ('Ctrl+T', '深浅主题切换', '径向渐变过渡；设置页图标按钮同效'),
        ('Esc', '退出全屏 / 关闭浮层', ''),
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
    '出问题先看设置页「日志」：fell.log 里记录了启动、打开/改名/删除、播放失败与未捕获异常。',
]


def _shortcut_row(keys: str, action: str, note: str) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(4, 3, 4, 3)
    lay.setSpacing(16)
    key = StrongBodyLabel(keys)
    key.setMinimumWidth(200)
    act = BodyLabel(action)
    act.setMinimumWidth(190)
    hint = CaptionLabel(note)
    hint.setWordWrap(True)
    lay.addWidget(key, 0)
    lay.addWidget(act, 0)
    lay.addWidget(hint, 1)
    return row


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


class HelpPage(ScrollArea):
    """使用说明书：分组快捷键表 + 要点 + 已知限制。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('helpPage')
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

        layout = QVBoxLayout(self.scrollWidget)
        layout.setContentsMargins(36, 20, 36, 36)
        layout.setSpacing(18)

        intro = BodyLabel(
            'Fell 是本地图片 / 音频 / 视频查看器。下面按场景列出全部快捷键，'
            '界面上每个动作也都有对应按钮，悬停按钮能看到同样的提示。'
        )
        intro.setWordWrap(True)
        layout.addWidget(_card('快速上手', [intro]))

        for title, rows in SECTIONS:
            layout.addWidget(_card(title, [
                _shortcut_row(keys, action, note) for keys, action, note in rows
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.settingLabel.move(36, 30)
