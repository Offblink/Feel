"""目录扫描与文件分类（FR-01）。

可读文件 = 扩展名白名单内的 图片/视频/音频，按自然序（a2 < a10）排序，
构成播放/浏览队列。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff', '.ico'}
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.ts'}
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.aac', '.m4a', '.wma', '.ogg', '.opus', '.aiff'}

READABLE_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

MEDIA_FILTER = (
    '媒体文件 (' + ' '.join(f'*{e}' for e in sorted(READABLE_EXTS)) + ');;所有文件 (*.*)'
)

IMAGE, VIDEO, AUDIO = 'image', 'video', 'audio'


def media_kind(path: str | Path) -> str | None:
    """返回 'image' / 'video' / 'audio'，不可读返回 None。"""
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return IMAGE
    if ext in VIDEO_EXTS:
        return VIDEO
    if ext in AUDIO_EXTS:
        return AUDIO
    return None


def natural_key(name: str) -> list[tuple[int, object]]:
    """自然排序键：img2.png < img10.png；数字段与文本段用类型标签避免混合比较。"""
    key: list[tuple[int, object]] = []
    for part in re.split(r'(\d+)', name):
        if not part:
            continue
        key.append((0, int(part)) if part.isdigit() else (1, part.lower()))
    return key


SORT_NAME = 'name'
SORT_TIME_DESC = 'time_desc'
SORT_TIME_ASC = 'time_asc'
SORT_MODES = (SORT_NAME, SORT_TIME_DESC, SORT_TIME_ASC)


@dataclass(frozen=True)
class MediaEntry:
    path: Path
    kind: str
    mtime: float = 0.0


def sort_entries(entries: list[MediaEntry], sort_mode: str = SORT_NAME) -> list[MediaEntry]:
    """按名称（自然序）或文件修改时间排序。

    时间排序不是严格全序（同秒文件很多）：以名称自然序作稳定次序，
    因此「mtime 倒序 + 名称」在千级目录里也不会因为 scandir 顺序抖动而乱跳。
    """
    if sort_mode in (SORT_TIME_DESC, SORT_TIME_ASC):
        sign = -1.0 if sort_mode == SORT_TIME_DESC else 1.0
        return sorted(entries,
                      key=lambda entry: (sign * entry.mtime,
                                         natural_key(entry.path.name)))
    return sorted(entries, key=lambda entry: natural_key(entry.path.name))


def scan_folder(folder: str | Path,
                sort_mode: str = SORT_NAME) -> list[MediaEntry]:
    """扫描目录内可读媒体（不含当前文件定位），用于命令行传目录时打开首项。"""
    entries: list[MediaEntry] = []
    try:
        with os.scandir(Path(folder)) as iterator:
            for item in iterator:
                try:
                    if not item.is_file():
                        continue
                except OSError:
                    continue
                kind = media_kind(item.name)
                if kind is not None:
                    try:
                        mtime = item.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    entries.append(MediaEntry(Path(item.path), kind, mtime))
    except OSError:
        pass
    return sort_entries(entries, sort_mode)


def scan_directory(file_path: str | Path,
                   sort_mode: str = SORT_NAME) -> tuple[list[MediaEntry], int]:
    """扫描 file_path 所在目录的可读文件，返回 (排序后列表, 当前文件下标)。

    ``sort_mode``：``name`` 自然序 / ``time_desc`` 新→旧 / ``time_asc`` 旧→新。

    性能（大目录 1000+ 文件）：用 ``os.scandir`` 一次取目录项（其 DirEntry 已缓存
    类型/属性，避免逐个 ``Path.is_file()`` 走 stat），当前文件用文件名比对定位，
    不再对每个条目做 ``Path.resolve()``（Windows 上是逐项系统调用，千项可达数百毫秒）。
    mtime 也取自同一个 DirEntry.stat()（Windows 目录项自带时间，不额外 syscall）。
    """
    file_path = Path(file_path)
    entries = scan_folder(file_path.parent, sort_mode)

    target = os.path.normcase(file_path.name)
    index = 0
    for i, entry in enumerate(entries):
        if os.path.normcase(entry.path.name) == target:
            index = i
            break
    return entries, index
