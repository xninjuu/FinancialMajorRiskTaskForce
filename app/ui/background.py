from __future__ import annotations

from typing import Any, Callable

from PySide6 import QtCore, QtWidgets


class _Job(QtCore.QRunnable):
    def __init__(self, fn: Callable[[], Any], callback: Callable[[Any, Exception | None], None] | None) -> None:
        super().__init__()
        self.fn = fn
        self.callback = callback

    def run(self) -> None:
        result: Any = None
        error: Exception | None = None
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            error = exc
        if self.callback:
            app = QtWidgets.QApplication.instance()
            if app:
                QtCore.QMetaObject.invokeMethod(
                    app,
                    lambda r=result, e=error: self.callback(r, e),
                    QtCore.Qt.QueuedConnection,
                )


def run_in_background(fn: Callable[[], Any], callback: Callable[[Any, Exception | None], None] | None = None) -> None:
    pool = QtCore.QThreadPool.globalInstance()
    pool.start(_Job(fn, callback))
