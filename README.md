# Feel

本地音视频 / 图片查看器（PySide6 + PySide6-Fluent-Widgets）。打开一个文件，自动加载同目录的
图片 / 音频 / 视频，支持播放（含倍速）、缩放旋转与放大拖动、名称/时间排序、shelf 卡片墙、
OCR 图片搜索、收藏与书签；内置**帮助页**（Ctrl+4）按场景列全部快捷键。

规格：[SPEC.md](SPEC.md)。所有功能动作都同时具备快捷键与可视化控件（结构上由 `ActionRegistry`
保证一一对应），界面采用折叠式布局（导航 / 抽屉 / 悬停弹层 / 上下文工具组）。

## 运行

本机全局 Python 已带 PySide6 / cv2 / PyAV / rapidocr / Pillow，venv 用 `--system-site-packages`
复用，仅装 fluent 组件：

双击 `run.bat` 即可启动（自动使用 `.venv` 的 pythonw，无控制台窗口）。

也可以带文件/目录启动，或作为 Windows「打开方式」的目标：

```bat
run.bat "D:\照片\a.jpg"
run.bat "D:\照片"            :: 目录 → 打开按当前排序的第一项
```

`run.bat` 会把参数原样转发给 `main.py`（`FEEL_LAUNCH_DIR` 保留你调用时的目录，
相对路径按它解析）。

手动安装：

```bash
python -m venv --system-site-packages .venv
# 本机 ensurepip 的 bundled wheel 缺失，若 venv 报 ensurepip 错误：
#   python -m venv --system-site-packages --without-pip .venv
#   然后用系统 pip 往 venv 装： python -m pip install --no-index --find-links <wheel目录> pyside6_fluent_widgets
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe main.py
```

数据目录：`%APPDATA%/Feel/`
- `config.json`：设置（快进秒数、音量步长、播放模式、倍速、资料库排序、主题、图片搜索开关、直接删除开关）
- `feel.db`：OCR 缓存、收藏、书签
- `thumbs/`：缩略图缓存（设置页可清）
- `logs/feel.log`：运行日志（1 MiB × 3 轮转；设置页「日志」可打开文件或目录）

## 打包（Windows）

```bash
.venv/Scripts/python.exe -m pip install -r requirements-build.txt   # 仅首次
build.bat
```

- 用 PyInstaller 6.x + `feel.spec` 构建 **onedir** 产物：`dist/Feel/Feel.exe`，整个 `dist/Feel/` 目录压缩即可分发。
- `feel.spec` 会收齐 qfluentwidgets / qframelesswindow / rapidocr（含模型）/ onnxruntime / av / cv2，
  并排除 transformers、torch 等运行时不用的大家伙。
- OCR 跑在子进程里，`main.py` 已调用 `multiprocessing.freeze_support()`；打包后子进程以 `Feel.exe` 自身拉起。
- exe 的设置、数据库、日志仍写在 `%APPDATA%/Feel/`，与源码运行共用。

## 快捷键（与界面控件一一对应）

