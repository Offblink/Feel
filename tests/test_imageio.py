"""图片解码单测：PNG 走 Qt 原生，AVIF 走 Pillow 兜底（Qt 无 qavif 插件）。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QImage  # noqa: E402

from feel.imageio import load_image  # noqa: E402


class ImageIoTest(unittest.TestCase):
    def test_png_decodes_via_qt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.png'
            source = QImage(8, 6, QImage.Format_RGB888)
            source.fill(0x804020)
            self.assertTrue(source.save(str(path)))

            decoded = load_image(path)
            self.assertFalse(decoded.isNull())
            self.assertEqual((decoded.width(), decoded.height()), (8, 6))

    def test_avif_decodes_via_pillow_fallback(self):
        try:
            from PIL import AvifImagePlugin  # noqa: F401
        except ImportError:
            self.skipTest('Pillow 未编入原生 AVIF')
        if not AvifImagePlugin.SUPPORTED:
            self.skipTest('Pillow AVIF 插件未编入解码库')

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.avif'
            from PIL import Image
            Image.new('RGB', (16, 8), (250, 5, 5)).save(path)

            decoded = load_image(path)
            self.assertFalse(decoded.isNull())
            self.assertEqual((decoded.width(), decoded.height()), (16, 8))
            # AVIF 是有损编码，颜色允许小偏差
            color = decoded.pixelColor(0, 0)
            self.assertLess(abs(color.red() - 250), 12)
            self.assertLess(abs(color.green() - 5), 12)
            self.assertLess(abs(color.blue() - 5), 12)

    def test_unknown_bytes_return_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.avif'
            path.write_bytes(b'not an image at all')
            self.assertTrue(load_image(path).isNull())


if __name__ == '__main__':
    unittest.main()
