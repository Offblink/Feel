"""动作注册表：快捷键 ↔ 可视化控件的单一来源（SPEC §5.3 / FR-16）。

约定（结构保证，不靠人肉记）：
- 任何动作必须先 `register()` 再使用；register 时自动创建 QShortcut；
- 控件必须经 `bind_widget()` 挂到动作上，tooltip 自动写入快捷键；
- `problems()` 断言双向一一对应：有快捷键必有控件、控件必有动作；
- 上下文（GLOBAL / PLAYER / SHELF / SETTINGS）不合时，快捷键与动作一起禁用，
  不会出现「有键无钮」。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

GLOBAL = 'global'
PLAYER = 'player'
SHELF = 'shelf'
SETTINGS = 'settings'

# 帮助页 / tooltip 里的键名显示形态（Left → ←），按 + 分段精确映射，
# 避免 PageUp 之类的键名被子串误伤
KEY_GLYPHS = {'Left': '←', 'Right': '→', 'Up': '↑', 'Down': '↓'}


def display_sequence(sequence: str) -> str:
    """把 QKeySequence 的键名翻译成显示形态（Left → ← / Ctrl+Left → Ctrl+←）。"""
    return '+'.join(KEY_GLYPHS.get(part, part) for part in sequence.split('+'))


@dataclass
class Action:
    """一个用户动作：名称、快捷键、上下文、执行器。

    ``shortcut`` 是主快捷键（显示在控件 tooltip 里），``extra_shortcuts`` 是
    同一动作的别名键（例如上一个文件既有 ← 也有 Ctrl+←）。
    ``active_when`` 按「键位」进一步门控 QShortcut 是否生效（按上下文/媒体状态
    互斥的一对键位靠它共存，如视频 ←/→ 快进 vs 非视频 ←/→ 切文件）；
    与 ``enabled_when``（只拦 trigger、不拦 QShortcut）是两回事。
    """

    id: str
    name: str
    shortcut: Optional[str] = None
    icon: object = None
    context: str = GLOBAL
    enabled_when: Optional[Callable[[], bool]] = None
    handler: Optional[Callable[[], None]] = None
    # 快捷键按下时的专用执行器（默认为 handler）。方向键后退/前进用它：
    # 按键要区分短按/长按，而程序调用 trigger() 仍走 handler 立即执行
    key_handler: Optional[Callable[[], None]] = None
    extra_shortcuts: tuple[str, ...] = ()
    active_when: Optional[Callable[[str], bool]] = None
    # 按住键时是否重复触发。方向键后退/前进靠它关掉自动重复：
    # 长按归「临时倍速」，不能每一拍都再触发一次 seek
    auto_repeat: bool = True

    def shortcuts(self) -> tuple[str, ...]:
        # 主键可能与别名撞成同一个键（改绑时），去重保证一个键只建一个 QShortcut
        keys: list[str] = []
        for seq in ((self.shortcut,) if self.shortcut else ()) + self.extra_shortcuts:
            if seq not in keys:
                keys.append(seq)
        return tuple(keys)

    def tooltip(self) -> str:
        if not self.shortcut:
            return self.name
        return f'{self.name}（{display_sequence(self.shortcut)}）'


class ActionRegistry(QObject):
    """窗口级动作注册表。"""

    # 该动作的快捷键被改绑（帮助页键帽改键后各处 tooltip / 键帽自行刷新）
    shortcutsChanged = Signal(str)

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._actions: dict[str, Action] = {}
        self._widgets: dict[str, list[QWidget]] = {}
        self._explicit: dict[str, list[bool]] = {}
        self._shortcuts: dict[str, list[QShortcut]] = {}
        self._key_of: dict[QShortcut, str] = {}
        self._context = GLOBAL

    # ---- 注册 ----
    def _make_shortcut(self, action: Action, sequence: str) -> QShortcut:
        shortcut = QShortcut(QKeySequence(sequence), self._window)
        shortcut.setContext(Qt.ApplicationShortcut)
        shortcut.setAutoRepeat(action.auto_repeat)
        shortcut.activated.connect(
            lambda aid=action.id: self.trigger(aid, from_key=True)
        )
        shortcut.setEnabled(self._shortcut_enabled(action, sequence))
        self._key_of[shortcut] = sequence
        return shortcut

    def _shortcut_enabled(self, action: Action, sequence: str) -> bool:
        if not self._allows(action):
            return False
        return action.active_when is None or action.active_when(sequence)

    def register(self, action: Action) -> Action:
        if action.id in self._actions:
            raise KeyError(f'action already registered: {action.id}')
        self._actions[action.id] = action
        for sequence in dict.fromkeys(action.shortcuts()):
            self._shortcuts.setdefault(action.id, []).append(
                self._make_shortcut(action, sequence)
            )
        return action

    def bind_widget(
        self, action_id: str, widget: QWidget, tooltip: Optional[str] = None
    ) -> QWidget:
        action = self._actions[action_id]
        self._widgets.setdefault(action_id, []).append(widget)
        self._explicit.setdefault(action_id, []).append(tooltip is not None)
        widget.setToolTip(tooltip or action.tooltip())
        return widget

    # ---- 改绑 ----
    def set_shortcut(self, action_id: str, sequence: str) -> None:
        """把动作的主快捷键改绑为 sequence（同义别名保留，去重后重建 QShortcut）。

        只自动刷新 bind_widget 没给自定义文案的控件 tooltip，其余文案
        （帮助页键帽、带说明的自定义 tooltip）由 shortcutsChanged 的监听方重写。
        """
        action = self._actions[action_id]
        if sequence == action.shortcut:
            return
        for shortcut in self._shortcuts.pop(action_id, []):
            self._key_of.pop(shortcut, None)
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        action.shortcut = sequence
        for seq in dict.fromkeys(action.shortcuts()):
            self._shortcuts.setdefault(action_id, []).append(
                self._make_shortcut(action, seq)
            )
        for widget, explicit in zip(
            self._widgets.get(action_id, ()), self._explicit.get(action_id, ())
        ):
            if not explicit:
                widget.setToolTip(action.tooltip())
        self.shortcutsChanged.emit(action_id)

    def conflicts(self, action_id: str, sequence: str) -> list[str]:
        """sequence 已被别的动作占用时返回对方 id 列表（空 = 可用）。

        两个动作都带 active_when 时不判冲突：它们的键位按状态互斥启用
        （视频 ←/→ 快进 vs 非视频 ←/→ 切文件，正是这样共存的）。
        """
        own = self._actions[action_id]
        hits = []
        for other_id, other in self._actions.items():
            if other_id == action_id or sequence not in other.shortcuts():
                continue
            if own.active_when is not None and other.active_when is not None:
                continue
            hits.append(other_id)
        return hits

    # ---- 执行 ----
    def trigger(self, action_id: str, from_key: bool = False) -> bool:
        action = self._actions[action_id]
        if not self._allows(action):
            return False
        if action.enabled_when is not None and not action.enabled_when():
            return False
        handler = action.key_handler if from_key and action.key_handler else action.handler
        if handler is None:
            return False
        handler()
        return True

    def action(self, action_id: str) -> Action:
        return self._actions[action_id]

    @property
    def actions(self) -> dict[str, Action]:
        return dict(self._actions)

    # ---- 上下文 ----
    def set_context(self, context: str) -> None:
        self._context = context
        self.refresh_enabled()

    def refresh_enabled(self) -> None:
        """按上下文与 active_when 重算所有 QShortcut 的 enabled（媒体状态变了要调）。"""
        for aid, shortcuts in self._shortcuts.items():
            action = self._actions[aid]
            for shortcut in shortcuts:
                shortcut.setEnabled(self._shortcut_enabled(action, self._key_of[shortcut]))

    def _allows(self, action: Action) -> bool:
        return action.context == GLOBAL or action.context == self._context

    # ---- 不变量 ----
    def problems(self) -> list[str]:
        """返回违反一一对应的条目；空列表 = 全部动作均有快捷键与控件。"""
        issues: list[str] = []
        for aid, action in self._actions.items():
            if action.shortcut and aid not in self._shortcuts:
                issues.append(f'{aid}: shortcut missing')
            if not self._widgets.get(aid):
                issues.append(f'{aid}: no bound widget')
        for aid in self._widgets:
            if aid not in self._actions:
                issues.append(f'{aid}: orphan widget binding')
        return issues
