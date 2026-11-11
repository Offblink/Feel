"""Phase 4 冒烟：图片/视频缩放、旋转、全屏、图像工具组显隐。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Fell
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/fell-phase4/appdata'

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fell.app import FellWindow  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402

OUT = Path('C:/tmp/scratch/fell-phase4')
MEDIA = OUT / 'media'


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gen_media(MEDIA)

    app = QApplication(sys.argv)
    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)

    page = window.playerPage
    # 旋转已改为跨会话持久化：先清历史状态保证确定性
    window.store.set_rotation(MEDIA / 'image.png', 0)
    window.store.set_rotation(MEDIA / 'video.mp4', 0)

    problems = window.registry.problems()
    print('registry problems:', problems)
    assert not problems, problems

    # ---- 图片 ----
    page.open_path(MEDIA / 'image.png')
    QTest.qWait(300)
    assert page.current_kind == 'image'
    assert page.imageTools.isVisible(), '图像工具组应显示'
    base = page.imageLabel.pixmap().size()
    assert page.zoomLabelBtn.text() == '100%'

    page.zoom_by(1.1)
    QTest.qWait(50)
    assert page.zoomLabelBtn.text() == '110%', page.zoomLabelBtn.text()
    zoomed = page.imageLabel.pixmap().size()
    assert zoomed.width() > base.width(), (zoomed, base)

    page.reset_zoom()
    assert page.imageLabel.pixmap().size() == base

    page.rotate(90)
    QTest.qWait(50)
    rotated = page.imageLabel.pixmap().size()
    assert rotated.width() < rotated.height(), rotated
    assert window.store.get_rotation(MEDIA / 'image.png') == 90
    # 重开同一文件：旋转从 DB 恢复（等价于重启应用后再打开）
    page.open_path(MEDIA / 'image.png')
    QTest.qWait(300)
    assert page._rotation == 90, page._rotation
    assert page.imageLabel.pixmap().width() < page.imageLabel.pixmap().height()
    print('image zoom/rotate OK (persisted)', base, '->', rotated)
    window.grab().save(str(OUT / 'window_image_rotated.png'))

    # 滚轮缩放（事件过滤）
    before = page.imageLabel.pixmap().size()
    viewport_point = QPointF(page.imageLabel.width() / 2, page.imageLabel.height() / 2)
    wheel = QWheelEvent(viewport_point, page.imageLabel.mapToGlobal(viewport_point.toPoint()),
                        QPoint(0, 0), QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                        Qt.ScrollUpdate, False)
    QApplication.sendEvent(page.imageLabel, wheel)
    QTest.qWait(50)
    assert page.imageLabel.pixmap().width() > before.width(), '滚轮未放大'
    page.reset_zoom()
    print('wheel zoom OK')

    # 放大后拖动平移（FR-08）：图大于视口才可拖，边界贴边不露空白
    page.zoom_by(4.0)
    QTest.qWait(50)
    limit_x, limit_y = page.imageLabel.pan_limits()
    assert limit_x > 0 and limit_y > 0, (limit_x, limit_y)
    assert page.imageLabel.cursor().shape() == Qt.OpenHandCursor
    start = QPointF(page.imageLabel.width() / 2, page.imageLabel.height() / 2)
    end = start - QPointF(60, 40)
    for event_type, point, button, buttons in (
        (QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton),
        (QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton),
        (QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton),
    ):
        event = QMouseEvent(event_type, point,
                            page.imageLabel.mapToGlobal(point.toPoint()),
                            button, buttons, Qt.NoModifier)
        QApplication.sendEvent(page.imageLabel, event)
    QTest.qWait(50)
    pan = page.imageLabel.pan
    assert pan.x() < 0 and pan.y() < 0, pan
    page.reset_zoom()
    QTest.qWait(50)
    assert page.imageLabel.pan.x() == 0 and page.imageLabel.pan.y() == 0
    print('image pan OK')

    # 双击全屏 / Esc 退出
    assert not window.isFullScreen()
    QTest.mouseDClick(page.imageLabel, Qt.LeftButton)
    QTest.qWait(250)
    assert window.isFullScreen(), '双击未进入全屏'
    assert page.fullscreenBtn.toolTip().startswith('退出全屏'), page.fullscreenBtn.toolTip()
    assert window.registry.trigger('exit_fullscreen')
    QTest.qWait(250)
    assert not window.isFullScreen(), 'Esc 未退出全屏'
    assert page.fullscreenBtn.toolTip().startswith('全屏'), page.fullscreenBtn.toolTip()
    print('fullscreen toggle OK')

    # 图像工具组折叠
    page.imageToolsToggle.click()
    QTest.qWait(50)
    assert not page.imageToolsInner.isVisible()
    page.imageToolsToggle.click()
    QTest.qWait(50)
    assert page.imageToolsInner.isVisible()
    print('image tools collapse OK')

    # ---- 音频：工具组隐藏、旋转/缩放动作禁用 ----
    page.open_path(MEDIA / 'audio.wav')
    QTest.qWait(300)
    assert page.current_kind == 'audio'
    assert not page.imageTools.isVisible(), '音频页不应显示图像工具'
    assert not window.registry.trigger('rotate_cw')
    assert not window.registry.trigger('zoom_in')
    print('audio hides image tools OK')

    # ---- 视频：旋转/缩放作用到 QGraphicsVideoItem ----
    page.open_path(MEDIA / 'video.mp4')
    QTest.qWait(600)
    assert page.current_kind == 'video'
    assert page.imageTools.isVisible()
    assert window.registry.trigger('rotate_cw')
    assert page.videoItem.rotation() == 90, page.videoItem.rotation()
    assert window.registry.trigger('zoom_in')
    assert abs(page.videoItem.scale() - 1.1) < 1e-6, page.videoItem.scale()
    assert window.registry.trigger('zoom_reset')
    assert abs(page.videoItem.scale() - 1.0) < 1e-6
    assert window.store.get_rotation(MEDIA / 'video.mp4') == 90
    page.open_path(MEDIA / 'video.mp4')
    QTest.qWait(400)
    assert page._rotation == 90 and page.videoItem.rotation() == 90, (
        page._rotation, page.videoItem.rotation()
    )
    window.grab().save(str(OUT / 'window_video_rotated.png'))
    print('video rotate/zoom OK (persisted)')

    print('SMOKE PHASE4 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
