"""生成 Feel 应用图标：assets/app.png（1024）+ assets/app.ico（16–256 多尺寸）。

设计：心形（Feel = 感受/情绪）+ 镂空播放符（本地媒体查看器），青绿主题渐变瓷砖。
改色/改形后重跑：.venv/Scripts/python.exe tools/make_icon.py
"""
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

SIZE = 1024
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets'


def draw(size: int = SIZE) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 1024.0, size / 1024.0)

    tile = QPainterPath()
    tile.addRoundedRect(QRectF(16, 16, 992, 992), 228, 228)
    gradient = QLinearGradient(QPointF(120, 80), QPointF(920, 960))
    gradient.setColorAt(0.0, QColor('#2BD3D8'))
    gradient.setColorAt(0.55, QColor('#0FA6B4'))
    gradient.setColorAt(1.0, QColor('#00707C'))
    p.fillPath(tile, gradient)

    p.save()
    p.setClipPath(tile)
    highlight = QRadialGradient(QPointF(300, 200), 640)
    highlight.setColorAt(0.0, QColor(255, 255, 255, 42))
    highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(16, 16, 992, 992), highlight)
    p.restore()

    p.setPen(QPen(QColor(255, 255, 255, 62), 8))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(64, 64, 896, 896), 180, 180)

    # 心形（感受）
    heart = QPainterPath()
    heart.moveTo(0, 300)
    heart.cubicTo(-70, 222, -300, 62, -300, -92)
    heart.cubicTo(-300, -240, -152, -304, 0, -164)
    heart.cubicTo(152, -304, 300, -240, 300, -92)
    heart.cubicTo(300, 62, 70, 222, 0, 300)
    heart = heart.simplified()

    # 镂空播放符（媒体）
    play = QPainterPath()
    play.moveTo(-50, -100)
    play.lineTo(-50, 104)
    play.lineTo(132, 2)
    play.closeSubpath()

    p.save()
    p.translate(512, 500)
    p.rotate(-9)
    p.scale(0.94, 0.94)
    p.fillPath(heart.subtracted(play), QColor(255, 255, 255))
    p.restore()

    p.end()
    return image


def main() -> int:
    QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    image = draw()
    png = OUT / 'app.png'
    image.save(str(png))

    from PIL import Image

    with Image.open(png) as big:
        big.convert('RGBA').save(
            OUT / 'app.ico',
            sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                   (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    print('wrote', png)
    print('wrote', OUT / 'app.ico')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
