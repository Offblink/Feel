"""Phase 14 冒烟：进度条点击/悬停、音量点击静音、长按 ←/→ 临时倍速。

配置与数据库都写到 C:/tmp/scratch/feel-phase14/appdata，不碰用户真实 cfg/feel.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/feel-phase14')
MEDIA = OUT / 'media'

# 必须在 import feel.* 之前：config.py 在导入时就算出 CONFIG_PATH/DB_PATH
os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from feel.app import FeelWindow  # noqa: E402
from feel.config import cfg  # noqa: E402
from tools.gen_test_media import make_video  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402


def wait_position(page, target: int, timeout: int = 1500) -> bool:
    step = 50
    waited = 0
    while waited < timeout:
        if abs(page.engine.position - target) < 700:
            return True
        QTest.qWait(step)
        waited += step
    return False


def slider_x(slider, ratio: float) -> int:
    """比例位置 → 滑条本地 x（与 _x_to_ms 同一套 HANDLE_MARGIN）。"""
    margin = 11
    return int(margin + (slider.width() - 2 * margin) * ratio)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    gen_media(MEDIA)
    # 20s 视频：够验证「30s 处点 15s」这类回跳 + 长按倍速
    make_video(MEDIA / 'video_long.mp4', seconds=20.0)

    app = QApplication(sys.argv)
    cfg.set(cfg.ocrEnabled, False)
    cfg.set(cfg.sortMode, 'name')
    cfg.set(cfg.customShortcuts, {})
    cfg.set(cfg.speed, 1.0)
    cfg.set(cfg.seekStep, 5)
    cfg.save()

    window = FeelWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    window.activateWindow()
    window.raise_()
    QTest.qWait(500)
    page = window.playerPage
    slider = page.seekBar.slider

    # ---- 1) 长视频进度条：悬停不跳 / 点击必跳 ----
    window.open_path(MEDIA / 'video_long.mp4')
    QTest.qWait(1200)
    assert page.current_kind == 'video', page.current_kind
    assert page.engine.duration > 15000, page.engine.duration
    page.engine.pause()
    page.engine.seek(8000)
    assert wait_position(page, 8000), page.engine.position
    QTest.qWait(900)
    assert abs(slider.value() - 8000) < 900, slider.value()
    print('seek to 8s OK, duration', page.engine.duration)

    # 悬停：鼠标划过 90% 处，进度点不许自己跳过去（历史 bug）
    before = slider.value()
    before_x = slider.handle.x()
    hover_x = slider_x(slider, 0.90)
    hovered = []
    slider.hovered.connect(lambda ms, pos: hovered.append(ms))
    # QTest.mouseMove 走真实光标，headless 下不可靠：直接送一条无按键的
    # QMouseEvent（就是 slider 的 mouseMoveEvent 在悬停时收到的那个）
    hover_ev = QMouseEvent(
        QEvent.MouseMove, QPointF(hover_x, 14),
        QPointF(slider.mapToGlobal(QPoint(hover_x, 14))),
        Qt.NoButton, Qt.NoButton, Qt.NoModifier,
    )
    QApplication.sendEvent(slider, hover_ev)
    QTest.qWait(200)
    assert slider.value() == before, (before, slider.value())
    assert slider.handle.x() == before_x, (before_x, slider.handle.x())
    assert hovered and hovered[-1] > 15000, hovered[-1:]
    QApplication.sendEvent(slider, QEvent(QEvent.Leave))
    print('hover keeps dot at playback position OK')

    # 点击 25% 处：按下即定位、松开必 seek
    target_ratio = 0.25
    target = int(page.engine.duration * target_ratio)
    x = slider_x(slider, target_ratio)
    QTest.mousePress(slider, Qt.LeftButton, Qt.NoModifier, QPoint(x, 14))
    QTest.qWait(60)
    pressed_value = slider.value()
    QTest.mouseRelease(slider, Qt.LeftButton, Qt.NoModifier, QPoint(x, 14))
    assert abs(pressed_value - target) < 900, (target, pressed_value)
    # 松开瞬间进度点必须停在目标处（不能被落后一拍的位置回弹拉回去）
    assert abs(slider.value() - target) < 900, (target, slider.value())
    assert wait_position(page, target, timeout=1800), (target, page.engine.position)
    QTest.qWait(300)
    assert abs(slider.value() - target) < 900, (target, slider.value())
    print('click seek OK:', target, '->', page.engine.position)

    # 播放中从靠后位置点回靠前位置（用户报的关键场景）
    page.engine.play()
    page.engine.seek(16000)
    assert wait_position(page, 16000), page.engine.position
    QTest.qWait(500)
    back_target = int(page.engine.duration * 0.25)
    x = slider_x(slider, 0.25)
    QTest.mouseClick(slider, Qt.LeftButton, Qt.NoModifier, QPoint(x, 14))
    QTest.qWait(50)
    assert abs(slider.value() - back_target) < 900, (back_target, slider.value())
    assert wait_position(page, back_target, timeout=2000), page.engine.position
    QTest.qWait(400)
    assert slider.value() < back_target + 1200, slider.value()
    print('seek back while playing OK:', page.engine.position)

    # 拖动：按下 60% 拖到 20%，松开 seek 到 20%
    drag_from = slider_x(slider, 0.60)
    drag_to = slider_x(slider, 0.20)
    QTest.mousePress(slider, Qt.LeftButton, Qt.NoModifier, QPoint(drag_from, 14))
    QTest.mouseMove(slider, QPoint(drag_to, 14))
    QTest.qWait(50)
    dragged_value = slider.value()
    QTest.mouseRelease(slider, Qt.LeftButton, Qt.NoModifier, QPoint(drag_to, 14))
    assert abs(dragged_value - page.engine.duration * 0.20) < 1200, dragged_value
    assert wait_position(page, dragged_value, timeout=1800), page.engine.position
    print('drag seek OK:', dragged_value)
    page.engine.pause()

    # ---- 2) 音量按钮点击 = 静音 / 取消静音 ----
    page.engine.seek(2000)
    assert wait_position(page, 2000), page.engine.position
    volume = page.volumeBtn.volume
    assert volume > 0, volume
    QTest.mouseClick(page.volumeBtn._button, Qt.LeftButton)
    QTest.qWait(100)
    assert page.volumeBtn.muted and page.engine.is_muted, '点击音量钮没有静音'
    assert page.volumeOsd._muted and page.volumeOsd.isVisible(), '静音没有 OSD'
    assert '已静音' in page.volumeBtn._button.toolTip(), page.volumeBtn._button.toolTip()
    QTest.mouseClick(page.volumeBtn._button, Qt.LeftButton)
    QTest.qWait(100)
    assert not page.volumeBtn.muted and not page.engine.is_muted, '再点没有取消静音'
    assert page.volumeBtn.volume == volume, '取消静音后音量丢了'
    assert '点击静音' in page.volumeBtn._button.toolTip(), page.volumeBtn._button.toolTip()
    print('click volume mute/unmute OK')

    # 静音后调音量/按 ↑ 会自动取消静音
    QTest.mouseClick(page.volumeBtn._button, Qt.LeftButton)
    QTest.qWait(80)
    page.step_volume(5)
    assert not page.volumeBtn.muted and not page.engine.is_muted, '调音量没解除静音'
    print('volume step unmutes OK')

    # ---- 3) 长按 ←/→ 临时 0.5× / 2× ----
    assert not window.registry._shortcuts['seek_back'][0].autoRepeat(), \
        'seek 快捷键必须关掉自动重复'
    page.engine.play()
    page.engine.seek(6000)
    assert wait_position(page, 6000), page.engine.position
    QTest.qWait(300)

    # 长按 →：超过阈值后 2×，且不触发快进 seek
    pos_before = page.engine.position
    QTest.keyPress(window, Qt.Key_Right)
    QTest.qWait(page.SEEK_HOLD_MS + 260)
    assert abs(page.engine.playback_rate - 2.0) < 0.01, page.engine.playback_rate
    assert page.speedBtn.text() == '2×', page.speedBtn.text()
    QTest.qWait(350)
    pos_held = page.engine.position
    QTest.keyRelease(window, Qt.Key_Right)
    QTest.qWait(120)
    assert abs(page.engine.playback_rate - 1.0) < 0.01, page.engine.playback_rate
    assert page.speedBtn.text() == '1×', page.speedBtn.text()
    # 按住期间只按 2× 往前走，不准额外 +5s 跳
    assert pos_held > pos_before + 500, (pos_before, pos_held)
    assert pos_held < pos_before + 9000, f'长按被当成了快进：{pos_before} -> {pos_held}'
    print('long-press right = 2x OK:', pos_before, '->', pos_held)

    # 长按 ←：0.5×
    QTest.keyPress(window, Qt.Key_Left)
    QTest.qWait(page.SEEK_HOLD_MS + 260)
    assert abs(page.engine.playback_rate - 0.5) < 0.01, page.engine.playback_rate
    assert page.speedBtn.text() == '0.5×', page.speedBtn.text()
    QTest.keyRelease(window, Qt.Key_Left)
    QTest.qWait(120)
    assert abs(page.engine.playback_rate - 1.0) < 0.01, page.engine.playback_rate
    print('long-press left = 0.5x OK')

    # 短按仍是 ±N 秒 seek，倍速不变
    page.engine.pause()
    assert wait_position(page, page.engine.position), page.engine.position
    pos = page.engine.position
    QTest.keyPress(window, Qt.Key_Right)
    QTest.qWait(60)
    QTest.keyRelease(window, Qt.Key_Right)
    QTest.qWait(400)
    assert abs(page.engine.playback_rate - 1.0) < 0.01, '短按不该改倍速'
    assert page.engine.position > pos + 3000, (pos, page.engine.position)
    print('short press still seeks OK:', pos, '->', page.engine.position)

    # ---- 4) 双击视频 = 全屏，且不改变播放状态 ----
    page.engine.play()
    QTest.qWait(300)
    assert page.engine.is_playing, '双击测试前视频应在播放'
    assert not window.isFullScreen()
    QTest.mouseDClick(page.videoView.viewport(), Qt.LeftButton)
    QTest.qWait(250)
    assert window.isFullScreen(), '双击没有进全屏'
    assert page.engine.is_playing, '双击全屏把视频暂停了'
    # 再等过长于双击间隔，确认待兑现的单击已被取消
    QTest.qWait(max(600, QApplication.doubleClickInterval() + 200))
    assert page.engine.is_playing, '双击后单击回调仍然把视频暂停了'
    assert window.registry.trigger('exit_fullscreen')
    QTest.qWait(300)
    assert not window.isFullScreen()

    # 单击仍然切换播放/暂停（只是延后到双击间隔）
    page.engine.play()
    QTest.qWait(200)
    QTest.mouseClick(page.videoView.viewport(), Qt.LeftButton)
    QTest.qWait(QApplication.doubleClickInterval() + 250)
    assert not page.engine.is_playing, '单击视频没有暂停'
    QTest.mouseClick(page.videoView.viewport(), Qt.LeftButton)
    QTest.qWait(QApplication.doubleClickInterval() + 250)
    assert page.engine.is_playing, '再次单击没有继续播放'
    print('double-click fullscreen keeps playback OK')

    window.grab().save(str(OUT / 'player.png'))
    print('phase14 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
