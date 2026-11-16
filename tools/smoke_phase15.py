"""Phase 15 冒烟：资料库目录导航 / 空态 / 返回前进 / 移入 / 目录当文件类型（SPEC §11）。

覆盖 FR-27/28/29/31：文件夹卡置顶与点击进入、空目录中央空态（两种文案）、面包屑跳转与
窄窗省略号、Alt+← 与按钮返回/前进、选择模式移入（打桩文件夹选择框，含整个文件夹）、
文件夹参与涂抹/全选、播放页队列不拽回资料库、文件夹改名/收藏/分类过滤/搜索按名字、
文件夹删除。撤销/重做与拖拽移入均已移除（二轮、三轮拍板），不再覆盖。

配置与数据库都写到 C:/tmp/scratch/feel-phase15/appdata，不碰用户真实 cfg/feel.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/feel-phase15')
TREE = OUT / 'tree'

# 必须在 import feel.* 之前：config.py 在导入时就算出 CONFIG_PATH/DB_PATH
os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QImage,
    QMouseEvent,
)
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402
from qfluentwidgets import TransparentPushButton  # noqa: E402

from feel import logs  # noqa: E402
from feel.app import FeelWindow  # noqa: E402
from feel.config import cfg  # noqa: E402
from feel.ui.widgets.folder_card import FolderCard  # noqa: E402


def png(path: Path, color: str) -> None:
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(QColor(color))
    image.save(str(path))


def make_tree() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    TREE.mkdir(parents=True)
    for name in ('z1.png', 'z2.png', 'z3.png'):
        png(TREE / name, '#3a6ea5')
    (TREE / 'note.txt').write_text('not media', encoding='utf-8')
    (TREE / 'a_sub').mkdir()
    (TREE / 'b_empty').mkdir()
    (TREE / 'c_sub').mkdir()
    (TREE / 'd_texts').mkdir()
    png(TREE / 'a_sub' / 'one.png', '#a53a3a')
    png(TREE / 'c_sub' / 'c1.png', '#3aa53a')
    png(TREE / 'c_sub' / 'c2.png', '#3aa53a')
    (TREE / 'd_texts' / 'readme.txt').write_text('x', encoding='utf-8')
    # 深链路：面包屑 11 段长名，窄窗（FluentWindow 最小宽度 ~826px，
    # crumbsBox ~535px，全量估算 ~822px）才放得下 → 触发省略号
    (TREE / 'deep' / 'level1' / 'level2' / 'level3'
     / 'level4' / 'level5').mkdir(parents=True)


def center_in_viewport(shelf, widget) -> QPoint:
    top_left = widget.mapTo(shelf.scroll.viewport(), QPoint(0, 0))
    return top_left + QPoint(widget.width() // 2, widget.height() // 2)


def folder_card(shelf, name: str) -> FolderCard:
    for card in shelf._folder_cards:
        if card.folder.name == name:
            return card
    raise AssertionError(f'没有文件夹卡 {name}')


def crumb_buttons(shelf):
    return shelf._crumbsBox.findChildren(TransparentPushButton)


def main() -> int:
    make_tree()

    app = QApplication(sys.argv)
    cfg.set(cfg.ocrEnabled, False)
    cfg.set(cfg.sortMode, 'name')
    cfg.set(cfg.customShortcuts, {})
    cfg.save()

    log = logs.setup()
    window = FeelWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(700)  # 首帧后补：设置/帮助页 + 动作注册

    shelf = window.shelfPage
    page = window.playerPage
    assert not window.registry.problems(), window.registry.problems()
    for aid in ('nav_back', 'nav_forward', 'move_selected'):
        assert aid in window.registry.actions, aid
    for aid in ('undo', 'redo'):
        assert aid not in window.registry.actions, f'{aid} 应已移除'
    print('actions OK')

    # ---- 1) 打开文件 → 资料库同目录，文件夹卡置顶（FR-27）----
    window.open_path(TREE / 'z1.png')
    window.switchTo(shelf)
    QTest.qWait(500)
    assert shelf.current_folder == TREE, shelf.current_folder
    assert [c.folder.name for c in shelf._folder_cards] == \
        ['a_sub', 'b_empty', 'c_sub', 'd_texts', 'deep'], \
        [c.folder.name for c in shelf._folder_cards]
    assert all(isinstance(c, FolderCard) for c in shelf._ordered_cards[:5])
    assert len(shelf._media_cards()) == 3, len(shelf._media_cards())
    assert shelf.countLabel.text() == '5 个文件夹 · 3 项', shelf.countLabel.text()
    assert not shelf.backBtn.isEnabled() and not shelf.forwardBtn.isEnabled()
    window.grab().save(str(OUT / 'p15_shelf_root.png'))
    print('folder cards OK')

    # ---- 2) 点文件夹卡进入；播放页队列不受影响 ----
    QTest.mouseClick(folder_card(shelf, 'a_sub'), Qt.LeftButton)
    QTest.qWait(200)
    assert shelf.current_folder == TREE / 'a_sub', shelf.current_folder
    assert [e.path.name for e in shelf.entries] == ['one.png']
    assert shelf.backBtn.isEnabled() and not shelf.forwardBtn.isEnabled()
    assert page.current_path == TREE / 'z1.png', page.current_path
    print('folder click OK')

    # ---- 3) 空目录中央空态，两种文案（FR-28）----
    shelf.navigate_to(TREE / 'b_empty')
    QTest.qWait(150)
    assert shelf.emptyLabel.isVisible(), '空态没显示'
    assert shelf.emptyLabel.text() == '此文件夹为空', shelf.emptyLabel.text()
    assert shelf.emptyLabel.geometry() == shelf.scroll.viewport().rect()
    assert page.current_path == TREE / 'z1.png', '浏览空目录不能动播放队列'

    shelf.navigate_to(TREE / 'd_texts')
    QTest.qWait(150)
    assert shelf.emptyLabel.text() == '此文件夹没有图片 / 音频 / 视频', \
        shelf.emptyLabel.text()
    print('empty state OK')

    # ---- 4) 面包屑跳转 + 窄窗口省略号（FR-27）----
    names = [b.text() for b in crumb_buttons(shelf)]
    assert names[-1] == 'd_texts', names
    tree_btn = next(b for b in crumb_buttons(shelf) if b.text() == TREE.name)
    QTest.mouseClick(tree_btn, Qt.LeftButton)
    QTest.qWait(150)
    assert shelf.current_folder == TREE, shelf.current_folder

    # 深目录 11 段面包屑：缩到窗口最小宽度也应裁出省略号
    shelf.navigate_to(TREE / 'deep' / 'level1' / 'level2'
                      / 'level3' / 'level4' / 'level5')
    QTest.qWait(150)
    window.resize(460, 700)
    QTest.qWait(400)
    assert any(b.text() == '…' for b in crumb_buttons(shelf)), \
        f'窄窗口面包屑没出省略号: {[b.text() for b in crumb_buttons(shelf)]}'
    window.resize(1180, 780)
    QTest.qWait(400)
    assert not any(b.text() == '…' for b in crumb_buttons(shelf)), \
        '恢复宽度后省略号应消失'
    print('breadcrumb OK')

    # ---- 5) 返回/前进：Alt+← 与按钮（FR-29）----
    QTest.keyClick(window, Qt.Key_Left, Qt.AltModifier)
    QTest.qWait(150)
    assert shelf.current_folder == TREE, shelf.current_folder
    assert shelf.forwardBtn.isEnabled()
    QTest.mouseClick(shelf.forwardBtn, Qt.LeftButton)
    QTest.qWait(150)
    assert shelf.current_folder == \
        TREE / 'deep' / 'level1' / 'level2' / 'level3' / 'level4' / 'level5', \
        shelf.current_folder
    assert not shelf.forwardBtn.isEnabled() and shelf.backBtn.isEnabled()
    tree_btn = next(b for b in crumb_buttons(shelf) if b.text() == TREE.name)
    QTest.mouseClick(tree_btn, Qt.LeftButton)
    QTest.qWait(150)
    assert shelf.current_folder == TREE, shelf.current_folder
    print('back/forward OK')

    # ---- 6) 选择模式「移入」：文件系统 + 收藏迁移 + 按钮态（FR-31）----
    window.toggle_favorite(TREE / 'z1.png')
    shelf.toggle_paint_mode()
    QTest.qWait(100)
    assert not shelf.moveBtn.isHidden(), '选择模式下移入按钮应可见'
    shelf.selected = {TREE / 'z1.png', TREE / 'z2.png'}
    shelf._refresh_selection()
    assert shelf.selLabel.text() == '已选 2', shelf.selLabel.text()

    real_get = QFileDialog.getExistingDirectory
    QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: str(TREE / 'a_sub'))
    try:
        shelf.move_selected()
    finally:
        QFileDialog.getExistingDirectory = real_get
    QTest.qWait(300)
    assert not (TREE / 'z1.png').exists() and not (TREE / 'z2.png').exists()
    assert (TREE / 'a_sub' / 'z1.png').exists()
    assert (TREE / 'a_sub' / 'z2.png').exists()
    assert window.store.favorite_paths() == {TREE / 'a_sub' / 'z1.png'}, \
        window.store.favorite_paths()
    assert shelf.selected == set(), shelf.selected
    assert shelf.countLabel.text() == '5 个文件夹 · 1 项', shelf.countLabel.text()
    print('move-selected OK')

    # ---- 7) 移入结果持久 + 收藏随迁可逆（无撤销；手动移回归位，后续段还要用三个文件）----
    assert window.move_to_folder([TREE / 'a_sub' / 'z1.png',
                                  TREE / 'a_sub' / 'z2.png'], str(TREE))
    QTest.qWait(300)
    assert (TREE / 'z1.png').exists() and (TREE / 'z2.png').exists(), '移回失败'
    assert not (TREE / 'a_sub' / 'z1.png').exists()
    assert window.store.favorite_paths() == {TREE / 'z1.png'}, \
        window.store.favorite_paths()
    assert shelf.countLabel.text() == '5 个文件夹 · 3 项', shelf.countLabel.text()
    print('move back OK')

    # ---- 8) 文件夹参与涂抹 / 全选（2026-11-16 二轮：当成文件类型）----
    shelf.select_all()
    folder_paths = {c.folder for c in shelf._folder_cards}
    assert folder_paths <= shelf.selected, '全选应包含文件夹'
    assert {TREE / 'z1.png', TREE / 'z2.png'} <= shelf.selected, shelf.selected
    # 取消笔从媒体卡扫回文件夹行：区间内的文件夹与媒体一并退出选区
    media = shelf._media_cards()
    shelf.begin_paint(center_in_viewport(shelf, media[0]))
    shelf.paint_to(center_in_viewport(shelf, folder_card(shelf, 'a_sub')))
    shelf.end_paint()
    assert TREE / 'a_sub' not in shelf.selected, '取消笔应把扫过的文件夹退掉'
    assert media[0].path not in shelf.selected, '取消笔应把起笔媒体退掉'
    print('folders selectable OK')

    # ---- 9) 选择模式下点文件夹卡 = 进入（overlay 起笔特判）----
    target = folder_card(shelf, 'c_sub')
    center = QPoint(target.width() // 2, target.height() // 2)
    # QWidget.mapFrom(source, pos) 只认祖先：source 是后代时走 fallback 返回垃圾，
    # 必须经全局坐标中转
    local = shelf.overlay.mapFromGlobal(target.mapToGlobal(center))
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(local), QPointF(local),
                        target.mapToGlobal(center), Qt.LeftButton, Qt.LeftButton,
                        Qt.NoModifier)
    QApplication.sendEvent(shelf.overlay, press)
    QTest.qWait(200)
    assert shelf.current_folder == TREE / 'c_sub', shelf.current_folder
    shelf.toggle_paint_mode()
    QTest.mouseClick(shelf.backBtn, Qt.LeftButton)
    QTest.qWait(150)
    assert shelf.current_folder == TREE, shelf.current_folder
    print('overlay folder press OK')

    # ---- 10) 播放队列变化不拽回资料库（D9）----
    shelf.navigate_to(TREE / 'a_sub')
    QTest.qWait(150)
    page.queueChanged.emit()  # 模拟播放页队列刷新（含异目录场景）
    QTest.qWait(150)
    assert shelf.current_folder == TREE / 'a_sub', '播放页队列把资料库拽回去了'
    QTest.mouseClick(shelf.backBtn, Qt.LeftButton)
    QTest.qWait(150)
    assert shelf.current_folder == TREE, shelf.current_folder
    print('queue isolation OK')

    # ---- 11) 文件夹当文件类型：改名 / 收藏 / 分类过滤 / 搜索按名字 ----
    # 改名（文件夹卡走 rename_file 的 Path 入口）
    assert window.rename_file(TREE / 'd_texts', 'd_renamed')
    QTest.qWait(300)
    assert (TREE / 'd_renamed').is_dir() and not (TREE / 'd_texts').exists()
    assert any(c.folder.name == 'd_renamed' for c in shelf._folder_cards), \
        [c.folder.name for c in shelf._folder_cards]

    # 收藏文件夹（♥ → 收藏筛选里出现）
    window.toggle_favorite(TREE / 'a_sub')
    assert TREE / 'a_sub' in window.store.favorite_paths()
    assert folder_card(shelf, 'a_sub').favorite, '文件夹卡 ♥ 没亮'

    # 分类过滤对文件夹生效：图片 → 全隐藏；收藏 → 只剩已收藏的
    shelf._on_category('image')
    QTest.qWait(100)
    assert not shelf._folder_cards, [c.folder.name for c in shelf._folder_cards]
    shelf._on_category('favorite')
    QTest.qWait(100)
    assert [c.folder.name for c in shelf._folder_cards] == ['a_sub'], \
        [c.folder.name for c in shelf._folder_cards]
    shelf._on_category('all')
    QTest.qWait(100)
    assert len(shelf._folder_cards) == 5, \
        [c.folder.name for c in shelf._folder_cards]

    # 搜索 = OCR 文本 ∪ 文件名 ∪ 目录名（图片搜索关着也按名字匹配）
    shelf.set_search_visible(True)
    shelf.searchEdit.setText('d_renamed')
    QTest.qWait(150)
    assert [c.folder.name for c in shelf._folder_cards] == ['d_renamed'], \
        [c.folder.name for c in shelf._folder_cards]
    shelf.searchEdit.setText('z1')
    QTest.qWait(150)
    assert not shelf._folder_cards, '目录名不匹配时文件夹应被滤掉'
    visible = shelf.visible_paths()
    assert TREE / 'z1.png' in visible and TREE / 'z2.png' not in visible, visible
    shelf.searchEdit.clear()
    shelf.set_search_visible(False)
    QTest.qWait(100)
    print('folder rename/favorite/filter/search OK')

    # ---- 12) 文件夹删除 + 选择模式移入整个文件夹 ----
    doomed = TREE / 'doomed'
    doomed.mkdir()
    (doomed / 'inner.png').write_bytes(b'x')
    shelf.rescan()
    QTest.qWait(150)
    assert any(c.folder == doomed for c in shelf._folder_cards)
    assert window.delete_paths([doomed], confirm=False)
    QTest.qWait(300)
    assert not doomed.exists(), '文件夹删除失败（应回收站）'
    assert not any(c.folder == doomed for c in shelf._folder_cards)

    real_get2 = QFileDialog.getExistingDirectory
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(TREE / 'a_sub'))
    try:
        shelf.selected = {TREE / 'deep'}
        shelf._refresh_selection()
        shelf.move_selected()
    finally:
        QFileDialog.getExistingDirectory = real_get2
    QTest.qWait(300)
    assert not (TREE / 'deep').exists() and (TREE / 'a_sub' / 'deep').exists(), \
        '文件夹移入失败'
    print('folder delete/move OK')

    # ---- 13) 日志与收尾 ----
    text = logs.LOG_PATH.read_text(encoding='utf-8')
    assert '资料库导航到' in text, '导航没写日志'
    assert '移入' in text, '移入没写日志'
    assert '未捕获异常' not in text, '存在未捕获异常'
    window.grab().save(str(OUT / 'p15_final.png'))
    window.close()
    QTest.qWait(200)
    print('phase15 PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
