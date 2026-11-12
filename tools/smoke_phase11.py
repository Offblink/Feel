"""Phase 11 冒烟：F 全屏 / E 收藏、点别处收起标题输入框、打开文件夹、帮助页。

配置与数据库都写到 C:/tmp/scratch/feel-phase11/appdata，不碰用户真实 cfg/feel.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/feel-phase11')
MEDIA = OUT / 'media'

# 必须在 import feel.* 之前：config.py 在导入时就算出 CONFIG_PATH/DB_PATH
os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

import PySide6.QtWidgets as qt_widgets  # noqa: E402
from feel.app import FeelWindow  # noqa: E402
from feel.config import cfg  # noqa: E402
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

    window = FeelWindow()
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

    # ---- 5) 左右键语义：视频 ←/→ 快进快退；图片 / 音频 ←/→ 上/下一个 ----
    window.open_path(MEDIA / 'video.mp4')
    QTest.qWait(900)
    assert page.current_kind == 'video', page.current_kind
    page.engine.pause()
    page.engine.seek(0)
    QTest.qWait(300)
    assert page.engine.position < 600, page.engine.position
    before = page.index
    QTest.keyClick(window, Qt.Key_Right)
    QTest.qWait(350)
    assert page.engine.position > 1400, f'视频里 → 没有快进：{page.engine.position}'
    assert page.index == before, '视频里 → 不该切换文件'
    QTest.keyClick(window, Qt.Key_Left)
    QTest.qWait(350)
    assert page.engine.position < 600, f'视频里 ← 没有后退：{page.engine.position}'
    assert page.index == before
    print('video arrow seek OK')

    images = [e.path for e in page.entries if e.kind == 'image']
    assert images, '测试媒体里没有图片'
    window.open_path(images[0])
    QTest.qWait(600)
    assert page.current_kind == 'image', page.current_kind
    before = page.index
    QTest.keyClick(window, Qt.Key_Right)
    QTest.qWait(450)
    assert page.index == (before + 1) % len(page.entries), \
        f'图片里 → 没有切到下一个：{before} -> {page.index}'
    QTest.keyClick(window, Qt.Key_Left)
    QTest.qWait(450)
    assert page.index == before, '图片里 ← 没有切回上一个'
    print('image arrow navigate OK')

    audio = next((e.path for e in page.entries if e.kind == 'audio'), None)
    assert audio is not None, '测试媒体里没有音频'
    window.open_path(audio)
    QTest.qWait(800)
    assert page.current_kind == 'audio', page.current_kind
    before = page.index
    QTest.keyClick(window, Qt.Key_Right)
    QTest.qWait(450)
    assert page.index == (before + 1) % len(page.entries), \
        f'音频里 → 没有切到下一个：{before} -> {page.index}'
    print('audio arrow navigate OK')

    # ---- 6) 帮助页键帽改键：冲突提示 / 提交 / 持久化 / tooltip 同步 / Esc 取消 ----
    assert window.registry.trigger('goto_help')
    QTest.qWait(300)
    chip = help_page.chips['bookmark_add']
    assert chip.text() == 'B', chip.text()
    QTest.mouseClick(chip, Qt.LeftButton)
    QTest.qWait(100)
    assert chip._capturing, '点键帽没有进入捕获态'
    QTest.keyClick(chip, Qt.Key_F)  # F 已被「全屏」占用
    QTest.qWait(300)
    assert window.registry.action('bookmark_add').shortcut == 'B', '冲突键被提交了'
    assert chip._capturing, '冲突后应保持捕获态等下一个键'
    QTest.keyClick(chip, Qt.Key_N)
    QTest.qWait(300)
    assert window.registry.action('bookmark_add').shortcut == 'N', \
        window.registry.action('bookmark_add').shortcut
    assert cfg.customShortcuts.value.get('bookmark_add') == 'N', \
        cfg.customShortcuts.value
    assert chip.text() == 'N', chip.text()
    assert 'N' in page.bookmarkBtn.toolTip(), page.bookmarkBtn.toolTip()
    print('chip rebind + persist + tooltip OK')

    QTest.mouseClick(chip, Qt.LeftButton)
    QTest.qWait(100)
    QTest.keyClick(chip, Qt.Key_Escape)
    QTest.qWait(200)
    assert not chip._capturing, 'Esc 没有取消捕获'
    assert window.registry.action('bookmark_add').shortcut == 'N', \
        'Esc 不该改掉已提交的键'
    print('esc cancels capture OK')

    print('SMOKE PHASE11 OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
