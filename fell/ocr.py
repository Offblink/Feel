"""后台 OCR 服务（FR-23）：独立子进程识别 + sqlite 缓存，全程静默。

onnxruntime 在 Qt 线程池线程里会死锁（实测：第二张图推理永不返回），
因此 OCR 跑在单 worker 的 ProcessPoolExecutor 子进程里，主线程用 QTimer 轮询结果。
结果逐张写缓存；中途关闭后，下次打开同目录会自动续跑未识别项。
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .logs import logger
from .ocr_engine import recognize


class OcrService(QObject):
    textReady = Signal(str, str)
    progress = Signal(int, int)
    finished = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self._store = store
        self._executor: ProcessPoolExecutor | None = None
        self._futures: dict[object, tuple[int, str, int, int]] = {}
        self._generation = 0
        self._pending = 0
        self._done = 0
        self._total = 0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._poll)

    @property
    def is_running(self) -> bool:
        return self._pending > 0

    # ---- 对外 ----
    def scan(self, images: list[Path], force: bool = False) -> None:
        self._generation += 1
        logger().info('OCR 扫描：%d 张（force=%s）', len(images), force)
        generation = self._generation
        for future in list(self._futures):
            future.cancel()
        self._futures.clear()
        self._pending = 0
        self._done = 0
        self._total = len(images)
        self._timer.stop()

        for path in images:
            try:
                stat = path.stat()
            except OSError:
                continue
            if force:
                self._store.delete_ocr(path)
            cached = None if force else self._store.get_ocr(
                path, stat.st_mtime_ns, stat.st_size
            )
            if cached is not None:
                self._done += 1
                self.textReady.emit(str(path), cached)
                continue
            executor = self._ensure_executor()
            future = executor.submit(recognize, str(path))
            self._futures[future] = (generation, str(path),
                                     stat.st_mtime_ns, stat.st_size)
            self._pending += 1

        self.progress.emit(self._done, self._total)
        if self._pending == 0:
            self.finished.emit()
        else:
            self._timer.start()

    def cancel(self) -> None:
        self._generation += 1
        for future in list(self._futures):
            future.cancel()
        self._futures.clear()
        self._pending = 0
        self._timer.stop()
        self.finished.emit()

    def shutdown(self) -> None:
        self.cancel()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    # ---- 内部 ----
    def _ensure_executor(self) -> ProcessPoolExecutor:
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=1)
        return self._executor

    def _poll(self) -> None:
        for future in list(self._futures):
            if not future.done():
                continue
            generation, path, mtime, size = self._futures.pop(future)
            try:
                text = future.result()
            except Exception as error:  # noqa: BLE001 - 单张失败不影响其它
                logger().warning('OCR 失败：%s（%s）', path, error)
                text = ''
            if generation != self._generation:
                continue
            self._store.put_ocr(Path(path), mtime, size, text)
            self._done += 1
            self._pending = max(0, self._pending - 1)
            self.textReady.emit(path, text)
            self.progress.emit(self._done, self._total)
        if self._pending == 0:
            self._timer.stop()
            logger().info('OCR 完成：%d/%d', self._done, self._total)
            self.finished.emit()
