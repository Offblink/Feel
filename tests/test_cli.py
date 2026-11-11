"""启动参数解析单测（文件关联 / 用 Feel 打开）。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feel.cli import find_open_target  # noqa: E402


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.media = self.root / 'photo.png'
        self.media.write_bytes(b'x')
        self._old_launch_dir = os.environ.get('FEEL_LAUNCH_DIR')

    def tearDown(self):
        if self._old_launch_dir is None:
            os.environ.pop('FEEL_LAUNCH_DIR', None)
        else:
            os.environ['FEEL_LAUNCH_DIR'] = self._old_launch_dir
        self._tmp.cleanup()

    def test_first_existing_path_wins(self):
        missing = self.root / 'nope.mp4'
        self.assertEqual(find_open_target([str(missing), str(self.media)]), self.media)

    def test_directory_is_accepted(self):
        self.assertEqual(find_open_target([str(self.root)]), self.root)

    def test_qt_style_flags_are_ignored(self):
        self.assertEqual(find_open_target(['-platform', 'offscreen', str(self.media)]),
                         self.media)

    def test_quoted_path_is_unwrapped(self):
        self.assertEqual(find_open_target([f'"{self.media}"']), self.media)

    def test_relative_path_uses_launch_dir(self):
        os.environ['FEEL_LAUNCH_DIR'] = str(self.root)
        self.assertEqual(find_open_target(['photo.png']), self.media)

    def test_no_target_returns_none(self):
        self.assertIsNone(find_open_target([]))
        self.assertIsNone(find_open_target([str(self.root / 'missing.png')]))


if __name__ == '__main__':
    unittest.main()
