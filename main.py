"""Feel — 本地音视频 / 图片查看器入口。

用法：
    python main.py [文件或目录]

支持 Windows「打开方式」把文件路径作为第一个参数传进来（run.bat 已转发 %*）。
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from feel import logs
from feel.app import FeelWindow
from feel.cli import find_open_target


def icon_path() -> Path:
    """assets/app.ico；冻结后在 sys._MEIPASS（onedir 的 _internal）里。"""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return base / 'assets' / 'app.ico'


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    log = logs.setup()
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(argv)
        app.setApplicationName('Feel')
        app.setApplicationDisplayName('Feel')
        app.setWindowIcon(QIcon(str(icon_path())))
        log.info('窗口图标：%s', icon_path())

        window = FeelWindow()
        window.show()

        target = find_open_target(argv[1:])
        if target is not None:
            log.info('启动参数打开：%s', target)
            window.open_argument(target)
        return app.exec()
    except Exception as error:  # noqa: BLE001 - 记录后照常抛出
        log.critical('启动/运行失败：%s', error, exc_info=True)
        raise


if __name__ == '__main__':
    import multiprocessing

    # 打包成 exe 后 OCR 的 ProcessPoolExecutor 会以本 exe 重新拉起子进程；
    # 不调用 freeze_support() 会把整个应用再跑一遍（表现为闪出多个窗口）。
    multiprocessing.freeze_support()
    sys.exit(main())
