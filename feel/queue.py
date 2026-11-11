"""播放队列模式状态机（SPEC §5.4）。

- manual（手动上一个/下一个）：顺序模式顺序走；随机模式随机跳；
- auto（媒体播完自动续播）：单曲播放停止、列表循环下一项回绕、
  单曲循环重播当前、随机跳另一项；
- 图片没有自动续播（调用方不调 auto_index）。
"""
from __future__ import annotations

import random
from typing import Optional

PLAY_MODE_ORDER = ('once', 'list', 'one', 'shuffle')


def _random_other(count: int, index: int, rng) -> int:
    if count <= 1:
        return 0
    choice = rng.randrange(count - 1)
    return choice if choice < index else choice + 1


def step_index(count: int, index: int, mode: str, direction: int = 1,
               rng: Optional[random.Random] = None) -> Optional[int]:
    """手动上一个/下一个。direction=+1 下一个，-1 上一个。"""
    if count <= 0:
        return None
    if count == 1:
        return 0
    rng = rng or random
    if mode == 'shuffle':
        return _random_other(count, index, rng)
    return (index + direction) % count


def auto_index(count: int, index: int, mode: str,
               rng: Optional[random.Random] = None) -> Optional[int]:
    """媒体播完后的自动续播目标；None = 停止。"""
    if count <= 0:
        return None
    rng = rng or random
    if mode == 'once':
        return None
    if mode == 'one':
        return index
    if mode == 'list':
        return (index + 1) % count
    if mode == 'shuffle':
        return _random_other(count, index, rng)
    return (index + 1) % count
