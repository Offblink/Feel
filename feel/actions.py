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

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

GLOBAL = 'global'
PLAYER = 'player'
SHELF = 'shelf'
SETTINGS = 'settings'


@dataclass
class Action:
    """一个用户动作：名称、快捷键、上下文、执行器。

    ``shortcut`` 是主快捷键（显示在控件 tooltip 里），``extra_shortcuts`` 是
    同一动作的别名键（例如上一个文件既有 ← 也有 Ctrl+←）。
    """

    id: str
    name: str
    shortcut: Optional[str] = None
    icon: object = None
    context: str = GLOBAL
    enabled_when: Optional[Callable[[], bool]] = None
    handler: Optional[Callable[[], None]] = None
    extra_shortcuts: tuple[str, ...] = ()

    def shortcuts(self) -> tuple[str, ...]:
        keys = (self.shortcut,) if self.shortcut else ()
        return keys + tuple(self.extra_shortcuts)

    def tooltip(self) -> str:
        return f'{self.name}（{self.shortcut}）' if self.shortcut else self.name


class ActionRegistry(QObject):
    """窗口级动作注册表。"""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._actions: dict[str, Action] = {}
        self._widgets: dict[str, list[QWidget]] = {}
        self._shortcuts: dict[str, list[QShortcut]] = {}
        self._context = GLOBAL

    # ---- 注册 ----
    def register(self, action: Action) -> Action:
        if action.id in self._actions:
            raise KeyError(f'action already registered: {action.id}')
        self._actions[action.id] = action
        for sequence in action.shortcuts():
            shortcut = QShortcut(QKeySequence(sequence), self._window)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(lambda aid=action.id: self.trigger(aid))
            self._shortcuts.setdefault(action.id, []).append(shortcut)
            shortcut.setEnabled(self._allows(action))
        return action

    def bind_widget(
        self, action_id: str, widget: QWidget, tooltip: Optional[str] = None
    ) -> QWidget:
        action = self._actions[action_id]
        self._widgets.setdefault(action_id, []).append(widget)
        widget.setToolTip(tooltip or action.tooltip())
        return widget

    # ---- 执行 ----
    def trigger(self, action_id: str) -> bool:
        action = self._actions[action_id]
        if not self._allows(action):
            return False
        if action.enabled_when is not None and not action.enabled_when():
            return False
        if action.handler is None:
            return False
        action.handler()
        return True

    def action(self, action_id: str) -> Action:
        return self._actions[action_id]

    @property
    def actions(self) -> dict[str, Action]:
        return dict(self._actions)

    # ---- 上下文 ----
    def set_context(self, context: str) -> None:
        self._context = context
        for aid, shortcuts in self._shortcuts.items():
            enabled = self._allows(self._actions[aid])
            for shortcut in shortcuts:
                shortcut.setEnabled(enabled)

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
