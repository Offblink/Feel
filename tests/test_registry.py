"""ActionRegistry 不变量单测（SPEC §5.3 / FR-16）。"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from feel.actions import Action, ActionRegistry, PLAYER, SHELF  # noqa: E402


class RegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QWidget()

    def tearDown(self):
        self.window.deleteLater()

    def test_complete_bijection_has_no_problems(self):
        registry = ActionRegistry(self.window)
        registry.register(Action('go', '去某个页面', 'Ctrl+X', handler=lambda: None))
        registry.bind_widget('go', QWidget(self.window))
        self.assertEqual(registry.problems(), [])

    def test_missing_widget_is_detected(self):
        registry = ActionRegistry(self.window)
        registry.register(Action('go', '去某个页面', 'Ctrl+X', handler=lambda: None))
        problems = registry.problems()
        self.assertTrue(any('no bound widget' in p for p in problems), problems)

    def test_orphan_widget_is_detected(self):
        registry = ActionRegistry(self.window)
        registry.register(Action('go', '去某个页面', 'Ctrl+X', handler=lambda: None))
        registry.bind_widget('go', QWidget(self.window))
        registry._widgets['phantom'] = [QWidget(self.window)]
        problems = registry.problems()
        self.assertTrue(any('orphan widget' in p for p in problems), problems)

    def test_context_gates_shortcut_and_trigger(self):
        ran = []
        registry = ActionRegistry(self.window)
        registry.register(
            Action('play', '播放', 'P', context=PLAYER, handler=lambda: ran.append(1))
        )
        registry.bind_widget('play', QWidget(self.window))

        registry.set_context(SHELF)
        self.assertFalse(registry.trigger('play'))
        self.assertTrue(registry._shortcuts['play'])
        self.assertFalse(any(s.isEnabled() for s in registry._shortcuts['play']))

        registry.set_context(PLAYER)
        self.assertTrue(registry.trigger('play'))
        self.assertTrue(all(s.isEnabled() for s in registry._shortcuts['play']))
        self.assertEqual(ran, [1])

    def test_extra_shortcuts_are_registered(self):
        registry = ActionRegistry(self.window)
        registry.register(
            Action('next', '下一个', 'Right', handler=lambda: None,
                   extra_shortcuts=('Ctrl+Right',))
        )
        registry.bind_widget('next', QWidget(self.window))
        keys = [shortcut.key().toString() for shortcut in registry._shortcuts['next']]
        self.assertEqual(keys, ['Right', 'Ctrl+Right'])
        self.assertEqual(registry.problems(), [])

    def test_enabled_when_blocks_trigger(self):
        registry = ActionRegistry(self.window)
        registry.register(
            Action('sign', '签名', 'S', enabled_when=lambda: False, handler=lambda: None)
        )
        registry.bind_widget('sign', QWidget(self.window))
        self.assertFalse(registry.trigger('sign'))


if __name__ == '__main__':
    unittest.main()
