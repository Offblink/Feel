"""删除到 Windows 回收站（FR-09，零依赖 ctypes）。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400

_FILEOP_FLAGS = wintypes.WORD


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND),
        ('wFunc', wintypes.UINT),
        ('pFrom', wintypes.LPCWSTR),
        ('pTo', wintypes.LPCWSTR),
        ('fFlags', _FILEOP_FLAGS),
        ('fAnyOperationsAborted', wintypes.BOOL),
        ('hNameMappings', ctypes.c_void_p),
        ('lpszProgressTitle', wintypes.LPCWSTR),
    ]


def move_to_recycle_bin(path: str | Path) -> tuple[bool, str]:
    """把文件移入回收站。返回 (成功, 错误信息)。"""
    target = Path(path)
    try:
        resolved = str(target.resolve())
    except OSError:
        resolved = str(target)
    if not target.exists():
        return False, '文件不存在'

    source = ctypes.create_unicode_buffer(resolved + '\0')  # 双 \0 终止
    operation = _SHFILEOPSTRUCTW()
    operation.wFunc = FO_DELETE
    operation.pFrom = ctypes.cast(source, ctypes.c_wchar_p)
    operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        return False, f'回收站操作失败（code {result}）'
    if operation.fAnyOperationsAborted:
        return False, '操作被取消'
    return True, ''
