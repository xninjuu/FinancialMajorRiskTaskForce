from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List

from app.domain import Alert
from app.storage.db import Database


class CorrelationEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    def correlate(self, alerts: Iterable[Alert]) -> Dict[str, List[str]]:
        by_account: Dict[str, List[Alert]] = defaultdict(list)
        by_counterparty: Dict[str, List[Alert]] = defaultdict(list)
        for alert in alerts:
            by_account[alert.transaction.account_id].append(alert)
            by_counterparty[alert.transaction.counterparty_country].append(alert)
        edges: Dict[str, List[str]] = defaultdict(list)

        def _link(a: Alert, b: Alert, reason: str, token: str, confidence: float) -> None:
            edges[a.id].append(b.id)
            edges[b.id].append(a.id)
            self.db.record_correlation(a.id, b.id, reason, confidence=confidence, reason_token=token)
            self.db.record_correlation(b.id, a.id, reason, confidence=confidence, reason_token=token)

        for bucket, token, base_reason in [
            (by_account.values(), "shared_destination", "Shared account linkage"),
            (by_counterparty.values(), "timing_anomaly", "Repeated counterparty"),
        ]:
            for group in bucket:
                for i, source in enumerate(group):
                    for target in group[i + 1 :]:
                        confidence = 0.55
                        reasons: List[str] = [base_reason]
                        if abs(source.score - target.score) < 5:
                            confidence += 0.1
                            reasons.append("similar_score")
                        if _temporal_overlap(source, target, window=timedelta(hours=2)):
                            confidence += 0.1
                            reasons.append("temporal_burst")
                        if source.transaction.amount == target.transaction.amount:
                            confidence += 0.05
                            reasons.append("amount_match")
                        _link(source, target, "; ".join(reasons), token, min(confidence, 0.95))
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


def _temporal_overlap(a: Alert, b: Alert, *, window: timedelta) -> bool:
    delta = abs(a.transaction.timestamp - b.transaction.timestamp)
    return delta <= window
