from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from .domain import Alert, Case


@dataclass
class CaseManagementService:
    cases: Dict[str, Case]

    def __init__(self) -> None:
        self.cases = {}

    def _find_case_for_alert(self, alert: Alert) -> Optional[Case]:
        for case in self.cases.values():
            if case.customer_id == alert.transaction.account_id and case.status != "Closed":
                return case
        return None

    def attach_alert(self, alert: Alert) -> Case:
        existing_case = self._find_case_for_alert(alert)
        if existing_case:
            existing_case.add_alert(alert)
            return existing_case

        new_case = Case(id=f"case-{len(self.cases)+1}")
        new_case.add_alert(alert)
        self.cases[new_case.id] = new_case
        return new_case

    def close_case(self, case_id: str) -> bool:
        case = self.cases.get(case_id)
        if not case:
            return False
        case.status = "Closed"
        case.updated_at = datetime.utcnow()
        return True

    def summary(self) -> List[Case]:
        return list(self.cases.values())
