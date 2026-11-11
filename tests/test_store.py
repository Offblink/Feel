"""sqlite 存储单测：旋转（跨会话）/收藏/书签。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fell.store import Store  # noqa: E402


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / 'fell.db'
        self.store = Store(self.db_path)
        self.file = Path('C:/media/clip.mp4')

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_rotation_defaults_to_zero(self):
        self.assertEqual(self.store.get_rotation(self.file), 0)

    def test_rotation_roundtrip_and_normalization(self):
        self.store.set_rotation(self.file, 90)
        self.assertEqual(self.store.get_rotation(self.file), 90)
        self.store.set_rotation(self.file, -90)
        self.assertEqual(self.store.get_rotation(self.file), 270)
        self.store.set_rotation(self.file, 360)
        self.assertEqual(self.store.get_rotation(self.file), 0)

    def test_rotation_persists_across_connections(self):
        self.store.set_rotation(self.file, 180)
        self.store.close()
        reopened = Store(self.db_path)
        try:
            self.assertEqual(reopened.get_rotation(self.file), 180)
        finally:
            reopened.close()
        self.store = Store(self.db_path)  # tearDown 用

    def test_favorite_roundtrip(self):
        self.assertFalse(self.store.is_favorite(self.file))
        self.assertTrue(self.store.toggle_favorite(self.file))
        self.assertIn(self.file, self.store.favorite_paths())
        self.assertFalse(self.store.toggle_favorite(self.file))
        self.assertNotIn(self.file, self.store.favorite_paths())

    def test_bookmark_add_and_delete(self):
        bookmark_id = self.store.add_bookmark(self.file, 1500)
        self.assertEqual(len(self.store.bookmarks(self.file)), 1)
        duplicate = self.store.add_bookmark(self.file, 1500)
        self.assertEqual(duplicate, bookmark_id)
        self.assertEqual(len(self.store.bookmarks(self.file)), 1)
        self.store.delete_bookmark(bookmark_id)
        self.assertEqual(self.store.bookmarks(self.file), [])

    def test_bookmark_label_is_upserted_at_same_position(self):
        self.store.add_bookmark(self.file, 1500, '副歌')
        rows = self.store.bookmarks(self.file)
        self.assertEqual(rows[0][2], '副歌')
        self.store.add_bookmark(self.file, 1500, '结尾')
        rows = self.store.bookmarks(self.file)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0][1], 1500)
        self.assertEqual(rows[0][2], '结尾')


if __name__ == '__main__':
    unittest.main()
