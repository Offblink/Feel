"""sqlite 持久化：OCR 缓存（FR-23），收藏/书签在 Phase 7 扩展。"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .config import DB_PATH


class Store:
    def __init__(self, db_path: Path | str = DB_PATH):
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute(
            '''
            CREATE TABLE IF NOT EXISTS ocr_cache(
                path TEXT PRIMARY KEY,
                mtime INTEGER NOT NULL,
                size INTEGER NOT NULL,
                text TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            '''
        )
        self._db.execute(
            '''
            CREATE TABLE IF NOT EXISTS favorites(
                path TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL
            )
            '''
        )
        self._db.execute(
            '''
            CREATE TABLE IF NOT EXISTS bookmarks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                pos_ms INTEGER NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                UNIQUE(path, pos_ms)
            )
            '''
        )
        self._db.execute(
            '''
            CREATE TABLE IF NOT EXISTS rotation(
                path TEXT PRIMARY KEY,
                degrees INTEGER NOT NULL
            )
            '''
        )
        self._db.commit()

    # ---- OCR 缓存 ----
    def get_ocr(self, path: Path, mtime: int, size: int) -> str | None:
        row = self._db.execute(
            'SELECT text FROM ocr_cache WHERE path=? AND mtime=? AND size=?',
            (str(path), mtime, size),
        ).fetchone()
        return row[0] if row else None

    def put_ocr(self, path: Path, mtime: int, size: int, text: str) -> None:
        self._db.execute(
            '''
            INSERT INTO ocr_cache(path, mtime, size, text, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                mtime=excluded.mtime, size=excluded.size,
                text=excluded.text, updated_at=excluded.updated_at
            ''',
            (str(path), int(mtime), int(size), text, int(time.time())),
        )
        self._db.commit()

    def delete_ocr(self, path: Path) -> None:
        self._db.execute('DELETE FROM ocr_cache WHERE path=?', (str(path),))
        self._db.commit()

    # ---- 收藏 ----
    def is_favorite(self, path: Path) -> bool:
        row = self._db.execute(
            'SELECT 1 FROM favorites WHERE path=?', (str(path),)
        ).fetchone()
        return row is not None

    def set_favorite(self, path: Path, favorite: bool) -> None:
        if favorite:
            self._db.execute(
                'INSERT OR IGNORE INTO favorites(path, created_at) VALUES(?, ?)',
                (str(path), int(time.time())),
            )
        else:
            self._db.execute('DELETE FROM favorites WHERE path=?', (str(path),))
        self._db.commit()

    def toggle_favorite(self, path: Path) -> bool:
        state = not self.is_favorite(path)
        self.set_favorite(path, state)
        return state

    def favorite_paths(self) -> set[Path]:
        rows = self._db.execute('SELECT path FROM favorites').fetchall()
        return {Path(row[0]) for row in rows}

    # ---- 书签 ----
    def add_bookmark(self, path: Path, pos_ms: int, label: str = '') -> int:
        """同一位置再次保存时更新内容（时间+内容键值对，UNIQUE(path, pos_ms)）。"""
        pos_ms = max(0, int(pos_ms))
        self._db.execute(
            'INSERT INTO bookmarks(path, pos_ms, label, created_at) VALUES(?, ?, ?, ?) '
            'ON CONFLICT(path, pos_ms) DO UPDATE SET label=excluded.label, '
            'created_at=excluded.created_at',
            (str(path), pos_ms, label, int(time.time())),
        )
        self._db.commit()
        row = self._db.execute(
            'SELECT id FROM bookmarks WHERE path=? AND pos_ms=?',
            (str(path), pos_ms),
        ).fetchone()
        return int(row[0]) if row else 0

    def bookmarks(self, path: Path) -> list[tuple[int, int, str]]:
        rows = self._db.execute(
            'SELECT id, pos_ms, label FROM bookmarks WHERE path=? ORDER BY pos_ms',
            (str(path),),
        ).fetchall()
        return [(int(r[0]), int(r[1]), r[2]) for r in rows]

    def delete_bookmark(self, bookmark_id: int) -> None:
        self._db.execute('DELETE FROM bookmarks WHERE id=?', (int(bookmark_id),))
        self._db.commit()

    # ---- 旋转（跨会话持久化）----
    def get_rotation(self, path: Path) -> int:
        row = self._db.execute(
            'SELECT degrees FROM rotation WHERE path=?', (str(path),)
        ).fetchone()
        return int(row[0]) % 360 if row else 0

    def set_rotation(self, path: Path, degrees: int) -> None:
        degrees = int(degrees) % 360
        if degrees == 0:
            self._db.execute('DELETE FROM rotation WHERE path=?', (str(path),))
        else:
            self._db.execute(
                'INSERT INTO rotation(path, degrees) VALUES(?, ?) '
                'ON CONFLICT(path) DO UPDATE SET degrees=excluded.degrees',
                (str(path), degrees),
            )
        self._db.commit()

    def rename_path(self, old: Path, new: Path) -> None:
        """文件改名后迁移随路径保存的数据（收藏 / 书签 / 旋转 / OCR 缓存）。

        不做迁移的话，改名等于把用户的收藏和书签静默清空。
        """
        old_s, new_s = str(old), str(new)
        if old_s == new_s:
            return
        with self._db:
            for table in ('favorites', 'rotation', 'ocr_cache'):
                self._db.execute(f'DELETE FROM {table} WHERE path=?', (new_s,))
                self._db.execute(
                    f'UPDATE OR REPLACE {table} SET path=? WHERE path=?', (new_s, old_s)
                )
            self._db.execute(
                'UPDATE OR REPLACE bookmarks SET path=? WHERE path=?', (new_s, old_s)
            )

    def close(self) -> None:
        self._db.close()
