"""Phase 15 冒烟：资料库目录导航 / 空态 / 返回前进 / 移入 / 拖拽 / 撤销重做（SPEC §11）。

覆盖 FR-27~32：文件夹卡置顶与点击进入、空目录中央空态（两种文案）、面包屑跳转与
窄窗省略号、Alt+← 与按钮返回/前进、选择模式移入（打桩文件夹选择框）、合成拖拽
（非媒体拒绝 / 非落点忽略 / 文件夹卡落点移动）、涂抹与全选不含文件夹、播放页队列
不拽回资料库、Ctrl+Z/Y 往返（移动 + 重命名）、搜索框里 Ctrl+Z 归文本撤销。

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

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
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


def center_in_page(shelf, widget) -> QPoint:
    top_left = widget.mapTo(shelf, QPoint(0, 0))
    return top_left + QPoint(widget.width() // 2, widget.height() // 2)


def folder_card(shelf, name: str) -> FolderCard:
    for card in shelf._folder_cards:
        if card.folder.name == name:
            return card
    raise AssertionError(f'没有文件夹卡 {name}')


def crumb_buttons(shelf):
    return shelf._crumbsBox.findChildren(TransparentPushButton)


def drag_event(cls, pos: QPoint, mime: QMimeData, accept: bool = False):
    # PySide6 签名要 QPoint + 单个 DropAction（处理器不读 actions，用 CopyAction 即可）
    event = cls(QPoint(pos), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    if not accept:
        event.ignore()  # QEvent 默认 accepted=true，先归零让断言只认处理器行为
    return event


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
    for aid in ('nav_back', 'nav_forward', 'move_selected', 'undo', 'redo'):
        assert aid in window.registry.actions, aid
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
    assert not shelf.undoBtn.isEnabled() and not shelf.redoBtn.isEnabled()
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
    assert shelf.undoBtn.isEnabled() and not shelf.redoBtn.isEnabled()
    print('move-selected OK')

    # ---- 7) Ctrl+Z / Ctrl+Y 往返（FR-30，移动类）----
    window.activateWindow()
    shelf.searchEdit.clearFocus()
    QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    QTest.qWait(300)
    assert (TREE / 'z1.png').exists() and (TREE / 'z2.png').exists(), '撤销移入失败'
    assert not (TREE / 'a_sub' / 'z1.png').exists()
    assert window.store.favorite_paths() == {TREE / 'z1.png'}, \
        window.store.favorite_paths()
    assert shelf.countLabel.text() == '5 个文件夹 · 3 项', shelf.countLabel.text()
    assert not shelf.undoBtn.isEnabled() and shelf.redoBtn.isEnabled()

    QTest.keyClick(window, Qt.Key_Y, Qt.ControlModifier)
    QTest.qWait(300)
    assert (TREE / 'a_sub' / 'z1.png').exists() and not (TREE / 'z1.png').exists(), \
        '重做移入失败'
    assert shelf.undoBtn.isEnabled() and not shelf.redoBtn.isEnabled()

    QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    QTest.qWait(300)
    assert (TREE / 'z1.png').exists(), '第二次撤销应回到移入前'
    print('undo/redo OK')

    # ---- 8) 拖拽移入（FR-32）：非媒体拒绝 / 非落点忽略 / 文件夹卡移动 ----
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(TREE / 'z3.png'))])
    bad = QMimeData()
    bad.setUrls([QUrl.fromLocalFile(str(TREE / 'note.txt'))])
    target = folder_card(shelf, 'c_sub')
    over_media = shelf._media_cards()[0]
    pos_media = center_in_page(shelf, over_media)
    pos_target = center_in_page(shelf, target)

    enter_bad = drag_event(QDragEnterEvent, pos_target, bad)
    QApplication.sendEvent(shelf, enter_bad)
    assert not enter_bad.isAccepted(), '非媒体拖入不该被接受'

    enter = drag_event(QDragEnterEvent, pos_media, mime, accept=True)
    QApplication.sendEvent(shelf, enter)
    assert enter.isAccepted(), '有效媒体 dragEnter 应先接受（落点后面裁决）'

    move_off = drag_event(QDragMoveEvent, pos_media, mime)
    QApplication.sendEvent(shelf, move_off)
    assert not move_off.isAccepted(), '不在文件夹卡上不该接受'
    drop_off = drag_event(QDropEvent, pos_media, mime)
    QApplication.sendEvent(shelf, drop_off)
    assert not drop_off.isAccepted()
    assert (TREE / 'z3.png').exists(), '落点不对不能搬'

    # Qt 在合成事件里：一次 drop 之后拖拽会话即结束，后续 dragMove 不再投递
    # （真实拖拽每轮都从 dragEnter 开始，不受影响）——这里补一次 enter 再 move
    enter_on = drag_event(QDragEnterEvent, pos_target, mime, accept=True)
    QApplication.sendEvent(shelf, enter_on)
    assert enter_on.isAccepted()
    move_on = drag_event(QDragMoveEvent, pos_target, mime, accept=True)
    QApplication.sendEvent(shelf, move_on)
    assert move_on.isAccepted()
    drop_on = drag_event(QDropEvent, pos_target, mime, accept=True)
    QApplication.sendEvent(shelf, drop_on)
    assert drop_on.isAccepted()
    QTest.qWait(300)
    assert (TREE / 'c_sub' / 'z3.png').exists() and not (TREE / 'z3.png').exists(), \
        '拖拽移入失败'
    assert shelf.undoBtn.isEnabled()
    print('drag-drop OK')

    # ---- 9) 涂抹 / 全选不含文件夹（D7）----
    shelf.select_all()
    assert shelf.selected == {TREE / 'z1.png', TREE / 'z2.png'}, shelf.selected
    media = shelf._media_cards()
    shelf.begin_paint(center_in_viewport(shelf, media[0]))
    shelf.paint_to(center_in_viewport(shelf, folder_card(shelf, 'a_sub')))
    shelf.end_paint()
    assert TREE / 'a_sub' not in shelf.selected, '文件夹进了涂抹选区'
    assert all(p.suffix == '.png' for p in shelf.selected), shelf.selected
    print('selection excludes folders OK')

    # ---- 10) 选择模式下点文件夹卡 = 进入（overlay 起笔特判）----
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

    # ---- 11) 播放队列变化不拽回资料库（D9）----
    shelf.navigate_to(TREE / 'a_sub')
    QTest.qWait(150)
    page.queueChanged.emit()  # 模拟播放页队列刷新（含异目录场景）
    QTest.qWait(150)
    assert shelf.current_folder == TREE / 'a_sub', '播放页队列把资料库拽回去了'
    QTest.mouseClick(shelf.backBtn, Qt.LeftButton)
    QTest.qWait(150)
    assert shelf.current_folder == TREE, shelf.current_folder
    print('queue isolation OK')

    # ---- 12) 搜索框里 Ctrl+Z 归文本撤销，不触发全局撤销（已知陷阱验证）----
    shelf.set_search_visible(True)
    shelf.searchEdit.setFocus()
    shelf.searchEdit.setText('abc')
    QTest.qWait(100)
    assert window.undoStack.can_undo(), '栈上应有第 8 步的拖入条目'
    QTest.keyClick(shelf.searchEdit, Qt.Key_Z, Qt.ControlModifier)
    QTest.qWait(150)
    assert (TREE / 'c_sub' / 'z3.png').exists(), \
        '搜索框里 Ctrl+Z 不该触发全局撤销'
    assert window.undoStack.can_undo()
    shelf.searchEdit.clear()
    shelf.set_search_visible(False)
    print('search Ctrl+Z isolation OK')

    # ---- 13) 重命名撤销 / 重做往返（FR-30，重命名类）----
    window.activateWindow()
    shelf.searchEdit.clearFocus()
    entry = next(e for e in shelf.entries if e.path.name == 'z1.png')
    assert window.rename_file(entry, 'z1_renamed')
    QTest.qWait(300)
    assert (TREE / 'z1_renamed.png').exists() and not (TREE / 'z1.png').exists()
    QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    QTest.qWait(300)
    assert (TREE / 'z1.png').exists() and not (TREE / 'z1_renamed.png').exists(), \
        '撤销重命名失败'
    QTest.keyClick(window, Qt.Key_Y, Qt.ControlModifier)
    QTest.qWait(300)
    assert (TREE / 'z1_renamed.png').exists(), '重做重命名失败'
    QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    QTest.qWait(300)
    assert (TREE / 'z1.png').exists(), '再撤销应回到原名'
    print('rename undo/redo OK')

    # ---- 14) 日志与收尾 ----
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
