"""Phase 13 冒烟：资料库筛选决定播放队列、音量滚轮（弹层抓鼠标）、深色卡片操作图标。

配置与数据库都写到 C:/tmp/scratch/feel-phase13/appdata，不碰用户真实 cfg/feel.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/feel-phase13')
MEDIA = OUT / 'media'

os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from qfluentwidgets import isDarkTheme  # noqa: E402

import PySide6.QtWidgets as qt_widgets  # noqa: E402
from feel.app import FeelWindow  # noqa: E402
from feel.config import cfg  # noqa: E402
from feel.ui.widgets.shelf_card import ShelfCard  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402


def queue_names(page) -> list[str]:
    return [entry.path.name for entry in page.entries]


def wheel(widget, delta: int) -> None:
    event = QWheelEvent(
        QPointF(8, 8), QPointF(widget.mapToGlobal(QPoint(8, 8))),
        QPoint(0, 0), QPoint(0, delta), Qt.NoButton, Qt.NoModifier,
        Qt.NoScrollPhase, False,
    )
    QApplication.sendEvent(widget, event)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    gen_media(MEDIA)

    app = QApplication(sys.argv)
    cfg.set(cfg.ocrEnabled, False)
    cfg.set(cfg.sortMode, 'name')
    cfg.save()

    window = FeelWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(500)
    page = window.playerPage
    shelf = window.shelfPage
    window.switchTo(shelf)
    QTest.qWait(300)

    real = qt_widgets.QFileDialog.getExistingDirectory
    qt_widgets.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(MEDIA))
    try:
        QTest.mouseClick(shelf.openFolderBtn, Qt.LeftButton)
        QTest.qWait(800)
    finally:
        qt_widgets.QFileDialog.getExistingDirectory = real
    assert len(shelf.entries) == 5, len(shelf.entries)
    assert page.current_path is None

    def click_card(name: str) -> None:
        window.switchTo(shelf)
        QTest.qWait(200)
        card = shelf.cards[MEDIA / name]
        QTest.mouseClick(card, Qt.LeftButton)
        QTest.qWait(500)

    # ---- 1) 分类 chip：视频 → 队列只有视频 ----
    shelf.chips['video'].click()
    QTest.qWait(200)
    assert [e.path.name for e in shelf._visible_entries()] == ['video.mp4']
    click_card('video.mp4')
    assert queue_names(page) == ['video.mp4'], queue_names(page)
    assert page.index == 0
    assert not page.prevBtn.isEnabled() and not page.nextBtn.isEnabled()
    print('category filter -> queue OK:', queue_names(page))
    assert len(shelf.entries) == 5, '资料库不该被筛选队列替换'

    # ---- 2) 分类 chip：图片 → 队列 = 图片（顺序跟随排序） ----
    window.switchTo(shelf)
    shelf.chips['image'].click()
    QTest.qWait(200)
    visible = [e.path.name for e in shelf._visible_entries()]
    click_card('image.jpg')
    assert queue_names(page) == visible, (queue_names(page), visible)
    assert page.index == queue_names(page).index('image.jpg')
    QTest.keyClick(window, Qt.Key_Right, Qt.ControlModifier)
    QTest.qWait(500)
    assert page.current_path.name == visible[1], page.current_path
    print('image filter queue + ctrl-right OK:', queue_names(page))

    # ---- 3) 扩展名下拉 → 队列只有一个扩展名 ----
    window.switchTo(shelf)
    QTest.qWait(200)
    exts = shelf._ext_options
    shelf.extCombo.setCurrentIndex(exts.index('.png'))
    QTest.qWait(200)
    click_card('image.png')
    assert queue_names(page) == ['image.png'], queue_names(page)
    print('ext filter -> queue OK')

    # ---- 4) 收藏分类 ----
    window.switchTo(shelf)
    shelf.chips['all'].click()
    shelf.extCombo.setCurrentIndex(0)
    QTest.qWait(200)
    audio = MEDIA / 'audio.m4a'
    window.store.set_favorite(audio, True)
    shelf.set_favorites(window.store.favorite_paths())
    shelf.chips['favorite'].click()
    QTest.qWait(200)
    click_card('audio.m4a')
    assert queue_names(page) == ['audio.m4a'], queue_names(page)
    print('favorite filter -> queue OK')

    # ---- 5) 排序决定队列顺序 ----
    window.switchTo(shelf)
    shelf.chips['image'].click()
    QTest.qWait(200)
    cfg.set(cfg.sortMode, 'time_desc')
    window._apply_sort()
    QTest.qWait(200)
    visible = [e.path.name for e in shelf._visible_entries()]
    click_card(visible[0])
    assert queue_names(page) == visible, (queue_names(page), visible)
    print('sort order -> queue OK:', visible)
    # 复位排序
    cfg.set(cfg.sortMode, 'name')
    window._apply_sort()
    QTest.qWait(200)

    # ---- 6) 滚轮在音量按钮 / 弹层上都生效 ----
    window.open_path(MEDIA / 'audio.m4a')
    QTest.qWait(700)
    page.engine.set_volume(50)
    page.volumeBtn.set_volume(50)
    page.volumeBtn._show_popup()
    QTest.qWait(150)
    assert page.volumeBtn._popup.isVisible(), '音量弹层未显示'
    wheel(page.volumeBtn._popup, 120)
    QTest.qWait(120)
    assert page.engine.volume == 50 + cfg.volumeStep.value, page.engine.volume
    wheel(page.volumeBtn._button, -120)
    QTest.qWait(120)
    assert page.engine.volume == 50, page.engine.volume
    page.volumeBtn._popup.hide()
    print('volume wheel on popup/button OK')

    # ---- 7) 深色模式下卡片重命名/删除图标是浅色 ----
    if not isDarkTheme():
        page.engine.pause()
        window.registry.trigger('toggle_theme')
        QTest.qWait(700)
    assert isDarkTheme()
    card = ShelfCard(shelf.entries[0])
    card.resize(200, 168)
    card._hover = True
    pixmap = card.grab()
    image = pixmap.toImage()
    rename = card._rename_rect()
    delete = card._delete_rect()

    def bright_pixels(rect) -> int:
        bright = 0
        for y in range(int(rect.top()), int(rect.bottom()) + 1):
            for x in range(int(rect.left()), int(rect.right()) + 1):
                color = image.pixelColor(x, y)
                if color.red() + color.green() + color.blue() > 480:
                    bright += 1
        return bright

    assert bright_pixels(rename) > 6, '深色下重命名图标不够浅'
    assert bright_pixels(delete) > 6, '深色下删除图标不够浅'
    card.deleteLater()
    window.switchTo(shelf)
    QTest.qWait(400)
    window.grab().save(str(OUT / 'dark_cards.png'))
    print('dark card action icons are light OK')

    print('SMOKE PHASE13 OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
