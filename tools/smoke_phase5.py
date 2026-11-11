"""Phase 5 冒烟：资料库卡片、筛选、涂抹多选/全选、重命名、删除、点击打开。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Feel
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/feel-phase5/appdata'

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from feel.app import FeelWindow  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402

OUT = Path('C:/tmp/scratch/feel-phase5')
MEDIA = OUT / 'media'


def wait_for(predicate, timeout=8000, interval=50):
    elapsed = 0
    while elapsed < timeout:
        if predicate():
            return True
        QTest.qWait(interval)
        elapsed += interval
    return False


def card_center_in_viewport(shelf, card) -> QPoint:
    return card.mapTo(shelf.scroll.viewport(), card.rect().center())


def main() -> int:
    import shutil
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    gen_media(MEDIA)

    app = QApplication(sys.argv)
    window = FeelWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)

    # 打开一个文件 → 同目录 5 个条目进播放页与资料库
    window.open_path(MEDIA / 'image.png')
    QTest.qWait(300)
    window.switchTo(window.shelfPage)  # shelf 的可见性断言需要页面在前台
    QTest.qWait(300)
    shelf = window.shelfPage
    page = window.playerPage
    assert len(shelf.entries) == 5, [e.path.name for e in shelf.entries]
    assert len(shelf.cards) == 5, len(shelf.cards)
    assert shelf.countLabel.text() == '5 项', shelf.countLabel.text()

    # 顶栏收敛为「刷新 / 选择」：重命名、删除不在顶栏，选择模式内才出现
    assert shelf.refreshBtn.text() == '刷新', shelf.refreshBtn.text()
    assert shelf.paintBtn.text() == '选择', shelf.paintBtn.text()
    assert not hasattr(shelf, 'renameBtn'), '资料库顶栏不应再有重命名按钮'
    assert not shelf.selectAllBtn.isVisible() and not shelf.deleteBtn.isVisible()
    assert not shelf.cancelSelectBtn.isVisible()

    # 卡片悬停操作：左上角 重命名 / 删除（独立卡片，避免触发窗口级确认框）
    from feel.ui.widgets.shelf_card import ShelfCard  # noqa: E402
    probe = ShelfCard(shelf.entries[0])
    probe._hover = True
    hits = []
    probe.deleteRequested.connect(lambda e: hits.append(('delete', e.path)))
    def _press(widget, pos):
        for kind, buttons in ((QEvent.MouseButtonPress, Qt.LeftButton),
                              (QEvent.MouseButtonRelease, Qt.NoButton)):
            event = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(pos)),
                                Qt.LeftButton, buttons, Qt.NoModifier)
            QApplication.sendEvent(widget, event)
    _press(probe, QPoint(20, 18))
    assert probe._edit is not None, '悬停重命名未打开内联编辑'
    probe._cancel_rename()
    _press(probe, QPoint(44, 18))
    assert hits == [('delete', shelf.entries[0].path)], hits
    probe.deleteLater()
    print('card hover rename/delete OK')

    problems = window.registry.problems()
    print('registry problems:', problems)
    assert not problems, problems

    # 缩略图：图片/视频有图，音频走占位
    shelf.thumbs.wait_idle(10000)
    QTest.qWait(300)
    image_card = shelf.cards[MEDIA / 'image.png']
    video_card = shelf.cards[MEDIA / 'video.mp4']
    audio_card = shelf.cards[MEDIA / 'audio.wav']
    assert wait_for(lambda: image_card.has_thumbnail, 3000), '图片缩略图缺失'
    assert wait_for(lambda: video_card.has_thumbnail, 5000), '视频缩略图缺失'
    assert not audio_card.has_thumbnail, '音频不应有缩略图（应走占位）'
    print('thumbnails OK (image+video generated, audio placeholder)')

    # 分类筛选
    shelf._on_category('image')
    QTest.qWait(150)
    assert len(shelf.cards) == 2, len(shelf.cards)
    shelf._on_category('all')
    QTest.qWait(150)
    assert len(shelf.cards) == 5

    # 扩展名细分
    exts = shelf._ext_options
    png_index = exts.index('.png')
    shelf.extCombo.setCurrentIndex(png_index)
    QTest.qWait(150)
    assert list(shelf.cards) == [MEDIA / 'image.png'], list(shelf.cards)
    shelf.extCombo.setCurrentIndex(0)
    QTest.qWait(150)
    assert len(shelf.cards) == 5
    print('category + extension filter OK')

    # 涂抹多选：一维顺序取起终点之间的卡片（跳过中间也包含）
    shelf.toggle_paint_mode()
    QTest.qWait(100)
    assert shelf.overlay.isVisible()
    assert shelf.selectAllBtn.isVisible() and shelf.deleteBtn.isVisible()
    assert shelf.cancelSelectBtn.isVisible() and shelf.selLabel.isVisible()
    ordered = [shelf.cards[e.path] for e in shelf.entries]
    order_names = [e.path.name for e in shelf.entries]
    assert len(ordered) == 5, order_names
    shelf.begin_paint(card_center_in_viewport(shelf, ordered[0]))
    shelf.paint_to(card_center_in_viewport(shelf, ordered[2]))
    shelf.end_paint()
    QTest.qWait(80)
    assert len(shelf.selected) == 3, (order_names, shelf.selected)
    assert all(ordered[i].selected for i in range(3))

    # 反选：起点落在已选卡片上 → 取消该范围
    shelf.begin_paint(card_center_in_viewport(shelf, ordered[1]))
    shelf.paint_to(card_center_in_viewport(shelf, ordered[3]))
    shelf.end_paint()
    QTest.qWait(80)
    assert len(shelf.selected) == 1, shelf.selected
    assert ordered[0].selected and not ordered[1].selected

    # 起笔后不松手回拖：区间收缩，涂出去的卡片要撤销
    shelf.selected = set()
    shelf._refresh_selection()
    shelf.begin_paint(card_center_in_viewport(shelf, ordered[0]))
    shelf.paint_to(card_center_in_viewport(shelf, ordered[4]))
    QTest.qWait(50)
    assert len(shelf.selected) == 5, shelf.selected
    shelf.paint_to(card_center_in_viewport(shelf, ordered[1]))   # 回拖到第 2 张
    shelf.end_paint()
    QTest.qWait(50)
    assert len(shelf.selected) == 2, shelf.selected
    assert ordered[0].selected and ordered[1].selected
    assert not ordered[2].selected and not ordered[4].selected

    # 取消笔同样可回拖撤销：全选后从第 1 张拖到第 5 张再拖回第 3 张
    shelf.select_all()
    shelf.begin_paint(card_center_in_viewport(shelf, ordered[0]))
    shelf.paint_to(card_center_in_viewport(shelf, ordered[4]))
    QTest.qWait(50)
    assert not shelf.selected, shelf.selected
    shelf.paint_to(card_center_in_viewport(shelf, ordered[2]))
    shelf.end_paint()
    QTest.qWait(50)
    assert len(shelf.selected) == 2, shelf.selected
    assert ordered[3].selected and ordered[4].selected

    # 真实鼠标事件走 Overlay：按下→拖到第 5 张→回拖到第 2 张→松开
    shelf.selected = set()
    shelf._refresh_selection()
    overlay = shelf.overlay
    p0 = shelf.cards[shelf.entries[0].path].mapTo(shelf.scroll.viewport(),
                                                  shelf.cards[shelf.entries[0].path].rect().center())
    p4 = shelf.cards[shelf.entries[4].path].mapTo(shelf.scroll.viewport(),
                                                  shelf.cards[shelf.entries[4].path].rect().center())
    p1 = shelf.cards[shelf.entries[1].path].mapTo(shelf.scroll.viewport(),
                                                  shelf.cards[shelf.entries[1].path].rect().center())
    QTest.mousePress(overlay, Qt.LeftButton, pos=p0)
    QTest.mouseMove(overlay, p4)
    QTest.qWait(50)
    QTest.mouseMove(overlay, p1)
    QTest.mouseRelease(overlay, Qt.LeftButton, pos=p1)
    QTest.qWait(80)
    assert len(shelf.selected) == 2, shelf.selected
    print('overlay mouse drag-back OK')

    shelf.selected = set()
    shelf._refresh_selection()
    shelf.toggle_paint_mode()
    QTest.qWait(80)
    assert not shelf.overlay.isVisible()
    assert not shelf.selectAllBtn.isVisible() and not shelf.cancelSelectBtn.isVisible()
    print('paint range selection + reverse selection OK')

    # 全选 / 再点取消全选
    shelf.select_all()
    assert len(shelf.selected) == 5
    assert shelf.selectAllBtn.text() == '取消全选', shelf.selectAllBtn.text()
    shelf.select_all()
    assert not shelf.selected and shelf.selectAllBtn.text() == '全选'
    shelf.select_all()
    assert len(shelf.selected) == 5
    print('select all toggle OK')

    # 点击卡片打开（单击即打开，FR-22）
    shelf.selected = set()
    QTest.mouseClick(shelf.cards[MEDIA / 'audio.m4a'], Qt.LeftButton)
    QTest.qWait(300)
    assert page.current_path == MEDIA / 'audio.m4a', page.current_path
    assert shelf.selected == {MEDIA / 'audio.m4a'}
    print('click to open OK')

    # Ctrl+点击 = 切换选择，不打开
    before_path = page.current_path
    QTest.mouseClick(shelf.cards[MEDIA / 'image.jpg'], Qt.LeftButton, Qt.ControlModifier)
    QTest.qWait(150)
    assert page.current_path == before_path
    assert MEDIA / 'image.jpg' in shelf.selected
    print('ctrl+click toggle OK')

    # 重命名（单选内联编辑）——回到资料库页：真实操作只发生在可见卡片上
    window.switchTo(shelf)
    QTest.qWait(300)
    shelf.selected = {MEDIA / 'image.jpg'}
    shelf._refresh_selection()
    rename_card = shelf.cards[MEDIA / 'image.jpg']
    rename_card.start_rename()
    QTest.qWait(80)
    rename_card._edit.setText('renamed_pic')
    rename_card._commit_rename()
    QTest.qWait(400)
    assert (MEDIA / 'renamed_pic.jpg').exists(), '文件未重命名'
    assert not (MEDIA / 'image.jpg').exists()
    assert MEDIA / 'renamed_pic.jpg' in shelf.cards
    print('rename OK')

    # 删除（复用窗口层，跳过确认框）
    targets = [MEDIA / 'audio.wav', MEDIA / 'audio.m4a']
    assert window.delete_paths(targets, confirm=False)
    QTest.qWait(300)
    assert not any(p.exists() for p in targets)
    assert len(shelf.entries) == 3, [e.path.name for e in shelf.entries]
    assert page.current_path in {MEDIA / 'renamed_pic.jpg', MEDIA / 'video.mp4',
                                 MEDIA / 'image.png'} or page.current_path is None
    print('delete (batch) OK, entries left', len(shelf.entries))

    shelf.resize(1100, 700)
    QTest.qWait(150)
    window.switchTo(shelf)
    QTest.qWait(200)
    window.grab().save(str(OUT / 'window_shelf.png'))
    print('SMOKE PHASE5 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
