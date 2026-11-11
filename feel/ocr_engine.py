"""纯 OCR 引擎（不依赖 Qt）：在独立子进程里运行，避免 onnxruntime 与 Qt 线程池死锁。"""
from __future__ import annotations

from pathlib import Path

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def recognize(path: str | Path) -> str:
    """识别单张图片，返回用空格连接的文本（异常时返回空串）。"""
    try:
        result = _get_engine()(str(path))
    except Exception:
        return ''
    if isinstance(result, tuple):
        result = result[0]
    parts = []
    for item in result or []:
        if len(item) >= 2:
            parts.append(str(item[1]))
    return ' '.join(parts)
