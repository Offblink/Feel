"""Phase 10 冒烟：主题图标按钮、启动空态、播放页标题就地改名、直接删除开关。

配置与数据库都写到 C:/tmp/scratch/feel-phase10/appdata，不碰用户真实 cfg/feel.db。
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path('C:/tmp/scratch/feel-phase10')
MEDIA = OUT / 'media'

# 必须在 import feel.* 之前：config.py 在导入时就算出 CONFIG_PATH/DB_PATH
os.environ['APPDATA'] = str(OUT / 'appdata')

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from qfluentwidgets import SwitchButton, isDarkTheme  # noqa: E402

import feel.app as app_module  # noqa: E402
from feel.app import FeelWindow  # noqa: E402
from feel.config import cfg  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402


class _FakeButton:
    def setText(self, *_args) -> None:
        pass


class _FakeBox:
    """记录确认框是否被构造；exec() 返回 False = 用户点了取消。"""

    calls: list[str] = []

    def __init__(self, *_args, **_kwargs):
        _FakeBox.calls.append('box')
        self.yesButton = _FakeButton()
        self.cancelButton = _FakeButton()

    def exec(self) -> bool:
        return False


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    gen_media(MEDIA)

    app = QApplication(sys.argv)
    cfg.set(cfg.ocrEnabled, False)
    cfg.set(cfg.sortMode, 'name')
    cfg.set(cfg.directDelete, False)
    cfg.save()

    window = FeelWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)
    shelf = window.shelfPage
    page = window.playerPage

    # ---- 1) 启动未打开文件：播放页/资料库空态文案都在 ----
    assert page.stageStack.currentWidget() is page.emptyStage, '播放页没停在空态'
    assert page.emptyLabel.isVisible(), '播放页空态文案不可见'
    window.grab().save(str(OUT / 'empty_player.png'))
    window.switchTo(shelf)
    QTest.qWait(300)
    assert not page.entries, '启动时不该有队列'
    assert shelf.emptyLabel.isVisible(), '启动时资料库空态文案不可见'
    viewport = shelf.scroll.viewport()
    assert shelf.emptyLabel.geometry().size() == viewport.size(), (
        shelf.emptyLabel.geometry(), viewport.size()
    )
    assert '同目录' in shelf.emptyLabel.text(), shelf.emptyLabel.text()
    window.grab().save(str(OUT / 'empty_shelf.png'))
    print('startup shelf empty state OK')

    # ---- 2) 设置页主题控件：图标按钮，不是 Off/On 开关 ----
    window.switchTo(window.settingsPage)
    QTest.qWait(300)
    card = window.settingsPage.themeCard
    assert card.findChild(SwitchButton) is None, '主题不该再用 Off/On 开关'
    assert card.themeButton.isVisible(), '主题按钮不可见'
    before_dark = isDarkTheme()
    before_icon = card.themeButton.icon().cacheKey()
    card.themeButton.click()
    QTest.qWait(700)
    assert isDarkTheme() != before_dark, '点击主题按钮没有换肤'
    assert card.themeButton.icon().cacheKey() != before_icon, '主题按钮图标没随主题更新'
    window.grab().save(str(OUT / 'settings.png'))
    print('theme icon button OK', before_dark, '->', isDarkTheme())

    # ---- 3) 播放页标题：点击变输入框，Enter 真的改磁盘文件名 ----
    window.open_path(MEDIA / 'image.png')
    QTest.qWait(500)
    assert page.current_path is not None and page.current_path.name == 'image.png'
    # 资料库在后台时延后建卡，空态文案要到切过去建完卡才收起
    window.switchTo(shelf)
    QTest.qWait(300)
    assert shelf.emptyLabel.isHidden(), '有卡片后资料库空态文案还挂着'
    window.switchTo(page)
    QTest.qWait(200)
    old = page.current_path
    window.store.set_favorite(old, True)
    window.store.set_rotation(old, 90)

    QTest.mouseClick(page.titleLabel, Qt.LeftButton)
    QTest.qWait(100)
    assert page.titleEdit.isVisible(), '点击标题没有出现输入框'
    assert not page.titleLabel.isVisible()
    assert page.titleEdit.text() == 'image', page.titleEdit.text()
    assert page.titleEdit.hasFocus(), '输入框没拿到焦点'

    # Esc 取消：文件不变、输入框收起
    page.titleEdit.setText('should_not_apply')
    QTest.keyClick(page.titleEdit, Qt.Key_Escape)
    QTest.qWait(150)
    assert not page.titleEdit.isVisible(), 'Esc 没能收起输入框'
    assert page.titleLabel.isVisible()
    assert (MEDIA / 'image.png').exists(), 'Esc 后不该改名'
    print('title rename cancel OK')

    # 真改名：Enter 提交
    QTest.mouseClick(page.titleLabel, Qt.LeftButton)
    QTest.qWait(100)
    page.titleEdit.setText('renamed')
    QTest.keyClick(page.titleEdit, Qt.Key_Return)
    QTest.qWait(700)
    new = MEDIA / 'renamed.png'
    assert new.exists() and not old.exists(), '磁盘文件没有被改名'
    assert page.current_path == new, page.current_path
    assert page.titleLabel.text() == 'renamed.png', page.titleLabel.text()
    assert window.windowTitle() == 'renamed.png', window.windowTitle()
    assert window.store.is_favorite(new) and not window.store.is_favorite(old), (
        '收藏没有随改名迁移'
    )
    assert window.store.get_rotation(new) == 90, '旋转没有随改名迁移'
    assert any(entry.path == new for entry in page.entries), '队列里还是旧路径'
    print('title rename commit OK')

    # ---- 4) 正在播放的视频改名：先释放句柄再 os.rename ----
    window.open_path(MEDIA / 'video.mp4')
    QTest.qWait(700)
    video = MEDIA / 'video.mp4'
    assert page.current_path == video, page.current_path
    QTest.mouseClick(page.titleLabel, Qt.LeftButton)
    QTest.qWait(100)
    page.titleEdit.setText('clip')
    QTest.keyClick(page.titleEdit, Qt.Key_Return)
    QTest.qWait(800)
    clip = MEDIA / 'clip.mp4'
    assert clip.exists() and not video.exists(), '播放中的视频改名失败（句柄未释放）'
    assert page.current_path == clip, page.current_path
    print('rename while playing OK')

    # ---- 4.5) 音量 OSD：画面中央半透明提示，约 1 秒后自动消失 ----
    page.engine.set_volume(50)
    page.volumeBtn.set_volume(50)
    QTest.keyClick(window, Qt.Key_Up)
    QTest.qWait(250)
    level = 50 + cfg.volumeStep.value
    assert page.engine.volume == level, page.engine.volume
    assert page.volumeOsd.isVisible(), '↑ 调音量没有画中提示'
    assert page.volumeOsd.testAttribute(Qt.WA_TransparentForMouseEvents), 'OSD 会挡住点击'
    stage_center = page.stageStack.geometry().center()
    osd_center = page.volumeOsd.geometry().center()
    assert abs(osd_center.x() - stage_center.x()) <= 1, (osd_center, stage_center)
    assert abs(osd_center.y() - stage_center.y()) <= 1, (osd_center, stage_center)
    window.grab().save(str(OUT / 'volume_osd.png'))
    QTest.qWait(1300)
    assert not page.volumeOsd.isVisible(), '画中提示没有自动消失'
    print('volume OSD OK')

    # ---- 5) 设置页「直接删除」：默认关；关=弹确认，开=不弹直接进回收站 ----
    cfg.set(cfg.directDelete, False)
    assert window.settingsPage.deleteCard.switchButton.isChecked() is False
    real_box = app_module.MessageBox
    app_module.MessageBox = _FakeBox
    _FakeBox.calls.clear()
    try:
        target = MEDIA / 'delete_me.png'
        shutil.copy(MEDIA / 'renamed.png', target)

        # 默认（关）：确认框出现；这里模拟取消 → 文件保留
        assert window.delete_paths([target]) is False
        assert _FakeBox.calls == ['box'], '默认关时应该弹确认框'
        assert target.exists(), '取消后不该删除'

        # 打开「直接删除」：不弹确认，直接进回收站
        cfg.set(cfg.directDelete, True)
        assert window.settingsPage.deleteCard.switchButton.isChecked() is True
        log_path = page.current_path
        page.engine.pause()
        assert window.delete_paths([target]) is True, '开启后应删除成功'
        assert _FakeBox.calls == ['box'], '开启直接删除后不该再弹确认框'
        assert not target.exists(), '文件还在'
        assert page.current_path == log_path, '删的不是当前文件，当前项不该变'
    finally:
        app_module.MessageBox = real_box
        cfg.set(cfg.directDelete, False)
    print('direct delete switch OK')

    # 设置页「文件」组截图（直接删除卡片在底部）
    window.switchTo(window.settingsPage)
    QTest.qWait(300)
    bar = window.settingsPage.verticalScrollBar()
    bar.setValue(bar.maximum())
    QTest.qWait(300)
    assert window.settingsPage.deleteCard.isVisible(), '「直接删除」卡片不可见'
    window.grab().save(str(OUT / 'settings_files.png'))

    window.grab().save(str(OUT / 'window_phase10.png'))
    print('SMOKE PHASE10 OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
