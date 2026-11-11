"""Fell — 本地音视频 / 图片查看器入口。

用法：
    python main.py [文件或目录]

支持 Windows「打开方式」把文件路径作为第一个参数传进来（run.bat 已转发 %*）。
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from fell import logs
from fell.app import FellWindow
from fell.cli import find_open_target


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    log = logs.setup()
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(argv)
        app.setApplicationName('Fell')
        app.setApplicationDisplayName('Fell')

        window = FellWindow()
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
    sys.exit(main())
