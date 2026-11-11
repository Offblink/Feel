"""Phase 3 冒烟：四种播放模式 + 自动续播 + 删除到回收站 + 步长实时生效。"""
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 冒烟会改 cfg（播放模式/OCR/排序）与 sqlite：隔离到 scratch，绝不写用户 %APPDATA%/Fell
import os  # noqa: E402
os.environ['APPDATA'] = 'C:/tmp/scratch/fell-phase3/appdata'

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fell.app import FellWindow  # noqa: E402
from fell.config import cfg  # noqa: E402
from fell.queue import PLAY_MODE_ORDER  # noqa: E402
from tools.gen_test_media import main as gen_media  # noqa: E402

OUT = Path('C:/tmp/scratch/fell-phase3')
MEDIA = OUT / 'media'


def wait_for(predicate, timeout=5000, interval=50):
    elapsed = 0
    while elapsed < timeout:
        if predicate():
            return True
        QTest.qWait(interval)
        elapsed += interval
    return False


def main() -> int:
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    gen_media(MEDIA)

    cfg.set(cfg.seekStep, 5)
    cfg.save()

    app = QApplication(sys.argv)
    window = FellWindow()
    window.resize(1180, 780)
    window.show()
    window.setMicaEffectEnabled(False)
    QTest.qWait(400)

    page = window.playerPage
    # 模式语义依赖「video.mp4 的下一个是可播媒体」：先按名称自然序（只在内存改，
    # 不落盘，避免动用户的资料库排序设置；时间排序下顺序随文件 mtime 变）。
    cfg.set(cfg.sortMode, 'name')
    page.open_path(MEDIA / 'video.mp4')
    assert wait_for(lambda: page.engine.duration > 0, 5000)
    assert page.stageStack.currentWidget() is page.videoView
    duration = page.engine.duration
    assert len(page.entries) == 5, [e.path.name for e in page.entries]

    problems = window.registry.problems()
    print('registry problems:', problems)
    assert not problems, problems

    # 单曲循环：播完原地重播
    page.set_mode('one')
    index = page.index
    page.engine.seek(duration - 150)
    assert wait_for(lambda: page.engine.is_playing and page.engine.position < 1200, 6000), (
        f'replay fail pos={page.engine.position} playing={page.engine.is_playing}'
    )
    assert page.index == index, page.index
    print('mode one OK (replay)')

    # 列表循环：播完走下一项
    page.set_mode('list')
    page.engine.seek(page.engine.duration - 150)
    assert wait_for(lambda: page.index != index, 6000), 'list mode did not advance'
    print('mode list OK, index ->', page.index)

    # 单曲播放：播完停止
    page.set_mode('once')
    index = page.index
    page.engine.seek(page.engine.duration - 150)
    assert wait_for(lambda: not page.engine.is_playing, 6000), 'once mode did not stop'
    QTest.qWait(600)
    assert page.index == index, page.index
    assert page.engine.position <= 150, page.engine.position
    assert page.seekBar.currentLabel.text() == '00:00', page.seekBar.currentLabel.text()
    print('mode once OK (stopped, index unchanged)')

    # 随机：播完跳别的项（once 结束后播放器复位为暂停在 0，先恢复播放再逼近结尾）
    page.set_mode('shuffle')
    index = page.index
    page.engine.play()
    QTest.qWait(100)
    page.engine.seek(page.engine.duration - 150)
    assert wait_for(lambda: page.index != index, 6000), 'shuffle did not move'
    print('mode shuffle OK, index', index, '->', page.index)

    # 菜单直选（不弹窗，直接触发 Action）
    page.modeMenuActions[PLAY_MODE_ORDER.index('list')].trigger()
    assert cfg.playMode.value == 'list'
    assert page.modeBtn.text() == '列表循环'
    print('mode menu direct select OK')

    # 删除：当前项进回收站，队列缩减并切到相邻
    before = len(page.entries)
    current = page.entries[page.index].path
    assert page.delete_current(confirm=False)
    assert not current.exists(), current
    assert len(page.entries) == before - 1
    assert page.current_kind is not None
    print('delete to recycle bin OK:', current.name, 'entries left', len(page.entries))

    # 步长实时生效：7 秒步长，从 1500ms 后退应回到 0
    audio_entries = [i for i, e in enumerate(page.entries) if e.kind == 'audio']
    assert audio_entries, 'no audio entry left'
    page.index = audio_entries[0]
    page._show_current()
    assert wait_for(lambda: page.engine.duration > 0, 5000)
    old_step = cfg.seekStep.value
    cfg.set(cfg.seekStep, 7)
    cfg.save()
    page.engine.seek(1500)
    assert wait_for(lambda: page.engine.position >= 1400, 2000)
    assert window.registry.trigger('seek_back')
    assert wait_for(lambda: page.engine.position < 800, 2000), page.engine.position
    assert page.seekBackBtn.text() == '−7s', repr(page.seekBackBtn.text())
    print('live seek step OK (7s), button text synced')
    cfg.set(cfg.seekStep, old_step)
    cfg.save()
    assert page.seekBackBtn.text() == f'−{old_step}s', repr(page.seekBackBtn.text())

    # 空队列态：删掉全部
    while page.entries:
        page.delete_current(confirm=False)
    assert page.index == -1
    assert page.stageStack.currentWidget() is page.emptyStage
    assert page.titleLabel.text() == '未打开文件'
    print('empty stage OK after deleting all')

    window.grab().save(str(OUT / 'window_phase3.png'))
    print('SMOKE PHASE3 OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
