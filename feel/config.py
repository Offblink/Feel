"""Feel 配置与数据目录（SPEC §6）。

配置项全部经 qfluentwidgets QConfig 持久化到 %APPDATA%/Feel/config.json，
主题使用 QConfig 内置的 themeMode（浅色/深色/跟随系统）。
"""
import os
from pathlib import Path

from qfluentwidgets import (
    QConfig,
    ConfigItem,
    RangeConfigItem,
    OptionsConfigItem,
    BoolValidator,
    OptionsValidator,
    RangeValidator,
    qconfig,
)

APP_NAME = 'Feel'

# 播放模式：单曲播放 / 列表循环 / 单曲循环 / 随机播放（SPEC §5.4）
PLAY_MODES = ['once', 'list', 'one', 'shuffle']
PLAY_MODE_TEXTS = {
    'once': '单曲播放',
    'list': '列表循环',
    'one': '单曲循环',
    'shuffle': '随机播放',
}

# 资料库排序（FR-18）：名称自然序 / 修改时间新→旧 / 修改时间旧→新
SORT_MODES = ['name', 'time_desc', 'time_asc']
SORT_MODE_TEXTS = {
    'name': '名称',
    'time_desc': '时间（新→旧）',
    'time_asc': '时间（旧→新）',
}

# 播放速度（FR-02 扩展）
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def app_data_dir() -> Path:
    """%APPDATA%/Feel（不存在则创建）。"""
    root = os.getenv('APPDATA')
    base = Path(root) if root else Path.home() / 'AppData' / 'Roaming'
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_PATH = app_data_dir() / 'config.json'
DB_PATH = app_data_dir() / 'feel.db'
THUMB_DIR = app_data_dir() / 'thumbs'


class FeelConfig(QConfig):
    """Feel 的设置项。"""

    seekStep = RangeConfigItem('Player', 'SeekStepSec', 5, RangeValidator(1, 30))
    volumeStep = RangeConfigItem('Player', 'VolumeStepPct', 5, RangeValidator(1, 25))
    playMode = OptionsConfigItem(
        'Player', 'PlayMode', 'list', OptionsValidator(PLAY_MODES)
    )
    speed = OptionsConfigItem(
        'Player', 'Speed', 1.0, OptionsValidator(SPEEDS)
    )
    sortMode = OptionsConfigItem(
        'Library', 'SortMode', 'name', OptionsValidator(SORT_MODES)
    )
    ocrEnabled = ConfigItem('Library', 'OcrEnabled', True, BoolValidator())
    # 删除不再弹确认框（默认关：误删代价高，用户显式打开才生效）
    directDelete = ConfigItem('Files', 'DirectDelete', False, BoolValidator())
    # 帮助页键帽改出来的自定义快捷键：{action_id: 主快捷键}；没改过的动作不在表里
    customShortcuts = ConfigItem('Shortcuts', 'Custom', {})


cfg = FeelConfig()
# 全局 qconfig 持有 FeelConfig：控件（主题卡片等）直接绑定 cfg 的配置项
qconfig.load(CONFIG_PATH, cfg)
