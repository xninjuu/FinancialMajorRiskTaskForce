from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.domain import Transaction
from app.storage.db import Database


@dataclass
class Baseline:
    customer_id: str
    avg_amount: float
    tx_count: int


class BaselineEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    def update_with_transactions(self, customer_id: str, txs: Iterable[Transaction]) -> Baseline:
        amounts = [t.amount for t in txs]
        if not amounts:
            avg = 0.0
            count = 0
        else:
            avg = sum(amounts) / len(amounts)
            count = len(amounts)
        self.db.upsert_baseline(customer_id, avg, count)
        return Baseline(customer_id=customer_id, avg_amount=avg, tx_count=count)

    def fetch(self, customer_id: str) -> Baseline | None:
        row = self.db.fetch_baseline(customer_id)
        if not row:
            return None
        return Baseline(customer_id=row["customer_id"], avg_amount=row["avg_amount"], tx_count=row["tx_count"])
