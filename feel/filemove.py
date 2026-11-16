"""移动文件到目标文件夹（移入 / 拖拽移入 / 撤销重做共用，FR-30/31/32）。

纯函数：不碰 Qt、播放页与队列。调用方负责 Store 路径迁移、队列刷新、撤销入栈。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def unique_target(target_dir: Path, name: str) -> Path:
    """同名自动改名：photo.png → photo (2).png（只动最后一段后缀，资源管理器口径）。"""
    candidate = target_dir / name
    if not candidate.exists():
        return candidate
    stem, suffix = os.path.splitext(name)
    index = 2
    while True:
        candidate = target_dir / f'{stem} ({index}){suffix}'
        if not candidate.exists():
            return candidate
        index += 1


def move_files(paths, target_dir: str | Path
               ) -> tuple[list[tuple[Path, Path]], list[tuple[Path, str]]]:
    """把文件移动进 target_dir，返回 (已移动 [(src, dst)], 失败 [(src, 原因)])。

    - 目标已有同名文件 → 自动改名，绝不覆盖；
    - 源已在目标目录 → 计入失败（原因「已在该文件夹」）；
    - 跨盘交给 shutil.move（同盘 rename、跨盘复制后删除）。
    """
    target_dir = Path(target_dir)
    moved: list[tuple[Path, Path]] = []
    failed: list[tuple[Path, str]] = []
    for raw in paths:
        src = Path(raw)
        if src.parent == target_dir:
            failed.append((src, '已在该文件夹'))
            continue
        if not src.is_file():
            failed.append((src, '文件不存在'))
            continue
        dst = unique_target(target_dir, src.name)
        try:
            shutil.move(str(src), str(dst))
        except OSError as error:
            failed.append((src, str(error)))
            continue
        moved.append((src, dst))
    return moved, failed


def relocate(src: Path, dst: Path) -> None:
    """撤销/重做：把路径对正/逆向搬过去（同父 = 改名，跨父 = 移动）。

    dst 已存在直接抛错（调用方丢弃该撤销条目），不覆盖用户文件。
    """
    src, dst = Path(src), Path(dst)
    if dst.exists():
        raise FileExistsError(f'目标已存在：{dst}')
    if src.parent == dst.parent:
        os.rename(src, dst)
    else:
        shutil.move(str(src), str(dst))
