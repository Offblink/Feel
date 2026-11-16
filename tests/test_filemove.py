"""移动文件单测（FR-30/31/32 的 filemove 层：同名改名 / 同目录跳过 / 搬运语义）。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feel.filemove import move_files, unique_target  # noqa: E402


class FilemoveTest(unittest.TestCase):
    def test_unique_target_counts_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(unique_target(root, 'a.png'), root / 'a.png')
            (root / 'a.png').write_bytes(b'x')
            self.assertEqual(unique_target(root, 'a.png'), root / 'a (2).png')
            (root / 'a (2).png').write_bytes(b'x')
            self.assertEqual(unique_target(root, 'a.png'), root / 'a (3).png')
            # 多后缀只动最后一段（资源管理器口径）
            (root / 'b.tar.gz').write_bytes(b'x')
            self.assertEqual(unique_target(root, 'b.tar.gz'),
                             root / 'b.tar (2).gz')

    def test_move_files_moves_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / 'src'
            dst_dir = root / 'dst'
            src_dir.mkdir()
            dst_dir.mkdir()
            a = src_dir / 'a.png'
            b = src_dir / 'b.png'
            a.write_bytes(b'x')
            b.write_bytes(b'x')
            (dst_dir / 'a.png').write_bytes(b'occupied')
            missing = src_dir / 'gone.png'

            moved, failed = move_files([a, b, missing], dst_dir)
            self.assertEqual({s.name: d.name for s, d in moved},
                             {'a.png': 'a (2).png', 'b.png': 'b.png'})
            self.assertFalse(a.exists())
            self.assertFalse(b.exists())
            self.assertEqual((dst_dir / 'a (2).png').read_bytes(), b'x')
            # 同名占位文件绝不被覆盖
            self.assertEqual((dst_dir / 'a.png').read_bytes(), b'occupied')
            self.assertEqual([p.name for p, _ in failed], ['gone.png'])

    def test_move_files_skips_same_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'here'
            target.mkdir()
            existing = target / 'x.png'
            existing.write_bytes(b'x')
            moved, failed = move_files([existing], target)
            self.assertEqual(moved, [])
            self.assertEqual(failed[0][1], '已在该文件夹')
            self.assertTrue(existing.exists())

    def test_move_folders_and_reject_self_nesting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'src'
            (src / 'inner').mkdir(parents=True)
            dst = root / 'dst'
            dst.mkdir()
            moved, failed = move_files([src], dst)
            self.assertEqual(len(moved), 1, failed)
            self.assertTrue((dst / 'src' / 'inner').exists())
            self.assertFalse(src.exists())
            # 目标是自己 / 自己的子孙 → 拒绝（目录树不能搬进自己）
            moved2, failed2 = move_files([dst / 'src'], dst / 'src' / 'inner')
            self.assertEqual(moved2, [])
            self.assertEqual(failed2[0][1], '不能移进自身')
            moved3, failed3 = move_files([dst / 'src'], dst / 'src')
            self.assertEqual(moved3, [])
            self.assertEqual(failed3[0][1], '不能移进自身')


if __name__ == '__main__':
    unittest.main()
