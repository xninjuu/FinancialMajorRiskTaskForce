from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from app.core.policy_engine import PolicyEngine, PolicyResult
from app.storage.db import Database


@dataclass(frozen=True)
class CaseViewModel:
    id: str
    band: str
    status: str
    priority: str | None
    created_at: str | None
    updated_at: str | None
    policy_triggers: tuple[str, ...]


@dataclass(frozen=True)
class AlertRow:
    id: str
    transaction_id: str
    score: float
    risk_level: str
    domain: str
    created_at: str
    case_id: str | None


@dataclass(frozen=True)
class EvidenceRow:
    id: str
    case_id: str | None
    kind: str
    hash_value: str | None
    added_at: str


class CaseRepository:
    def __init__(self, db: Database, policy_engine: PolicyEngine) -> None:
        self.db = db
        self.policy_engine = policy_engine
        self._cache: dict[str, CaseViewModel] = {}

    def list_cases(self) -> List[CaseViewModel]:
        raw_rows = self.db.list_cases()
        results: List[CaseViewModel] = []
        for row in raw_rows:
            row_dict = dict(row)
            alerts = self.db.alerts_for_case(row_dict["id"])
            policy_result = self.policy_engine.evaluate_case(row_dict, alerts)
            self.db.set_case_policy(
                row_dict["id"], policy_result.band, policy_result.triggered_policies, policy_result.explanations
            )
            vm = CaseViewModel(
                id=row_dict["id"],
                band=policy_result.band,
                status=row_dict.get("status") or "OPEN",
                priority=row_dict.get("priority"),
                created_at=row_dict.get("created_at"),
                updated_at=row_dict.get("updated_at"),
                policy_triggers=tuple(policy_result.triggered_policies),
            )
            results.append(vm)
            self._cache[vm.id] = vm
        return results

    def get_case_row(self, case_id: str) -> dict | None:
        case = self.db.get_case(case_id)
        return dict(case) if case else None

    def alerts_for_case(self, case_id: str) -> list[dict]:
        alerts = self.db.alerts_for_case(case_id)
        return [dict(a) for a in alerts]

    def case_timeline(self, case_id: str, limit: int = 400) -> list[dict]:
        events = self.db.case_timeline(case_id, limit=limit)
        return [dict(e) for e in events]

    def policy_result(self, case_row: dict, alerts: Iterable[dict]) -> PolicyResult:
        return self.policy_engine.evaluate_case(case_row, list(alerts))


class AlertRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_alerts(self, limit: int = 500) -> List[AlertRow]:
        rows = self.db.list_alerts(limit=limit)
        return [
            AlertRow(
                id=r["id"],
                transaction_id=r["transaction_id"],
                score=r["score"],
                risk_level=r.get("risk_level") or "Unknown",
                domain=r.get("domain") or "Unknown",
                created_at=r.get("created_at") or "",
                case_id=r.get("case_id"),
            )
            for r in rows
        ]


class EvidenceRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_evidence(self, limit: int = 500) -> List[EvidenceRow]:
        rows = self.db.list_evidence(limit=limit)
        return [
            EvidenceRow(
                id=str(r.get("id")),
                case_id=r.get("case_id"),
                kind=r.get("type") or "unknown",
                hash_value=r.get("hash"),
                added_at=r.get("created_at") or "",
            )
            for r in rows[:limit]
        ]