| 快捷键 | 动作 | 界面控件 |
|---|---|---|
| Ctrl+O | 打开文件 | 文件夹按钮（播放页顶栏） |
| Ctrl+Shift+O | 打开文件夹 | 「打开文件夹」按钮（资料库顶栏） |
| Space / 点视频画面 | 播放/暂停 | ▶/⏸ 主按钮（画面本身也可点；双击画面=全屏） |
| ← / → | 后退/前进 N 秒 | `−Ns` / `+Ns` 按钮（N 可在设置页改） |
| Ctrl+← / Ctrl+→ | 上一个/下一个 | ⏮ / ⏭ 按钮 |
| ↑ / ↓ | 音量 ±V% | 音量按钮或悬停弹层上滚轮均可；画面中央闪现半透明音量提示 |
| M | 播放模式切换 | 模式按钮（箭头直选四种模式） |
| ] / [ | 播放倍速 ±档（0.5×–2×） | 倍速按钮（点击弹出档位菜单；换文件保持） |
| E | 收藏/取消 | ♥ 按钮（实心=已收藏；播放页 + shelf 卡片，点击有提示） |
| B | 添加书签 | 书签按钮（记录图标；右侧弹出输入框，输入内容后保存） |
| I | 详情抽屉 | 右上角菜单按钮（播放列表/书签/文件信息） |
| Ctrl+L / Ctrl+R | 逆/顺时针旋转 90° | ⟲ / ⟳ 按钮（仅图片/视频） |
| 滚轮 / `=` / `-` | 缩放 | `+` / `−` 按钮 + 百分比 |
| 放大后按住左键拖动 | 平移图片显示区域 | 图片本身（直接操纵，边界贴边） |
| Ctrl+0 | 缩放重置 | `100%` 按钮 |
| Del | 删除（回收站） | 🗑 按钮（播放页顶栏 / 卡片悬停删除 / 选择模式删除；默认带确认，设置页「直接删除」可关） |
| — | 单曲播放播完 | 自动回到 0:00 并暂停（不停在黑屏） |
| F / 双击画面 | 全屏 | ⛶ 按钮 |
| Esc | 退出全屏 | —（全屏时生效） |
| Ctrl+1/2/3/4 | 切页（播放/资料库/设置/帮助） | 左侧导航 |
| Ctrl+A | 全选 | 全选按钮（资料库，选择模式下显示） |
| Enter | 打开选中 | 双击卡片 |
| F2 | 重命名（单选） | 卡片悬停左上角铅笔按钮；播放页点击标题也能就地改名（Enter 提交 / Esc 取消 / 点别处收起） |
| Ctrl+F | 聚焦搜索 | 搜索框 |
| F5 | 刷新资料库（重扫目录 + 强制 OCR） | 刷新按钮 |
| Ctrl+T | 深浅主题（径向渐变过渡） | 设置页主题图标按钮（☀ 浅色 / ☾ 深色） |

## 资料库（shelf）

- 类别 chips：全部 / 图片 / 视频 / 音频 / 收藏；扩展名下拉细分；**排序下拉**（名称自然序 / 时间新→旧 / 时间旧→新），
  排序结果与播放队列共用，改排序时当前文件不变；
- **筛选决定播放队列**：选中「视频」后点任意卡片，播放列表就只有视频；扩展名、收藏、图片搜索同理，
  排序决定队列顺序。上一/下一与抽屉播放列表都只在筛选结果里走，卡片墙仍展示整个目录。
- 卡片：图片/视频缩略图（视频取 10% 或 1s 处一帧），音频固定音符占位图；
  卡片宽度随窗口均分（列数动态、行内不留右侧空白，缩放窗口实时重排）；
- 顶栏：「打开文件夹」（Ctrl+Shift+O，只把目录加载进资料库与队列，**不跳页、不自动播放**，点卡片才打开）/「刷新」/「选择」；刷新重扫当前目录并强制重跑 OCR；
  选择进入涂抹多选模式，此时才出现「已选 N / 全选 / 删除 / 取消」；
- 涂抹多选（二维网格按一维顺序选中起终点之间的卡片；起笔格已选则为取消笔；不松手回拖自动撤销涂出部分）；
- 卡片悬停时左上角出现重命名（内联编辑）/ 删除按钮（回收站），右上角 ♥ 常驻；点击卡片打开；
- 搜索框按 OCR 文本过滤图片（中英文，不区分大小写）；设置页「图片搜索」关闭时搜索框整行收起（同时不跑 OCR）。
- 还没打开任何文件时，网格中央显示空态文案（播放页同样有「按 Ctrl+O 打开文件」提示）。
- 千级目录：卡片分批建立，等待期间显示加载动画；打开文件不再受资料库建卡阻塞。
- 大目录卡片按行数撑开滚动区高度，不会因窗口高度把行压扁而叠在一起。

## 日志

运行日志在 `%APPDATA%/Feel/logs/feel.log`（UTF-8，1 MiB × 3 轮转）。启动、命令、打开文件/文件夹、
刷新、改名、删除、主题、播放失败、OCR 生命周期都会记录；`sys.excepthook` / `threading.excepthook`
与 Qt 消息（warning 及以上）也会写进去。设置页「日志」组可直接**打开日志**或**打开日志目录**。

OCR 在后台静默运行：结果逐张写入 sqlite；关掉应用中断后，下次打开同目录会从缓存秒回已完成项，
未识别的继续补跑。

## 开发 / 验证

```bash
.venv/Scripts/python.exe -m unittest discover -s tests          # 纯逻辑单测
.venv/Scripts/python.exe tools/smoke_phase1.py                  # 骨架
.venv/Scripts/python.exe tools/smoke_phase2.py                  # 播放核心（格式矩阵/transport/音量）
.venv/Scripts/python.exe tools/smoke_phase3.py                  # 四种播放模式/删除/步长
.venv/Scripts/python.exe tools/smoke_phase4.py                  # 缩放/旋转/全屏
.venv/Scripts/python.exe tools/smoke_phase5.py                  # shelf 卡片/筛选/涂抹/重命名/删除
.venv/Scripts/python.exe tools/smoke_phase6.py                  # OCR/搜索/缓存
.venv/Scripts/python.exe tools/smoke_phase7.py                  # 收藏/书签/抽屉/OCR 续跑
.venv/Scripts/python.exe tools/smoke_phase8.py                  # 悬停帧预览/主题过渡/空态错误态
.venv/Scripts/python.exe tools/smoke_phase9.py                  # 排序/倍速/方向键/卡片均分/命令行参数
.venv/Scripts/python.exe tools/smoke_phase10.py                 # 主题图标按钮/启动空态/标题改名/音量 OSD/直接删除开关
.venv/Scripts/python.exe tools/smoke_phase11.py                 # F 全屏/E 收藏/点别处收起改名/打开文件夹/帮助页
.venv/Scripts/python.exe tools/smoke_phase12.py                 # 大目录打开文件夹不重不跳/日志捕获与设置页入口
.venv/Scripts/python.exe tools/smoke_phase13.py                 # 筛选决定播放队列/音量滚轮/深色卡片图标
```

`tools/gen_test_media.py` 可生成测试媒体；冒烟截图落在 `C:/tmp/scratch/feel-phase*/`。
冒烟脚本把自己的 `APPDATA` 指向 `C:/tmp/scratch/feel-phaseN/appdata`，不会改动用户的
`%APPDATA%/Feel/config.json` 与 `feel.db`。

## 已知限制

- 播放走 Qt6 FFmpeg 后端且本机未启用硬解，4K 高码率可能掉帧；
- HEIC/HEIF 需要额外解码库，未支持；
- 缩放与拖动平移为会话内状态；旋转按文件持久化到 sqlite（跨会话保留）；排序方式持久化到 config.json；
- 不支持 URL 流播放、字幕、图片编辑。
