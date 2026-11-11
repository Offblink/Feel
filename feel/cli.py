"""启动参数解析：支持「用 Feel 打开」文件关联（argv[1] = 文件或目录）。"""
from __future__ import annotations

import os
from pathlib import Path


def find_open_target(args: list[str]) -> Path | None:
    """返回第一个存在的文件/目录；忽略 Qt 参数（``-style``）与不存在的路径。

    ``run.bat`` 会先 ``cd`` 到项目目录，所以带 ``FEEL_LAUNCH_DIR`` 时把相对路径
    按用户调用时的目录解析，而不是 Feel 的安装目录。
    """
    base = os.environ.get('FEEL_LAUNCH_DIR')
    for raw in args:
        if not raw or raw.startswith('-'):
            continue
        path = Path(raw.strip('"').strip("'"))
        if not path.is_absolute() and base:
            path = Path(base) / path
        try:
            if path.exists():
                return path
        except OSError:
            continue
    return None
