"""Phase 6 冒烟：目录 OCR + 缓存 + 关键词搜图 + F5 重扫。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Fell
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/fell-phase6/appdata'

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fell.app import FellWindow  # noqa: E402
from fell.config import cfg  # noqa: E402

OUT = Path('C:/tmp/scratch/fell-phase6')
MEDIA = OUT / 'media'


def make_text_image(path: Path, text: str, size=(900, 300)) -> None:
    image = Image.new('RGB', size, (250, 250, 250))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 72)
    draw.text((40, 100), text, fill=(10, 10, 10), font=font)
    image.save(path)


def make_plain_image(path: Path) -> None:
    image = Image.new('RGB', (900, 300), (20, 60, 120))
    image.save(path)


def wait_for(predicate, timeout=40000, interval=100):
    elapsed = 0
    while elapsed < timeout:
        if predicate():
            return True
        QTest.qWait(interval)
        elapsed += interval
    return False


def main() -> int:
    import shutil
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    MEDIA.mkdir(parents=True)
    make_text_image(MEDIA / 'hello.png', 'HELLO FELL OCR')
    make_text_image(MEDIA / 'deepseek.png', 'DEEPSEEK MODEL')
    make_plain_image(MEDIA / 'plain.png')

    app = QApplication(sys.argv)
    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)

    # 用户可能在设置里关掉了 OCR；本阶段测的是扫描/缓存/搜索，内存里先强制打开，
    # 结束时恢复原值（不要把自己的测试状态写进用户配置）
    ocr_was_enabled = cfg.ocrEnabled.value
    cfg.set(cfg.ocrEnabled, True)

    window.open_path(MEDIA / 'hello.png')
    window.switchTo(window.shelfPage)
    QTest.qWait(200)

    shelf = window.shelfPage
    assert len(shelf.entries) == 3, len(shelf.entries)
    assert len(shelf.cards) == 3

    # 等 OCR 完成（首次含模型加载）
    assert wait_for(lambda: not window.ocr.is_running, 60000), 'OCR 未完成'
    QTest.qWait(400)
    texts = shelf.ocr_texts
    print('ocr texts:', {p.name: t[:30] for p, t in texts.items()})
    assert len(texts) == 3, texts
    assert 'HELLO' in texts[MEDIA / 'hello.png'].upper(), texts[MEDIA / 'hello.png']
    assert 'DEEPSEEK' in texts[MEDIA / 'deepseek.png'].upper()

    # 缓存写入 sqlite
    stat = (MEDIA / 'hello.png').stat()
    cached = window.store.get_ocr(MEDIA / 'hello.png', stat.st_mtime_ns, stat.st_size)
    assert cached and 'HELLO' in cached.upper()
    print('ocr cache OK')

    # 关键词搜索
    shelf.focus_search()
    shelf.searchEdit.setText('hello')
    QTest.qWait(200)
    assert list(shelf.cards) == [MEDIA / 'hello.png'], list(shelf.cards)
    shelf.searchEdit.setText('deep')
    QTest.qWait(200)
    assert list(shelf.cards) == [MEDIA / 'deepseek.png'], list(shelf.cards)
    shelf.searchEdit.setText('不存在的词')
    QTest.qWait(200)
    assert not shelf.cards
    shelf.searchEdit.clear()
    QTest.qWait(200)
    assert len(shelf.cards) == 3
    print('ocr keyword search OK')

    # F5 重新扫描（忽略缓存；全程静默，无进度 UI）
    assert not hasattr(shelf, 'ocrBar'), 'OCR 不应暴露进度 UI'
    print('ctx before rescan:', window.registry._context, window.stackedWidget.currentWidget().objectName())
    assert window.registry.trigger('rescan_ocr')
    assert wait_for(lambda: not window.ocr.is_running, 60000), '重扫未完成'
    QTest.qWait(300)
    assert len(shelf.ocr_texts) == 3
    print('rescan OK (silent)')

    # 关闭 OCR 开关后不扫描，且搜索框整个收起
    cfg.set(cfg.ocrEnabled, False)
    other = OUT / 'other'
    other.mkdir(exist_ok=True)
    make_text_image(other / 'other.png', 'SHOULD NOT SCAN')
    window.open_path(other / 'other.png')
    QTest.qWait(500)
    assert not window.ocr.is_running, 'OCR 关闭后不应扫描'
    assert shelf.searchEdit.isHidden(), '关闭搜索后搜索框应隐藏'
    cfg.set(cfg.ocrEnabled, ocr_was_enabled)
    cfg.save()  # 恢复用户原设置（本阶段临时打开过 OCR）
    assert shelf.searchEdit.isHidden() == (not bool(ocr_was_enabled))
    print('ocr setting respected')

    window.switchTo(shelf)
    QTest.qWait(150)
    window.grab().save(str(OUT / 'window_ocr.png'))
    print('SMOKE PHASE6 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
