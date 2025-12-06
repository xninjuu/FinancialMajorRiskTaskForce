from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6 import QtCore


@dataclass
class SelectionState:
    case_id: Optional[str] = None
    alert_id: Optional[str] = None
    actor_id: Optional[str] = None
    customer_id: Optional[str] = None


class AppState(QtCore.QObject):
    case_changed = QtCore.Signal(str)
    alert_changed = QtCore.Signal(str)
    filters_changed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.selection = SelectionState()
        self.domain_filter: str | None = None
        self.severity_filter: str | None = None
        self.date_filter_days: int | None = None

    def set_selected_case(self, case_id: Optional[str]) -> None:
        if case_id == self.selection.case_id:
            return
        self.selection.case_id = case_id
        if case_id:
            self.case_changed.emit(case_id)

    def set_selected_alert(self, alert_id: Optional[str]) -> None:
        if alert_id == self.selection.alert_id:
            return
        self.selection.alert_id = alert_id
        if alert_id:
            self.alert_changed.emit(alert_id)

    def update_filters(
        self,
        *,
        domain: Optional[str] = None,
        severity: Optional[str] = None,
        days: Optional[int] = None,
    ) -> None:
        changed = False
        if domain != self.domain_filter:
            self.domain_filter = domain
            changed = True
        if severity != self.severity_filter:
            self.severity_filter = severity
            changed = True
        if days != self.date_filter_days:
            self.date_filter_days = days
            changed = True
        if changed:
            self.filters_changed.emit()
