from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from app.domain import Transaction


def import_transactions_csv(path: Path) -> List[Transaction]:
    path = path.expanduser().resolve()
    txs: List[Transaction] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            txs.append(
                Transaction(
                    id=row["id"],
                    account_id=row["account_id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    amount=float(row["amount"]),
                    currency=row.get("currency", "EUR"),
                    counterparty_country=row.get("counterparty_country", ""),
                    channel=row.get("channel", "web"),
                    is_credit=row.get("is_credit", "true").lower() == "true",
                    merchant_category=row.get("merchant_category"),
                    purpose=row.get("purpose"),
                    device_id=row.get("device_id"),
                    card_present=(row.get("card_present", "true").lower() == "true"),
                )
            )
    return txs
