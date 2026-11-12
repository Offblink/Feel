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

    def test_active_when_gates_shortcut_by_state(self):
        """同一键位互斥归属：视频 ←/→ 归快进，非视频归切换（refresh 重算）。"""
        kind = ['video']
        registry = ActionRegistry(self.window)
        registry.register(
            Action('seek', '前进', 'Right', handler=lambda: None,
                   active_when=lambda seq: kind[0] == 'video')
        )
        registry.register(
            Action('next', '下一个', 'Right', handler=lambda: None,
                   active_when=lambda seq: kind[0] != 'video')
        )
        registry.bind_widget('seek', QWidget(self.window))
        registry.bind_widget('next', QWidget(self.window))
        seek_sc = registry._shortcuts['seek'][0]
        next_sc = registry._shortcuts['next'][0]
        self.assertTrue(seek_sc.isEnabled())
        self.assertFalse(next_sc.isEnabled())

        kind[0] = 'image'
        registry.refresh_enabled()
        self.assertFalse(seek_sc.isEnabled())
        self.assertTrue(next_sc.isEnabled())

    def test_set_shortcut_rebinds_and_updates_auto_tooltip(self):
        registry = ActionRegistry(self.window)
        action = registry.register(Action('go', '去某个页面', 'Ctrl+X', handler=lambda: None))
        widget = QWidget(self.window)
        registry.bind_widget('go', widget)
        fired = []
        registry.shortcutsChanged.connect(fired.append)

        registry.set_shortcut('go', 'Ctrl+Y')

        self.assertEqual(action.shortcut, 'Ctrl+Y')
        keys = [sc.key().toString() for sc in registry._shortcuts['go']]
        self.assertEqual(keys, ['Ctrl+Y'])
        self.assertEqual(widget.toolTip(), '去某个页面（Ctrl+Y）')
        self.assertEqual(fired, ['go'])
        self.assertEqual(registry.problems(), [])

    def test_set_shortcut_keeps_alias_without_duplicate_qshortcut(self):
        registry = ActionRegistry(self.window)
        action = registry.register(
            Action('nav', '导航', 'Left', handler=lambda: None,
                   extra_shortcuts=('Ctrl+Left',))
        )
        registry.bind_widget('nav', QWidget(self.window))
        # 改绑成自己的别名：QShortcut 不能重复建两个（同键歧义 = 都不触发）
        registry.set_shortcut('nav', 'Ctrl+Left')
        keys = [sc.key().toString() for sc in registry._shortcuts['nav']]
        self.assertEqual(keys, ['Ctrl+Left'])
        self.assertEqual(action.shortcuts(), ('Ctrl+Left',))

    def test_conflicts_reports_occupied_keys(self):
        registry = ActionRegistry(self.window)
        registry.register(Action('open', '打开', 'Ctrl+O', handler=lambda: None))
        registry.register(Action('save', '保存', 'Ctrl+S', handler=lambda: None))
        registry.bind_widget('open', QWidget(self.window))
        registry.bind_widget('save', QWidget(self.window))
        self.assertEqual(registry.conflicts('save', 'Ctrl+O'), ['open'])
        self.assertEqual(registry.conflicts('save', 'Ctrl+P'), [])

    def test_conflicts_allows_mutually_gated_pair(self):
        """都带 active_when 的两个动作同键不判冲突（键位按状态互斥启用）。"""
        registry = ActionRegistry(self.window)
        registry.register(Action('seek', '快进', 'Right', handler=lambda: None,
                                 active_when=lambda seq: True))
        registry.register(Action('next', '下一个', 'Left', handler=lambda: None,
                                 active_when=lambda seq: False))
        registry.bind_widget('seek', QWidget(self.window))
        registry.bind_widget('next', QWidget(self.window))
        # next 的主键 Left 不在 seek 的键位里；把 next 改绑成 Right 也不算冲突
        self.assertEqual(registry.conflicts('next', 'Right'), [])
        # 没有 active_when 的动作照常判
        registry.register(Action('plain', '普通', 'Del', handler=lambda: None))
        registry.bind_widget('plain', QWidget(self.window))
        self.assertEqual(registry.conflicts('seek', 'Del'), ['plain'])


if __name__ == '__main__':
    unittest.main()
