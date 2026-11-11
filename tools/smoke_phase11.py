"""Phase 11 冒烟：F 全屏 / E 收藏、点别处收起标题输入框、打开文件夹、帮助页。

配置与数据库都写到 C:/tmp/scratch/fell-phase11/appdata，不碰用户真实 cfg/fell.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/fell-phase11')
MEDIA = OUT / 'media'

# 必须在 import fell.* 之前：config.py 在导入时就算出 CONFIG_PATH/DB_PATH
os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

import PySide6.QtWidgets as qt_widgets  # noqa: E402
from fell.app import FellWindow  # noqa: E402
from fell.config import cfg  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402

KEY_TOKEN = {'Left': '←', 'Right': '→', 'Up': '↑', 'Down': '↓'}


def shown(seq: str) -> str:
    for token, glyph in KEY_TOKEN.items():
        seq = seq.replace(token, glyph)
    return seq


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    gen_media(MEDIA)

    app = QApplication(sys.argv)
    cfg.set(cfg.ocrEnabled, False)
    cfg.set(cfg.sortMode, 'name')
    cfg.save()

    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    window.activateWindow()
    window.raise_()
    QTest.qWait(500)
    page = window.playerPage
    shelf = window.shelfPage

    # ---- 1) 快捷键改绑：F = 全屏，E = 收藏 ----
    assert window.registry.action('fullscreen').shortcut == 'F'
    assert window.registry.action('favorite').shortcut == 'E'
    window.open_path(MEDIA / 'video.mp4')
    QTest.qWait(800)
    assert page.has_media

    QTest.keyClick(window, Qt.Key_F)
    QTest.qWait(400)
    assert window.isFullScreen(), 'F 没有进全屏'
    QTest.keyClick(window, Qt.Key_F)
    QTest.qWait(400)
    assert not window.isFullScreen(), 'F 没有退出全屏'
    print('F fullscreen OK')

    video = page.current_path
    QTest.keyClick(window, Qt.Key_E)
    QTest.qWait(300)
    assert window.store.is_favorite(video), 'E 没有收藏'
    QTest.keyClick(window, Qt.Key_E)
    QTest.qWait(300)
    assert not window.store.is_favorite(video), 'E 没有取消收藏'
    print('E favorite OK')

    # ---- 2) 点别处收起标题输入框（并提交） ----
    window.open_path(MEDIA / 'image.png')
    QTest.qWait(500)
    assert page.current_path.name == 'image.png'
    QTest.mouseClick(page.titleLabel, Qt.LeftButton)
    QTest.qWait(100)
    assert page.titleEdit.isVisible()
    page.titleEdit.setText('blurred')
    QTest.mouseClick(page.imageLabel, Qt.LeftButton)
    QTest.qWait(600)
    assert not page.titleEdit.isVisible(), '点画面没有收起输入框'
    assert (MEDIA / 'blurred.png').exists(), '点别处应该提交改名'
    assert page.current_path == MEDIA / 'blurred.png', page.current_path
    assert page.titleLabel.text() == 'blurred.png', page.titleLabel.text()
    print('click outside closes title edit OK')

    # ---- 3) 资料库「打开文件夹」 ----
    assert window.registry.action('open_folder').shortcut == 'Ctrl+Shift+O'
    window.switchTo(shelf)
    QTest.qWait(300)
    assert shelf.openFolderBtn.isVisible(), '资料库没有「打开文件夹」按钮'
    real_dialog = qt_widgets.QFileDialog.getExistingDirectory
    qt_widgets.QFileDialog.getExistingDirectory = staticmethod(
        lambda *args, **kwargs: str(MEDIA)
    )
    try:
        QTest.mouseClick(shelf.openFolderBtn, Qt.LeftButton)
        QTest.qWait(700)
    finally:
        qt_widgets.QFileDialog.getExistingDirectory = real_dialog
    assert page.entries, '打开文件夹后没有队列'
    assert page.current_path is None, '打开文件夹不该自动选中/播放文件'
    assert window.stackedWidget.currentWidget() is shelf, '打开文件夹不该跳转播放页'
    assert page.stageStack.currentWidget() is page.emptyStage, '播放页舞台不该被换上媒体'
    # 刷新 / 排序后继续保持资料库视图（不自动打开首项）
    window.refresh_library()
    QTest.qWait(400)
    assert page.current_path is None, '刷新后自动选中了文件'
    cfg.set(cfg.sortMode, 'time_desc')
    window._apply_sort()
    QTest.qWait(300)
    assert page.current_path is None, '排序后自动选中了文件'
    assert window.stackedWidget.currentWidget() is shelf
    print('open folder stays on shelf OK, entries:', len(page.entries))

    # ---- 4) 帮助页：说明书 + 快捷键与注册表一致 ----
    assert window.registry.trigger('goto_help')
    QTest.qWait(300)
    help_page = window.helpPage
    assert window.stackedWidget.currentWidget() is help_page, 'Ctrl+4 没切到帮助页'
    texts = [label.text() for label in help_page.findChildren(QLabel)]
    help_text = '\n'.join(texts)
    assert '使用说明' in help_text and '快速上手' in help_text
    for action in window.registry.actions.values():
        for seq in action.shortcuts():
            token = shown(seq)
            assert token in help_text, f'帮助页缺少快捷键 {seq}（{action.id}）'
    assert 'F11' not in help_text, '帮助页还写着旧的全屏键 F11'
    assert 'Ctrl+Shift+O' in help_text
    assert not window.registry.problems(), window.registry.problems()
    window.grab().save(str(OUT / 'help.png'))
    print('help page OK, registry problems:', window.registry.problems())

    print('SMOKE PHASE11 OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
