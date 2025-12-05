from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List

from app.domain import Alert
from app.storage.db import Database


class CorrelationEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    def correlate(self, alerts: Iterable[Alert]) -> Dict[str, List[str]]:
        by_account: Dict[str, List[Alert]] = defaultdict(list)
        for alert in alerts:
            by_account[alert.transaction.account_id].append(alert)
        edges: Dict[str, List[str]] = defaultdict(list)
        for account_alerts in by_account.values():
            for i, source in enumerate(account_alerts):
                for target in account_alerts[i + 1 :]:
                    edges[source.id].append(target.id)
                    edges[target.id].append(source.id)
                    reason = "Shared account linkage"
                    token = "shared_destination"
                    confidence = 0.6
                    if abs(source.score - target.score) < 5:
                        confidence += 0.1
                    self.db.record_correlation(
                        source.id,
                        target.id,
                        reason,
                        confidence=confidence,
                        reason_token=token,
                    )
                    self.db.record_correlation(
                        target.id,
                        source.id,
                        reason,
                        confidence=confidence,
                        reason_token=token,
                    )
        return edges

    def correlated_for(self, alert_id: str):
        rows = self.db.list_correlations(alert_id)
        return [
            dict(
                related_id=row["related_id"],
                reason=row["reason"],
                created_at=row["created_at"],
                confidence=row["confidence"] if "confidence" in row.keys() else None,
                reason_token=row["reason_token"] if "reason_token" in row.keys() else None,
            )
            for row in rows
        ]
