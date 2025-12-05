from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from app.core.validation import sanitize_text


class SecureClipboard(QtCore.QObject):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear)

    def copy(self, text: str, *, ttl_ms: int = 5000) -> None:
        safe = sanitize_text(text, max_length=1024)
        QtWidgets.QApplication.clipboard().setText(safe)
        self.timer.start(ttl_ms)

    def clear(self) -> None:
        QtWidgets.QApplication.clipboard().clear()
