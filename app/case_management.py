from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from .domain import Alert, Case
from .persistence import PersistenceLayer


@dataclass
class CaseManagementService:
    cases: Dict[str, Case]

    def __init__(self, persistence: PersistenceLayer | None = None) -> None:
        self.cases = {}
        self.persistence = persistence

    def _find_case_for_alert(self, alert: Alert) -> Optional[Case]:
        for case in self.cases.values():
            if case.customer_id == alert.transaction.account_id and case.status != "Closed":
                return case
        return None

    def attach_alert(self, alert: Alert) -> Case:
        existing_case = self._find_case_for_alert(alert)
        if existing_case:
            existing_case.add_alert(alert)
            if len(existing_case.alerts) >= 3 and existing_case.status == "Open":
                existing_case.status = "Investigating"
                existing_case.updated_at = datetime.utcnow()
            if self.persistence:
                self.persistence.record_case(existing_case)
            return existing_case

        new_case = Case(id=f"case-{len(self.cases)+1}")
        new_case.add_alert(alert)
        if len(new_case.alerts) >= 3:
            new_case.status = "Investigating"
        self.cases[new_case.id] = new_case
        if self.persistence:
            self.persistence.record_case(new_case)
        return new_case

    def close_case(self, case_id: str) -> bool:
        case = self.cases.get(case_id)
        if not case:
            return False
        case.status = "Closed"
        case.updated_at = datetime.utcnow()
        if self.persistence:
            self.persistence.record_case(case)
        return True

    def summary(self) -> List[Case]:
        return list(self.cases.values())
