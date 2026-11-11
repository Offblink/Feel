"""Phase 12 冒烟：大目录打开文件夹的布局/窗口稳定性 + 日志系统（设置页入口）。

配置与数据库都写到 C:/tmp/scratch/feel-phase12/appdata，不碰用户真实 cfg/feel.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/feel-phase12')
MEDIA = OUT / 'media'

# 必须在 import feel.* 之前：config.py 在导入时就算出 CONFIG_PATH/DB_PATH
os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import QPoint, Qt, qWarning  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import PySide6.QtWidgets as qt_widgets  # noqa: E402
from feel import logs  # noqa: E402
from feel.app import FeelWindow  # noqa: E402
from feel.config import cfg  # noqa: E402
from feel.ui.widgets.shelf_card import CARD_H  # noqa: E402

COUNT = 120


def make_media() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    for index in range(COUNT):
        image = QImage(160, 100, QImage.Format_RGB32)
        image.fill(QColor('#3a6ea5'))
        image.save(str(MEDIA / f'big_{index:04d}.png'))


def card_rects(shelf) -> list[tuple[int, int, int, int]]:
    viewport = shelf.scroll.viewport()
    rects = []
    for card in shelf._ordered_cards:
        top_left = card.mapTo(viewport, QPoint(0, 0))
        rects.append((top_left.x(), top_left.y(), card.width(), card.height()))
    return rects


def overlaps(rects) -> int:
    count = 0
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                    and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]):
                count += 1
    return count


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    make_media()

    app = QApplication(sys.argv)
    cfg.set(cfg.ocrEnabled, False)
    cfg.set(cfg.sortMode, 'name')
    cfg.save()

    log = logs.setup()
    log.info('phase12 marker')
    assert logs.LOG_PATH.exists(), logs.LOG_PATH
    text = logs.LOG_PATH.read_text(encoding='utf-8')
    assert 'phase12 marker' in text

    # 未捕获异常与 Qt 消息都要进日志
    try:
        raise RuntimeError('phase12 boom')
    except RuntimeError:
        exc_info = sys.exc_info()
    sys.excepthook(*exc_info)
    qWarning('phase12 qt warning')
    QTest.qWait(100)
    text = logs.LOG_PATH.read_text(encoding='utf-8')
    assert '未捕获异常' in text and 'phase12 boom' in text, '未捕获异常没进日志'
    assert '[Qt] phase12 qt warning' in text, 'Qt 警告没进日志'
    print('logging capture OK')

    window = FeelWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(500)
    shelf = window.shelfPage
    page = window.playerPage
    window.switchTo(shelf)
    QTest.qWait(300)

    tops_before = len(QApplication.topLevelWidgets())
    real = qt_widgets.QFileDialog.getExistingDirectory
    qt_widgets.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(MEDIA))
    try:
        QTest.mouseClick(shelf.openFolderBtn, Qt.LeftButton)
        QTest.qWait(1500)
    finally:
        qt_widgets.QFileDialog.getExistingDirectory = real

    assert window.stackedWidget.currentWidget() is shelf, '大目录打开后跳走了'
    assert page.current_path is None, '打开文件夹不该自动播放'
    assert len(shelf.entries) == COUNT, len(shelf.entries)
    assert len(shelf._ordered_cards) == COUNT, len(shelf._ordered_cards)

    rects = card_rects(shelf)
    assert overlaps(rects) == 0, f'卡片重叠 {overlaps(rects)} 处'
    cols = max(1, len({r[0] for r in rects}))
    rows = (COUNT - 1) // cols + 1
    assert shelf.gridContainer.minimumHeight() >= rows * CARD_H, (
        shelf.gridContainer.minimumHeight(), rows
    )
    assert len(QApplication.topLevelWidgets()) == tops_before, (
        [type(w).__name__ for w in QApplication.topLevelWidgets()]
    )
    window.grab().save(str(OUT / 'shelf_big.png'))
    text = logs.LOG_PATH.read_text(encoding='utf-8')
    assert '加载文件夹' in text, '打开文件夹没有写日志'
    print('big folder layout OK, rows:', rows, 'cols:', cols)

    # 点卡片照常打开（资料库 → 播放页）
    target = shelf.cards[MEDIA / 'big_0005.png']
    QTest.mouseClick(target, Qt.LeftButton)
    QTest.qWait(700)
    assert window.stackedWidget.currentWidget() is page, '点卡片没有打开文件'
    assert page.current_path == MEDIA / 'big_0005.png', page.current_path
    print('card click still opens OK')

    # ---- 设置页日志入口：两个按钮各走各的 open_* ----
    window.switchTo(window.settingsPage)
    QTest.qWait(400)
    bar = window.settingsPage.verticalScrollBar()
    bar.setValue(bar.maximum())
    QTest.qWait(300)
    card = window.settingsPage.logCard
    assert card.isVisible(), '设置页没有日志入口'
    opened: list[str] = []
    import os as _os
    real_startfile = _os.startfile
    _os.startfile = lambda path: opened.append(path)
    try:
        QTest.mouseClick(card.openBtn, Qt.LeftButton)
        QTest.qWait(100)
        QTest.mouseClick(card.openFolderBtn, Qt.LeftButton)
        QTest.qWait(100)
    finally:
        _os.startfile = real_startfile
    assert opened and opened[0] == str(logs.LOG_PATH), opened
    assert opened[1] == str(logs.LOG_DIR), opened
    window.grab().save(str(OUT / 'settings_logs.png'))
    print('settings log entry OK:', opened)

    print('SMOKE PHASE12 OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
