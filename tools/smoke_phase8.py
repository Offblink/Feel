"""Phase 8 冒烟：悬停帧预览、主题渐变过渡、空态/错误态。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Fell
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/fell-phase8/appdata'

from PySide6.QtCore import QPoint, QEvent, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fell.app import FellWindow  # noqa: E402
from fell.config import cfg  # noqa: E402
from fell.ui.widgets.theme_transition import ThemeTransitionOverlay  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402
from qfluentwidgets import Theme, isDarkTheme  # noqa: E402

OUT = Path('C:/tmp/scratch/fell-phase8')
MEDIA = OUT / 'media'


def wait_for(predicate, timeout=6000, interval=50):
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
    gen_media(MEDIA)

    app = QApplication(sys.argv)
    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)

    page = window.playerPage

    # ---- 视频悬停帧预览 ----
    window.open_path(MEDIA / 'video.mp4')
    assert wait_for(lambda: page.engine.duration > 0, 5000)
    slider = page.seekBar.slider
    slider.resize(600, 28)
    QTest.qWait(200)
    hover_pos = slider.mapToGlobal(QPoint(300, 14))
    slider.hovered.emit(1000, hover_pos)
    assert wait_for(lambda: page.preview.isVisible(), 3000), '预览未显示'
    assert page.preview._image is not None, '视频预览无帧'
    assert not hasattr(page.preview, '_text'), '预览不应再有时间码'
    slider.hoverLeft.emit()
    QTest.qWait(100)
    assert not page.preview.isVisible(), '离开后预览未隐藏'
    print('video hover frame preview OK')

    # ---- 音频悬停：不弹浮层（避免与进度点抢位置） ----
    window.open_path(MEDIA / 'audio.wav')
    assert wait_for(lambda: page.engine.duration > 0, 5000)
    slider.hovered.emit(800, hover_pos)
    QTest.qWait(150)
    assert not page.preview.isVisible(), '音频不该弹帧预览'
    slider.hoverLeft.emit()
    print('audio hover has no popup OK')

    # 进度条只有一个点：悬停不放大手柄（旧版会留白色光圈）
    slider.handle.enterEvent(None)
    assert slider.handle.radius == 5, slider.handle.radius
    slider.handle.leaveEvent(None)
    assert slider.handle.radius == 5, slider.handle.radius
    print('seek handle has no hover halo OK')

    # ---- 主题渐变过渡 ----
    before = cfg.themeMode.value
    assert window.registry.trigger('toggle_theme')
    overlay = window.findChild(ThemeTransitionOverlay)
    assert overlay is not None, '缺少过渡层'
    QTest.qWait(600)
    assert isDarkTheme() == (before != Theme.DARK)
    assert window.findChild(ThemeTransitionOverlay) is None, '过渡层未销毁'
    print('theme gradient transition OK', before, '->', cfg.themeMode.value)

    # 设置页主题控件：图标按钮（不是 Off/On 开关），图标随主题翻转
    window.switchTo(window.settingsPage)
    QTest.qWait(300)
    card = window.settingsPage.themeCard
    from qfluentwidgets import SwitchButton  # noqa: E402
    assert card.findChild(SwitchButton) is None, '主题不该再用 Off/On 开关'
    button = card.themeButton
    assert button.isVisible(), '主题按钮不可见'
    page.engine.pause()  # 音频播放中做全局 QSS 刷新会偶发冻屏（已知限制）
    before_dark = isDarkTheme()
    before_icon = button.icon().cacheKey()
    button.click()
    QTest.qWait(700)
    assert isDarkTheme() != before_dark, '点击主题按钮没有换肤'
    assert button.icon().cacheKey() != before_icon, '主题按钮图标没跟着主题变'
    assert window.findChild(ThemeTransitionOverlay) is None, '过渡层未销毁'
    print('settings theme button OK', before_dark, '->', isDarkTheme())
    # 复位浅色
    if isDarkTheme():
        window.registry.trigger('toggle_theme')
        QTest.qWait(500)

    # ---- 空态：资料库清空 ----
    window.switchTo(window.shelfPage)
    window.shelfPage.set_entries([])
    QTest.qWait(150)
    assert not window.shelfPage.cards
    assert window.shelfPage.emptyLabel.isVisible()
    viewport = window.shelfPage.scroll.viewport()
    assert window.shelfPage.emptyLabel.geometry().width() == viewport.width(), (
        window.shelfPage.emptyLabel.geometry(), viewport
    )
    assert window.shelfPage.emptyLabel.alignment() & Qt.AlignHCenter
    print('empty shelf state OK')

    # ---- 错误态：打开没有媒体的目录 ----
    empty_dir = OUT / 'emptydir'
    empty_dir.mkdir(exist_ok=True)
    (empty_dir / 'note.txt').write_text('no media here')
    entries_before = len(window.playerPage.entries)
    window.open_path(empty_dir / 'note.txt')
    QTest.qWait(300)
    assert len(window.playerPage.entries) == entries_before, '不应改变现有队列'
    from qfluentwidgets import InfoBar
    assert window.findChildren(InfoBar), '缺少错误提示'
    print('error state (no media) OK')

    window.grab().save(str(OUT / 'window_phase8.png'))
    print('SMOKE PHASE8 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
