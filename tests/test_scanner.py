"""目录扫描与自然排序单测（FR-01 / FR-18）。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feel.scanner import (  # noqa: E402
    natural_key,
    media_kind,
    scan_directory,
    scan_subdirs,
)


class ScannerTest(unittest.TestCase):
    def test_media_kind(self):
        self.assertEqual(media_kind('a.JPG'), 'image')
        self.assertEqual(media_kind('b.mp4'), 'video')
        self.assertEqual(media_kind('c.m4a'), 'audio')
        self.assertEqual(media_kind('d.avif'), 'image')
        self.assertIsNone(media_kind('d.txt'))
        self.assertIsNone(media_kind('Makefile'))

    def test_natural_key_avoids_mixed_compare(self):
        files = ['img10.png', 'img2.png', 'a.mp3', '10.mp3', 'a1b.jpg']
        ordered = sorted(files, key=natural_key)
        self.assertEqual(ordered, ['10.mp3', 'a1b.jpg', 'a.mp3', 'img2.png', 'img10.png'])

    def test_scan_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'img10.png').write_bytes(b'x')
            (root / 'img2.png').write_bytes(b'x')
            (root / 'song.mp3').write_bytes(b'x')
            (root / 'note.txt').write_text('ignore')
            (root / 'clip.mp4').write_bytes(b'x')
            (root / 'sub').mkdir()

            entries, index = scan_directory(root / 'img2.png')
            names = [entry.path.name for entry in entries]
            self.assertEqual(names, ['clip.mp4', 'img2.png', 'img10.png', 'song.mp3'])
            self.assertEqual(index, 1)
            self.assertEqual(entries[index].kind, 'image')

    def test_scan_unknown_file_starts_at_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'b.wav').write_bytes(b'x')
            (root / 'a.wav').write_bytes(b'x')
            entries, index = scan_directory(root / 'missing.mp3')
            self.assertEqual([e.path.name for e in entries], ['a.wav', 'b.wav'])
            self.assertEqual(index, 0)

    def test_sort_by_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, mtime in (('a.png', 300), ('b.png', 100), ('c.png', 200)):
                path = root / name
                path.write_bytes(b'x')
                os.utime(path, (mtime, mtime))

            entries, index = scan_directory(root / 'a.png', 'time_desc')
            self.assertEqual([e.path.name for e in entries], ['a.png', 'c.png', 'b.png'])
            self.assertEqual(index, 0)

            entries, index = scan_directory(root / 'a.png', 'time_asc')
            self.assertEqual([e.path.name for e in entries], ['b.png', 'c.png', 'a.png'])
            self.assertEqual(index, 2)

    def test_mtime_ties_fall_back_to_natural_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('img10.png', 'img2.png', 'img1.png'):
                path = root / name
                path.write_bytes(b'x')
                os.utime(path, (500, 500))
            entries, _ = scan_directory(root / 'img2.png', 'time_desc')
            self.assertEqual([e.path.name for e in entries],
                             ['img1.png', 'img2.png', 'img10.png'])

    def test_scan_subdirs_skips_files_and_hidden(self):
        if sys.platform != 'win32':
            self.skipTest('FILE_ATTRIBUTE_HIDDEN 是 Windows 口径')
        import ctypes

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sub10').mkdir()
            (root / 'sub2').mkdir()
            (root / 'file.png').write_bytes(b'x')
            hidden = root / 'hidden_sub'
            hidden.mkdir()
            ctypes.windll.kernel32.SetFileAttributesW(str(hidden), 0x2)
            self.addCleanup(ctypes.windll.kernel32.SetFileAttributesW,
                            str(hidden), 0x80)

            self.assertEqual([p.name for p in scan_subdirs(root)],
                             ['sub2', 'sub10'])
            # 与媒体同一套排序模式
            os.utime(root / 'sub2', (100, 100))
            os.utime(root / 'sub10', (200, 200))
            self.assertEqual([p.name for p in scan_subdirs(root, 'time_desc')],
                             ['sub10', 'sub2'])
            self.assertEqual([p.name for p in scan_subdirs(root, 'time_asc')],
                             ['sub2', 'sub10'])


if __name__ == '__main__':
    unittest.main()
