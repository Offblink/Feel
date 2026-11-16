"""撤销/重做栈（FR-30）：条目 = 路径对批次，移动与重命名同构。

只管记账与顺序；真正的搬运在 filemove.relocate，由窗口执行、失败时丢条，
保证栈与磁盘始终一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

MAX_DEPTH = 50


@dataclass
class Op:
    """一批 (原路径, 新路径) 路径对；label 用于提示（'移入' / '重命名'）。"""

    label: str
    pairs: list[tuple[Path, Path]] = field(default_factory=list)


class UndoStack(QObject):
    """会话级撤销栈：push 清空重做侧；undo/redo 交换条目归属；changed 驱动按钮态。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._undo: list[Op] = []
        self._redo: list[Op] = []

    def push(self, op: Op) -> None:
        if not op.pairs:
            return
        self._undo.append(op)
        if len(self._undo) > MAX_DEPTH:
            del self._undo[0]
        self._redo.clear()
        self.changed.emit()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Op | None:
        if not self._undo:
            return None
        op = self._undo.pop()
        self._redo.append(op)
        self.changed.emit()
        return op

    def redo(self) -> Op | None:
        if not self._redo:
            return None
        op = self._redo.pop()
        self._undo.append(op)
        self.changed.emit()
        return op

    def drop_from_redo(self, op: Op) -> None:
        """撤销执行失败：按身份从重做侧丢掉这条（栈与磁盘保持一致）。"""
        remaining = [item for item in self._redo if item is not op]
        if len(remaining) != len(self._redo):
            self._redo = remaining
            self.changed.emit()

    def drop_from_undo(self, op: Op) -> None:
        """重做执行失败：按身份从撤销侧丢掉这条。"""
        remaining = [item for item in self._undo if item is not op]
        if len(remaining) != len(self._undo):
            self._undo = remaining
            self.changed.emit()
