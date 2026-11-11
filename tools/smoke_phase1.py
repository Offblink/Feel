"""Phase 1 冒烟验收：三页截图 + 设置持久化 + 动作注册表不变量。

用法（venv）：  .venv/Scripts/python.exe tools/smoke_phase1.py
离屏模式：      FELL_OFFSCREEN=1 （无字体，仅验证逻辑）
输出截图：      C:/tmp/scratch/fell-phase1/
"""
import os
import sys
from pathlib import Path

if os.environ.get('FELL_OFFSCREEN') == '1':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Fell
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/fell-phase1/appdata'

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fell.app import FellWindow  # noqa: E402
from fell.config import CONFIG_PATH, FellConfig, cfg  # noqa: E402
from qfluentwidgets import Theme, qconfig  # noqa: E402

OUT = Path('C:/tmp/scratch/fell-phase1')
OUT.mkdir(parents=True, exist_ok=True)


def grab(widget, name: str) -> None:
    path = OUT / f'{name}.png'
    widget.grab().save(str(path))
    print('saved', path)


def main() -> int:
    app = QApplication(sys.argv)
    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)  # Mica 由 DWM 绘制，grab() 抓不到
    app.processEvents()

    # 1) 三页截图（抓整窗：含导航与背景）
    for name, page in (
        ('player', window.playerPage),
        ('shelf', window.shelfPage),
        ('settings', window.settingsPage),
    ):
        window.switchTo(page)
        app.processEvents()
        grab(window, f'window_{name}')

    # 2) 快捷键 ⇄ 控件一一对应
    problems = window.registry.problems()
    print('registry actions:', sorted(window.registry.actions))
    print('registry problems:', problems)
    assert not problems, problems

    # 3) 设置持久化往返
    old_seek = cfg.seekStep.value
    old_volume = cfg.volumeStep.value
    cfg.set(cfg.seekStep, 7)
    cfg.set(cfg.volumeStep, 9)
    cfg.set(cfg.playMode, 'shuffle')
    cfg.save()
    assert CONFIG_PATH.exists(), CONFIG_PATH

    reloaded = FellConfig()
    qconfig.load(CONFIG_PATH, reloaded)
    assert reloaded.seekStep.value == 7, reloaded.seekStep.value
    assert reloaded.volumeStep.value == 9, reloaded.volumeStep.value
    assert reloaded.playMode.value == 'shuffle', reloaded.playMode.value
    print('config roundtrip OK')

    # 恢复原值
    reloaded.set(reloaded.seekStep, old_seek)
    reloaded.set(reloaded.volumeStep, old_volume)
    reloaded.set(reloaded.playMode, 'list')
    reloaded.save()
    qconfig.load(CONFIG_PATH, cfg)

    # 4) 主题切换（Ctrl+T 动作与设置卡片同一路径）
    from qfluentwidgets import isDarkTheme, setTheme

    setTheme(Theme.LIGHT, save=False)
    QTest.qWait(300)
    light_qss = window.settingsPage.seekCard.styleSheet()
    before = cfg.themeMode.value
    assert window.registry.trigger('toggle_theme')
    after = cfg.themeMode.value
    assert after != before, (before, after)
    QTest.qWait(450)  # 等背景渐变动画跑完
    assert isDarkTheme() == (after == Theme.DARK), (after, isDarkTheme())
    dark_qss = window.settingsPage.seekCard.styleSheet()
    assert dark_qss and dark_qss != light_qss, 'QSS 未随主题重刷'
    print('QSS refreshed on theme change OK')
    print('theme toggle OK:', before, '->', after, '| isDarkTheme:', isDarkTheme())
    window.switchTo(window.settingsPage)
    QTest.qWait(450)
    grab(window, 'window_settings_dark')
    cfg.set(cfg.themeMode, before)
    QTest.qWait(450)
    assert isDarkTheme() == (before == Theme.DARK)
    cfg.save()

    # 5) 页面切换动作
    for action_id, page in (
        ('goto_shelf', window.shelfPage),
        ('goto_settings', window.settingsPage),
        ('goto_player', window.playerPage),
    ):
        assert window.registry.trigger(action_id)
        app.processEvents()
        assert window.stackedWidget.currentWidget() is page, action_id
    print('page switch actions OK')

    print('SMOKE PHASE1 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
