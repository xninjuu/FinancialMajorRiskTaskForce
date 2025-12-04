from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

from .domain import Alert, Case, Transaction


class PersistenceLayer:
    def __init__(self, db_path: str = "codex.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                account_id TEXT,
                timestamp TEXT,
                amount REAL,
                currency TEXT,
                counterparty_country TEXT,
                channel TEXT,
                is_credit INTEGER,
                merchant_category TEXT,
                purpose TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                status TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                transaction_id TEXT,
                score REAL,
                risk_level TEXT,
                created_at TEXT,
                case_id TEXT,
                rationales TEXT
            )
            """
        )
        self.conn.commit()

    def record_transaction(self, tx: Transaction) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO transactions (
                id, account_id, timestamp, amount, currency,
                counterparty_country, channel, is_credit, merchant_category, purpose
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx.id,
                tx.account_id,
                tx.timestamp.isoformat(),
                tx.amount,
                tx.currency,
                tx.counterparty_country,
                tx.channel,
                int(tx.is_credit),
                tx.merchant_category,
                tx.purpose,
            ),
        )
        self.conn.commit()

    def recent_transactions(self, account_id: str, *, window: timedelta) -> List[Transaction]:
        cursor = self.conn.cursor()
        threshold = datetime.utcnow() - window
        cursor.execute(
            """
            SELECT * FROM transactions
            WHERE account_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (account_id, threshold.isoformat()),
        )
        rows = cursor.fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def record_case(self, case: Case) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO cases (id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                case.id,
                case.status,
                case.created_at.isoformat(),
                case.updated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def record_alert(self, alert: Alert, risk_level: str) -> None:
        cursor = self.conn.cursor()
        rationales = [
            {
                "code": hit.indicator.code,
                "description": hit.indicator.description,
                "explanation": hit.explanation,
                "is_hit": hit.is_hit,
                "weight": hit.indicator.weight,
            }
            for hit in alert.evaluated_indicators
        ]
        cursor.execute(
            """
            INSERT OR REPLACE INTO alerts (
                id, transaction_id, score, risk_level, created_at, case_id, rationales
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.id,
                alert.transaction.id,
                alert.score,
                risk_level,
                alert.created_at.isoformat(),
                alert.case_id,
                json.dumps(rationales),
            ),
        )
        self.conn.commit()

    def list_alerts(self, *, limit: int = 50) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM alerts
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    def list_cases(self) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM cases ORDER BY datetime(updated_at) DESC")
        return cursor.fetchall()

    def _row_to_transaction(self, row: sqlite3.Row) -> Transaction:
        return Transaction(
            id=row["id"],
            account_id=row["account_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            amount=row["amount"],
            currency=row["currency"],
            counterparty_country=row["counterparty_country"],
            channel=row["channel"],
            is_credit=bool(row["is_credit"]),
            merchant_category=row["merchant_category"],
            purpose=row["purpose"],
        )
