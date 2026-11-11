"""Phase 7 冒烟：收藏 + 书签 + 抽屉 + OCR 静默/续跑。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Fell
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/fell-phase7/appdata'

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fell.app import FellWindow  # noqa: E402
from fell.config import cfg  # noqa: E402
from fell.store import Store  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402

OUT = Path('C:/tmp/scratch/fell-phase7')
MEDIA = OUT / 'media'


def wait_for(predicate, timeout=30000, interval=100):
    elapsed = 0
    while elapsed < timeout:
        if predicate():
            return True
        QTest.qWait(interval)
        elapsed += interval
    return False


def make_text_image(path: Path, text: str) -> None:
    image = Image.new('RGB', (900, 300), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 72)
    draw.text((40, 100), text, fill=(10, 10, 10), font=font)
    image.save(path)


def main() -> int:
    import shutil
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    gen_media(MEDIA)
    make_text_image(MEDIA / 'scan_a.png', 'FELL SCAN A')

    app = QApplication(sys.argv)
    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)

    page = window.playerPage
    shelf = window.shelfPage

    # 用户可能在设置里关掉了 OCR；本阶段要验证 OCR 续跑，内存里先强制打开
    cfg.set(cfg.ocrEnabled, True)

    window.open_path(MEDIA / 'video.mp4')
    QTest.qWait(500)
    assert page.current_kind == 'video'

    # 清掉历史运行残留（DB 跨次运行持久）
    video_path = MEDIA / 'video.mp4'
    window.store.set_favorite(video_path, False)
    for bid, _, _ in window.store.bookmarks(video_path):
        window.store.delete_bookmark(bid)

    problems = window.registry.problems()
    print('registry problems:', problems)
    assert not problems, problems

    # OCR 静默：没有进度条控件
    assert not hasattr(shelf, 'ocrBar'), 'OCR 不应暴露进度 UI'
    print('ocr silent (no progress UI)')

    # 收藏（带 InfoBar 提示）
    from qfluentwidgets import InfoBar
    assert window.registry.trigger('favorite')
    assert window.store.is_favorite(video_path)
    QTest.qWait(250)
    assert any('已收藏' in bar.titleLabel.text()
               for bar in window.findChildren(InfoBar)), '收藏缺少提示'
    window.switchTo(shelf)
    QTest.qWait(200)
    assert shelf.cards[video_path].favorite
    shelf._on_category('favorite')
    QTest.qWait(150)
    assert list(shelf.cards) == [video_path], list(shelf.cards)
    shelf._on_category('all')
    QTest.qWait(150)
    # 卡片心形点击取消收藏
    card = shelf.cards[video_path]
    QTest.mouseClick(card, Qt.LeftButton, pos=QPoint(card.width() - 19, 19))
    QTest.qWait(200)
    assert not window.store.is_favorite(video_path)
    print('favorite toggle OK (player + card + filter)')

    window.switchTo(page)
    QTest.qWait(150)

    # 书签
    assert wait_for(lambda: page.engine.duration > 0, 5000)
    page.engine.seek(800)
    assert wait_for(lambda: page.engine.position >= 700, 2000)
    page.engine.pause()  # 防止 2s 视频自动续播切走当前文件
    # 书签输入框：点 B 弹出右侧输入框，取消不落库，保存才写入 时间 + 内容
    position_before = page.engine.position
    assert window.registry.trigger('bookmark_add')
    QTest.qWait(150)
    popup = page.bookmarkPopup
    assert popup.isVisible(), '书签输入框未弹出'
    assert popup.x() > page.width() / 2, '书签输入框应贴在播放页右侧'
    assert popup.position_ms == position_before, (popup.position_ms, position_before)
    popup.edit.setText('放弃这次')
    popup.cancelBtn.click()
    QTest.qWait(150)
    assert not popup.isVisible()
    assert not window.store.bookmarks(video_path), '取消不该写入书签'

    page.add_bookmark()
    QTest.qWait(150)
    popup.edit.setText('副歌开始')
    popup.saveBtn.click()
    QTest.qWait(150)
    assert not popup.isVisible()
    marks = page.seekBar.slider._marks
    assert marks, '进度条无书签刻度'
    bookmark_rows = window.store.bookmarks(video_path)
    assert len(bookmark_rows) == 1, bookmark_rows
    bookmark_id, pos_ms, label = bookmark_rows[0]
    assert label == '副歌开始', bookmark_rows
    assert abs(pos_ms - position_before) < 400, (pos_ms, position_before)
    # 抽屉里能看到书签并跳转
    assert window.registry.trigger('drawer_toggle')
    QTest.qWait(350)
    assert page.drawer.isVisible()
    page.drawer.tabs.setCurrentItem('bookmarks')
    QTest.qWait(100)
    assert page.drawer.bookmarks.count() == 1, page.drawer.bookmarks.count()
    assert '副歌开始' in page.drawer.bookmarks.item(0).text(), \
        page.drawer.bookmarks.item(0).text()
    page.engine.seek(0)
    QTest.qWait(200)
    item = page.drawer.bookmarks.item(0)
    page.drawer.bookmarks.itemClicked.emit(item)
    QTest.qWait(300)
    assert page.engine.position > 500, page.engine.position
    print('bookmark add + marker + drawer jump OK')

    # 播放列表 tab 跳转
    page.drawer.tabs.setCurrentItem('playlist')
    QTest.qWait(100)
    assert page.drawer.playlist.count() == len(page.entries)
    # 列表文字按主题显式着色（不能靠 current 项配色：浅色主题会被刷白）
    row_color = page.drawer.playlist.item(0).foreground().color()
    assert row_color.lightness() < 100, row_color.name()
    window.toggle_theme()
    QTest.qWait(900)
    dark_color = page.drawer.playlist.item(0).foreground().color()
    assert dark_color.lightness() > 150, dark_color.name()
    window.toggle_theme()
    QTest.qWait(900)
    print('drawer list text follows theme OK')
    target_row = 0 if page.index != 0 else 1
    page.drawer.playlist.itemClicked.emit(page.drawer.playlist.item(target_row))
    QTest.qWait(400)
    assert page.index == target_row
    print('drawer playlist jump OK')

    # 信息 tab
    page.drawer.tabs.setCurrentItem('info')
    QTest.qWait(100)
    assert page.drawer.infoLayout.count() > 0
    window.grab().save(str(OUT / 'window_drawer.png'))
    page.drawer.hide_drawer()
    QTest.qWait(300)

    # 删除书签
    page._delete_bookmark(bookmark_id)
    assert not page.seekBar.slider._marks
    assert not window.store.bookmarks(video_path)
    print('bookmark delete OK')

    # 持久化：新 Store 读同一 DB
    fresh = Store()
    assert fresh.is_favorite(video_path) is False  # 上面已取消
    fresh.add_bookmark(video_path, 1500)
    assert fresh.bookmarks(video_path)
    fresh.close()
    print('store persistence OK')

    # OCR 续跑：删掉一条缓存模拟中断，重开目录补跑
    window.open_path(MEDIA / 'scan_a.png')
    assert wait_for(lambda: not window.ocr.is_running, 90000)
    QTest.qWait(300)
    assert 'FELL' in shelf.ocr_texts.get(MEDIA / 'scan_a.png', '').upper()
    window.store.delete_ocr(MEDIA / 'scan_a.png')
    shelf.ocr_texts.pop(MEDIA / 'scan_a.png', None)
    window._ocr_signature = None  # 模拟进程重启（新会话签名清空）
    window.open_path(MEDIA / 'scan_a.png')  # 重开同目录 → 续跑
    assert wait_for(lambda: not window.ocr.is_running, 90000)
    QTest.qWait(400)
    assert 'FELL' in shelf.ocr_texts.get(MEDIA / 'scan_a.png', '').upper(), 'OCR 未续跑'
    print('ocr resume after simulated interruption OK')

    print('SMOKE PHASE7 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
