from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, List

from PySide6 import QtCore, QtGui


@dataclass
class ColumnDef:
    key: str
    header: str
    formatter: Callable[[Any], str] | None = None
    band_key: str | None = None
    severity_key: str | None = None


class RowTableModel(QtCore.QAbstractTableModel):
    def __init__(self, columns: List[ColumnDef], rows: Iterable[dict] | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = list(rows) if rows else []

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = self.columns[index.column()]
        if role == QtCore.Qt.DisplayRole:
            value = row.get(col.key)
            if col.formatter:
                return col.formatter(value)
            return "" if value is None else str(value)
        if role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft
        if role == QtCore.Qt.BackgroundRole:
            band = row.get(col.band_key) if col.band_key else None
            severity = row.get(col.severity_key) if col.severity_key else None
            color = None
            if band:
                color = self._band_color(str(band))
            if severity and not color:
                color = self._severity_color(str(severity))
            if color:
                return QtGui.QBrush(QtGui.QColor(color))
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole) -> Any:  # type: ignore[override]
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.columns[section].header
        return super().headerData(section, orientation, role)

    def set_rows(self, rows: Iterable[dict]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def row_dict(self, index: QtCore.QModelIndex | None) -> dict | None:
        if not index or not index.isValid():
            return None
        return self.rows[index.row()]

    def _band_color(self, band: str) -> str | None:
        band_upper = band.upper()
        if band_upper == "GREEN":
            return "#2ecc71"
        if band_upper == "YELLOW":
            return "#f1c40f"
        if band_upper == "RED":
            return "#e74c3c"
        return None

    def _severity_color(self, level: str) -> str | None:
        normalized = level.title()
        if normalized == "High":
            return "#e74c3c"
        if normalized == "Medium":
            return "#f1c40f"
        if normalized == "Low":
            return "#2ecc71"
        return None
