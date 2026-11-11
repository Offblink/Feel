"""播放模式状态机单测（SPEC §5.4）。"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feel.queue import auto_index, step_index  # noqa: E402


class StepIndexTest(unittest.TestCase):
    def test_sequential_modes_wrap_both_ways(self):
        for mode in ('once', 'list', 'one', 'shuffle'):
            if mode == 'shuffle':
                continue
            self.assertEqual(step_index(3, 2, mode, +1), 0)
            self.assertEqual(step_index(3, 0, mode, -1), 2)

    def test_shuffle_never_returns_current(self):
        rng = random.Random(7)
        for _ in range(50):
            nxt = step_index(4, 2, 'shuffle', +1, rng=rng)
            self.assertIn(nxt, (0, 1, 3))
            prev = step_index(4, 2, 'shuffle', -1, rng=rng)
            self.assertIn(prev, (0, 1, 3))

    def test_single_entry_is_idempotent(self):
        for mode in ('once', 'list', 'one'):
            self.assertEqual(step_index(1, 0, mode), 0)


class AutoIndexTest(unittest.TestCase):
    def test_once_stops(self):
        self.assertIsNone(auto_index(3, 1, 'once'))

    def test_list_wraps(self):
        self.assertEqual(auto_index(3, 2, 'list'), 0)
        self.assertEqual(auto_index(3, 1, 'list'), 2)

    def test_one_replays(self):
        self.assertEqual(auto_index(3, 1, 'one'), 1)

    def test_shuffle_moves_elsewhere(self):
        rng = random.Random(3)
        for _ in range(50):
            self.assertNotEqual(auto_index(3, 1, 'shuffle', rng=rng), 1)

    def test_single_entry(self):
        self.assertIsNone(auto_index(1, 0, 'once'))
        self.assertEqual(auto_index(1, 0, 'one'), 0)
        self.assertEqual(auto_index(1, 0, 'list'), 0)


if __name__ == '__main__':
    unittest.main()
