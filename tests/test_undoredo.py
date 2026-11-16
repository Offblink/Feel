"""撤销栈单测（FR-30：顺序 / 清重做 / 上限 / 按身份丢条）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feel.undoredo import MAX_DEPTH, Op, UndoStack  # noqa: E402


def make_op(label='移入', n=1):
    return Op(label, [(Path(f'o{i}.png'), Path(f'n{i}.png'))
                      for i in range(n)])


class UndoStackTest(unittest.TestCase):
    def test_push_undo_redo_roundtrip(self):
        stack = UndoStack()
        self.assertFalse(stack.can_undo())
        self.assertFalse(stack.can_redo())
        first = make_op('移入', 2)
        second = make_op('重命名')
        stack.push(first)
        stack.push(second)
        self.assertTrue(stack.can_undo())
        self.assertFalse(stack.can_redo())
        self.assertIs(stack.undo(), second)
        self.assertTrue(stack.can_redo())
        self.assertIs(stack.undo(), first)
        self.assertIs(stack.redo(), first)
        self.assertIs(stack.redo(), second)
        self.assertIsNone(stack.redo())
        # 栈顺序是 LIFO：再撤回去，最新的一条先出
        self.assertIs(stack.undo(), second)
        self.assertIs(stack.undo(), first)
        self.assertIsNone(stack.undo())

    def test_new_push_clears_redo(self):
        stack = UndoStack()
        stack.push(make_op())
        stack.undo()
        self.assertTrue(stack.can_redo())
        stack.push(make_op('重命名'))
        self.assertFalse(stack.can_redo())

    def test_depth_cap_drops_oldest(self):
        stack = UndoStack()
        for index in range(MAX_DEPTH + 5):
            stack.push(Op(f'op{index}', [(Path('a'), Path('b'))]))
        count = 0
        labels = []
        while True:
            op = stack.undo()
            if op is None:
                break
            labels.append(op.label)
            count += 1
        self.assertEqual(count, MAX_DEPTH)
        # 最旧的 5 条（op0..op4）被挤掉；undo 按 LIFO 出，最新一条先出
        self.assertEqual(labels[0], f'op{MAX_DEPTH + 4}')
        self.assertEqual(labels[-1], 'op5')

    def test_empty_pairs_ignored(self):
        stack = UndoStack()
        stack.push(Op('空', []))
        self.assertFalse(stack.can_undo())

    def test_drop_is_identity_not_equality(self):
        stack = UndoStack()
        first = make_op()
        second = make_op()  # 与 first 值相等，但必须按身份区分
        stack.push(first)
        stack.push(second)
        self.assertIs(stack.undo(), second)
        stack.drop_from_redo(second)
        self.assertFalse(stack.can_redo())
        self.assertIs(stack.undo(), first)  # first 移到重做侧
        stack.drop_from_redo(first)
        self.assertFalse(stack.can_undo())
        self.assertFalse(stack.can_redo())
        # drop_from_undo 对称覆盖（重做失败时用）
        fresh = make_op('移入')
        stack.push(fresh)
        self.assertTrue(stack.can_undo())
        stack.drop_from_undo(fresh)
        self.assertFalse(stack.can_undo())

    def test_changed_signal_fires(self):
        stack = UndoStack()
        seen = []
        stack.changed.connect(lambda: seen.append(1))
        stack.push(make_op())
        stack.undo()
        stack.redo()
        self.assertEqual(len(seen), 3)


if __name__ == '__main__':
    unittest.main()
