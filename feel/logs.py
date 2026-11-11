"""运行日志：轮转文件日志 + 未捕获异常 / Qt 消息捕获（入口在设置页「日志」）。

- 文件：`%APPDATA%/Feel/logs/feel.log`（UTF-8，1 MiB × 3 份轮转）
- 捕获：主线程与工作线程的未捕获异常、Qt 消息（warning 及以上）
- 启动即记录 pid / 命令行 / 日志路径，打包成 pythonw 无控制台时也能事后定位
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import app_data_dir

LOG_DIR: Path = app_data_dir() / 'logs'
LOG_PATH: Path = LOG_DIR / 'feel.log'
LOG_FORMAT = '%(asctime)s %(levelname)-7s [%(threadName)s] %(message)s'
MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 3

_configured = False


def logger() -> logging.Logger:
    """全应用唯一的 logger（未 setup 时也不会炸：只有 lastResort 输出）。"""
    return logging.getLogger('feel')


def setup(level: int = logging.INFO) -> logging.Logger:
    global _configured
    log = logger()
    if _configured:
        return log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.setLevel(level)
    log.setLevel(level)
    log.addHandler(handler)
    log.propagate = False
    _configured = True

    def _excepthook(exc_type, exc, tb):
        log.critical('未捕获异常：%s', exc, exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _excepthook

    def _thread_hook(args):
        log.critical(
            '线程未捕获异常：%s', args.exc_value,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_hook

    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        levels = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }

        def _qt_handler(mode, _context, message):
            log.log(levels.get(mode, logging.INFO), '[Qt] %s', message)

        qInstallMessageHandler(_qt_handler)
    except Exception:  # noqa: BLE001 - 没有 Qt 时只留文件日志
        log.exception('安装 Qt 消息处理器失败')

    log.info('==== Feel 启动 pid=%s ====', os.getpid())
    log.info('命令行：%s', ' '.join(sys.argv))
    log.info('日志文件：%s', LOG_PATH)
    return log


def open_log_folder() -> None:
    """在资源管理器里打开日志目录（设置页按钮）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    os.startfile(str(LOG_DIR))


def open_log_file() -> None:
    """用系统默认程序打开 feel.log（设置页按钮）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.touch()
    os.startfile(str(LOG_PATH))
