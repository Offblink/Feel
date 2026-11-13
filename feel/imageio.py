"""图片解码：QImageReader 优先，Qt 不支持的格式（AVIF）回退 Pillow。

打包产物里 Qt 只带 qgif/qico/qjpeg/qtiff/qwebp 等插件，没有 qavif，
所以 AVIF 在 Qt 侧必然读不出来 —— 由 pillow-avif-plugin 兜底。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage, QImageReader


def load_image(path: str | Path) -> QImage:
    """解码整图为 QImage（自动应用 EXIF 方向），解不了返回空 QImage。"""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if not image.isNull():
        return image
    return _decode_with_pillow(path)


def _decode_with_pillow(path: str | Path) -> QImage:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return QImage()
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            # 统一转成 Qt 直接吃的打包像素（P/LA/P/16bit 一律先展开）
            image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            packed = image.tobytes('raw', image.mode)
            if image.mode == 'RGBA':
                return QImage(packed, image.width, image.height, image.width * 4,
                              QImage.Format_RGBA8888).copy()
            return QImage(packed, image.width, image.height, image.width * 3,
                          QImage.Format_RGB888).copy()
    except Exception:
        return QImage()
