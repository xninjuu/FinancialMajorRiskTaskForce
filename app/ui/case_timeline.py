from __future__ import annotations

from PySide6 import QtWidgets

from app.storage.db import Database


class CaseTimelineDialog(QtWidgets.QDialog):
    def __init__(self, db: Database, case_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Case Timeline – {case_id}")
        self.resize(700, 500)
        layout = QtWidgets.QVBoxLayout()
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Type", "Description"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self._load(db, case_id)

    def _load(self, db: Database, case_id: str) -> None:
        events = db.case_timeline(case_id)
        self.table.setRowCount(len(events))
        for idx, event in enumerate(events):
            self.table.setItem(idx, 0, QtWidgets.QTableWidgetItem(str(event.get("timestamp"))))
            self.table.setItem(idx, 1, QtWidgets.QTableWidgetItem(str(event.get("type"))))
            self.table.setItem(idx, 2, QtWidgets.QTableWidgetItem(str(event.get("description"))))
