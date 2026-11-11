"""Phase 9 冒烟：排序（名称/修改时间）、倍速、←/→ 上/下一个。

配置与数据库都写到 C:/tmp/scratch/fell-phase9/appdata，不碰用户真实 cfg/fell.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/fell-phase9')
MEDIA = OUT / 'media'

# 必须在 import fell.* 之前：config.py 在导入时就算出 CONFIG_PATH/DB_PATH
os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fell.app import FellWindow  # noqa: E402
from fell.config import SORT_MODES, cfg  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402

MTIMES = {
    'image.png': 1000,
    'video.mp4': 2000,
    'audio.m4a': 2000,
    'image.jpg': 3000,
    'audio.wav': 4000,
}
NAME_ORDER = ['audio.m4a', 'audio.wav', 'image.jpg', 'image.png', 'video.mp4']
DESC_ORDER = ['audio.wav', 'image.jpg', 'audio.m4a', 'video.mp4', 'image.png']
ASC_ORDER = ['image.png', 'audio.m4a', 'video.mp4', 'image.jpg', 'audio.wav']


def names(page) -> list[str]:
    return [entry.path.name for entry in page.entries]


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    gen_media(MEDIA)
    for name, mtime in MTIMES.items():
        os.utime(MEDIA / name, (mtime, mtime))

    app = QApplication(sys.argv)
    cfg.set(cfg.ocrEnabled, False)  # 探针目录里没有需要 OCR 的图，也避免子进程
    cfg.set(cfg.playMode, 'once')
    cfg.set(cfg.sortMode, 'name')
    cfg.save()

    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)

    page = window.playerPage
    shelf = window.shelfPage

    problems = window.registry.problems()
    print('registry problems:', problems)
    assert not problems, problems

    # ---- 排序：名称（自然序）----
    window.open_path(MEDIA / 'image.png')
    QTest.qWait(400)
    assert names(page) == NAME_ORDER, names(page)
    assert page.current_path.name == 'image.png'
    print('sort by name OK')

    # ---- 排序：时间（新→旧），队列与卡片共用同一顺序，当前文件不动 ----
    window.switchTo(shelf)
    QTest.qWait(250)
    shelf.sortCombo.setCurrentIndex(SORT_MODES.index('time_desc'))
    QTest.qWait(350)
    assert cfg.sortMode.value == 'time_desc'
    assert names(page) == DESC_ORDER, names(page)
    assert [card.entry.path.name for card in shelf._ordered_cards] == DESC_ORDER
    assert page.current_path.name == 'image.png', page.current_path
    screenshot = OUT / 'window_shelf_time_desc.png'
    window.grab().save(str(screenshot))
    print('sort by time desc OK')

    # ---- 排序：时间（旧→新）----
    shelf.sortCombo.setCurrentIndex(SORT_MODES.index('time_asc'))
    QTest.qWait(350)
    assert names(page) == ASC_ORDER, names(page)
    assert page.current_path.name == 'image.png'
    print('sort by time asc OK')

    # 回到名称排序，验证切换不只是单向
    shelf.sortCombo.setCurrentIndex(SORT_MODES.index('name'))
    QTest.qWait(350)
    assert names(page) == NAME_ORDER, names(page)
    print('sort back to name OK')

    # ---- 卡片宽度均分：行宽恰好等于视口宽度，右侧不留空 ----
    def row_width() -> tuple[int, int]:
        cols = shelf._cols()
        widths = [card.width() for card in shelf._ordered_cards[:cols]]
        return sum(widths) + shelf.grid.spacing() * (len(widths) - 1), \
            shelf.scroll.viewport().width()

    filled, viewport_w = row_width()
    assert abs(filled - viewport_w) <= 1, (filled, viewport_w)
    assert all(card.width() >= 140 for card in shelf._ordered_cards)
    cols_wide = shelf._cols()

    window.resize(820, 700)
    QTest.qWait(400)
    filled, viewport_w = row_width()
    assert abs(filled - viewport_w) <= 1, (filled, viewport_w)
    assert shelf._cols() < cols_wide, (shelf._cols(), cols_wide)
    window.resize(1180, 780)
    QTest.qWait(400)
    print('responsive card widths OK')

    # ---- 命令行/文件关联：目录打开首项，文件直接打开 ----
    assert window.open_argument(MEDIA), '目录参数未打开'
    QTest.qWait(400)
    assert page.current_path == MEDIA / NAME_ORDER[0], page.current_path
    assert window.open_argument(MEDIA / 'image.png')
    QTest.qWait(300)
    assert page.current_path == MEDIA / 'image.png', page.current_path
    assert not window.open_argument(MEDIA / 'missing.png')
    print('open argument OK')

    # ---- Ctrl+← / Ctrl+→ 上/下一个 ----
    window.switchTo(page)
    QTest.qWait(150)
    window.open_path(MEDIA / 'video.mp4')
    QTest.qWait(700)
    start_index = page.index
    QTest.keyClick(window, Qt.Key_Right, Qt.ControlModifier)
    QTest.qWait(350)
    assert page.index == (start_index + 1) % len(page.entries), page.index
    QTest.keyClick(window, Qt.Key_Left, Qt.ControlModifier)
    QTest.qWait(350)
    assert page.index == start_index, page.index
    print('ctrl+arrow keys navigate prev/next OK')

    # ---- ← / → 是 ±N 秒 ----
    cfg.set(cfg.seekStep, 1)
    cfg.save()
    page.refresh_shortcut_tooltips()
    window.open_path(MEDIA / 'video.mp4')
    QTest.qWait(700)
    page.engine.seek(0)
    QTest.qWait(200)
    page.engine.pause()
    QTest.qWait(100)
    index_before_seek = page.index
    QTest.keyClick(window, Qt.Key_Right)
    QTest.qWait(350)
    assert page.index == index_before_seek, '左右键不应切换文件'
    assert 700 <= page.engine.position <= 1200, page.engine.position
    print('arrow key seek OK')

    # ---- 倍速：按钮/菜单/快捷键 + 换文件后保持 ----
    page.set_speed(2.0)
    assert page.speedBtn.text() == '2×', page.speedBtn.text()
    assert abs(page.engine.playback_rate - 2.0) < 1e-6
    page.engine.seek(0)
    page.engine.play()
    QTest.qWait(150)
    before = page.engine.position
    QTest.qWait(600)
    advanced = page.engine.position - before
    assert advanced > 900, advanced
    print('2x playback OK:', advanced, 'ms in 600ms')

    # 换源后仍按 2×
    window.open_path(MEDIA / 'audio.wav')
    QTest.qWait(600)
    assert page.current_kind == 'audio'
    assert abs(page.engine.playback_rate - 2.0) < 1e-6, page.engine.playback_rate
    print('speed persists across files OK')

    # 快捷键 ] / [ 只改一档
    window.registry.trigger('speed_down')
    assert abs(float(cfg.speed.value) - 1.5) < 1e-6, cfg.speed.value
    window.registry.trigger('speed_up')
    assert abs(float(cfg.speed.value) - 2.0) < 1e-6, cfg.speed.value
    page.set_speed(1.0)
    print('speed shortcuts OK')

    window.grab().save(str(OUT / 'window_speed.png'))
    window.close()
    print('SMOKE PHASE9 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
