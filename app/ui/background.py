from __future__ import annotations

from typing import Any, Callable

from PySide6 import QtCore


class _Dispatcher(QtCore.QObject):
    _invoke = QtCore.Signal(object, object, object)

    def __init__(self) -> None:
        super().__init__()
        self._invoke.connect(self._execute, QtCore.Qt.QueuedConnection)

    @QtCore.Slot(object, object, object)
    def _execute(self, callback: Callable[[Any, Exception | None], None] | None, result: Any, error: Exception | None) -> None:
        if callback:
            callback(result, error)

    def dispatch(self, callback: Callable[[Any, Exception | None], None] | None, result: Any, error: Exception | None) -> None:
        self._invoke.emit(callback, result, error)


_DISPATCHER = _Dispatcher()


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
            _DISPATCHER.dispatch(self.callback, result, error)


def run_in_background(fn: Callable[[], Any], callback: Callable[[Any, Exception | None], None] | None = None) -> None:
    pool = QtCore.QThreadPool.globalInstance()
    pool.start(_Job(fn, callback))
