"""Phase 2 冒烟验收：播放引擎矩阵 + 页面三态 + 快捷键 + 截图。

用法（venv）：  .venv/Scripts/python.exe tools/smoke_phase2.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Feel
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/feel-phase2/appdata'

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from feel.app import FeelWindow  # noqa: E402
from feel.config import cfg  # noqa: E402
from feel.player import MediaEngine  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402

OUT = Path('C:/tmp/scratch/feel-phase2')
MEDIA = OUT / 'media'


def wait_for(predicate, timeout=5000, interval=50):
    elapsed = 0
    while elapsed < timeout:
        if predicate():
            return True
        QTest.qWait(interval)
        elapsed += interval
    return False


def grab_window(window, name: str, dpr: float):
    """Qt 端抓图（窗口内容坐标，可含视频帧；屏幕抓图会被遮挡）。"""
    QTest.qWait(250)
    image = window.grab()
    image.save(str(OUT / f'{name}.png'))
    return image


def main() -> int:
    gen_media(MEDIA)

    app = QApplication(sys.argv)

    # ---- 1) 引擎矩阵：mp4 / wav / m4a 可载、可播、可 seek ----
    engine = MediaEngine()
    for name in ('video.mp4', 'audio.wav', 'audio.m4a'):
        path = MEDIA / name
        engine.load(path)
        assert wait_for(lambda: engine.duration > 0, 4000), f'duration {name}'
        duration = engine.duration
        engine.play()
        assert wait_for(lambda: engine.position > 100, 3000), f'play {name}'
        engine.seek(800)
        assert wait_for(lambda: abs(engine.position - 800) < 300, 2000), (
            f'seek {name} pos={engine.position}'
        )
        engine.stop()
        print(f'engine OK: {name} duration={duration}ms')
    engine.deleteLater()

    # ---- 2) 窗口：三种媒体形态 ----
    window = FeelWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)  # DWM 层 grab 不到
    QTest.qWait(450)

    problems = window.registry.problems()
    print('registry problems:', problems)
    assert not problems, problems

    dpr = window.devicePixelRatioF()
    page = window.playerPage

    # 视频
    page.open_path(MEDIA / 'video.mp4')
    assert wait_for(lambda: page.engine.duration > 0, 5000)
    assert page.stageStack.currentWidget() is page.videoView
    assert page.titleLabel.text() == 'video.mp4'
    assert window.windowTitle() == 'video.mp4', window.windowTitle()
    window_img = grab_window(window, 'window_video', dpr)

    view = page.videoView
    top_left = view.mapTo(window, QPoint(0, 0))
    qt_image = window_img.toImage()
    x0, y0 = int(top_left.x() * dpr), int(top_left.y() * dpr)
    x1 = min(x0 + int(view.width() * dpr), qt_image.width())
    y1 = min(y0 + int(view.height() * dpr), qt_image.height())
    bright = 0
    for yy in range(y0, y1, 8):
        for xx in range(x0, x1, 8):
            color = qt_image.pixelColor(xx, yy)
            if max(color.red(), color.green(), color.blue()) > 150:
                bright += 1
    assert bright > 0, f'视频区域无亮像素 ({x0},{y0})-({x1},{y1})'
    print('video render OK, bright samples =', bright)

    # transport 鼠标点击（不是快捷键）：暂停 / 继续
    page.open_path(MEDIA / 'video.mp4')  # 前面等待可能已播完切走
    assert wait_for(lambda: page.current_path == MEDIA / 'video.mp4'
                    and page.engine.duration > 0, 5000)
    page.set_mode('one')  # 防止 2s 短片在等待中播完自动切走
    page.engine.seek(0); page.engine.play()
    assert wait_for(lambda: page.engine.is_playing, 2500), (
        '视频未进入播放', page.current_kind, page.index, page.current_path,
        page.engine.position, page.engine.duration,
        type(page.stageStack.currentWidget()).__name__)
    QTest.mouseClick(page.playBtn, Qt.LeftButton)
    assert wait_for(lambda: not page.engine.is_playing, 2500), '点击暂停无效'
    QTest.mouseClick(page.playBtn, Qt.LeftButton)
    assert wait_for(lambda: page.engine.is_playing, 2500), '点击播放无效'

    # 点视频画面同样切换播放/暂停
    page.engine.seek(0)
    page.engine.play()
    assert wait_for(lambda: page.engine.is_playing, 2500)
    QTest.mouseClick(page.videoView.viewport(), Qt.LeftButton)
    assert wait_for(lambda: not page.engine.is_playing, 2500), '点视频未暂停'
    QTest.mouseClick(page.videoView.viewport(), Qt.LeftButton)
    assert wait_for(lambda: page.engine.is_playing, 2500), '点视频未继续播放'
    print('video click toggle OK')

    page.set_mode('list')
    print('transport click OK')

    # seek 按钮/快捷键：位置 1500ms 时后退 5s 应夹到 0
    page.engine.seek(1500)
    assert wait_for(lambda: page.engine.position >= 1400, 2000)
    assert window.registry.trigger('seek_back'), 'seek_back 未触发'
    assert wait_for(lambda: page.engine.position < 600, 2000), page.engine.position
    print('seek action OK')

    # 音量：动作 + 按钮同步（步长取设置页）
    page.engine.set_volume(70)
    page.volumeBtn.set_volume(70)
    assert window.registry.trigger('volume_up')
    assert page.engine.volume == 70 + cfg.volumeStep.value, page.engine.volume
    print('volume action OK ->', page.engine.volume)

    # 图片
    page.open_path(MEDIA / 'image.png')
    QTest.qWait(350)
    assert page.stageStack.currentWidget() is page.imageLabel
    assert page.titleLabel.text() == 'image.png'
    assert page.imageLabel.pixmap() is not None and not page.imageLabel.pixmap().isNull()
    # 图片底栏：不摆一排禁用的播放控件，换成 上一张/序号/下一张
    assert not page.seekBar.isVisible() and not page.playBtn.isVisible()
    assert not page.volumeBtn.isVisible() and not page.modeBtn.isVisible()
    assert page.imageInfoLabel.isVisible() and '/ 5' in page.imageInfoLabel.text()
    assert page.prevBtn.isVisible() and page.nextBtn.isVisible()
    grab_window(window, 'window_image', dpr)
    print('image render OK')

    # 音频
    page.open_path(MEDIA / 'audio.wav')
    QTest.qWait(400)
    assert page.stageStack.currentWidget() is page.audioStage
    assert wait_for(lambda: page.engine.duration > 0, 4000)
    assert page.seekBar.totalLabel.text() != '00:00'
    grab_window(window, 'window_audio', dpr)
    print('audio render OK')

    # 上一个 / 下一个（循环）
    total = len(page.entries)
    assert total >= 3, total
    start = page.index
    page.next_file()
    assert page.index == (start + 1) % total
    page.prev_file()
    assert page.index == start
    print('prev/next OK, entries:', [e.path.name for e in page.entries])

    # 上下文门控：资料库页 Space 不应触发播放
    assert window.registry.trigger('play_pause')
    window.switchTo(window.shelfPage)
    QTest.qWait(150)
    assert not window.registry.trigger('play_pause'), 'Space 在资料库页仍可用'
    window.switchTo(window.playerPage)
    QTest.qWait(150)

    # 音量弹层
    page.volumeBtn._show_popup()
    QTest.qWait(150)
    assert page.volumeBtn._popup.isVisible(), '音量弹层未显示'
    assert page.volumeBtn._popup.slider.value() == page.volumeBtn.volume, (
        page.volumeBtn._popup.slider.value(), page.volumeBtn.volume
    )
    page.volumeBtn._popup.hide()
    print('volume popup OK')

    print('SMOKE PHASE2 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
