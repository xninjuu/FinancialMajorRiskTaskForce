from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from .domain import Alert, Case, CaseNote, CaseStatus, Transaction
from .runtime_paths import ensure_parent_dir


class PersistenceLayer:
    SCHEMA_VERSION = 3

    def __init__(self, db_path: str = "codex.db") -> None:
        self.db_path = Path(db_path)
        ensure_parent_dir(self.db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        if version != self.SCHEMA_VERSION:
            self._recreate_schema(cursor)
        self.conn.commit()

    def _recreate_schema(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("DROP TABLE IF EXISTS alerts")
        cursor.execute("DROP TABLE IF EXISTS cases")
        cursor.execute("DROP TABLE IF EXISTS transactions")
        cursor.execute("DROP TABLE IF EXISTS case_notes")
        cursor.execute(
            """
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                account_id TEXT,
                timestamp TEXT,
                amount REAL,
                currency TEXT,
                counterparty_country TEXT,
                channel TEXT,
                is_credit INTEGER,
                merchant_category TEXT,
                purpose TEXT,
                device_id TEXT,
                card_present INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE cases (
                id TEXT PRIMARY KEY,
                status TEXT,
                label TEXT,
                priority TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE alerts (
                id TEXT PRIMARY KEY,
                transaction_id TEXT,
                score REAL,
                risk_level TEXT,
                domain TEXT,
                created_at TEXT,
                case_id TEXT,
                rationales TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE case_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                author TEXT,
                message TEXT,
                created_at TEXT
            )
            """
        )
        cursor.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")

    def record_transaction(self, tx: Transaction) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO transactions (
                id, account_id, timestamp, amount, currency,
                counterparty_country, channel, is_credit, merchant_category, purpose, device_id, card_present
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                tx.device_id,
                int(tx.card_present) if tx.card_present is not None else None,
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
            INSERT OR REPLACE INTO cases (id, status, label, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case.id,
                case.status.name,
                case.label.name if case.label else None,
                case.priority,
                case.created_at.isoformat(),
                case.updated_at.isoformat(),
            ),
        )
        self.conn.commit()
        self._record_notes(case)

    def _record_notes(self, case: Case) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM case_notes WHERE case_id = ?", (case.id,))
        for note in case.notes:
            cursor.execute(
                """
                INSERT INTO case_notes (case_id, author, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (case.id, note.author, note.message, note.created_at.isoformat()),
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
                id, transaction_id, score, risk_level, domain, created_at, case_id, rationales
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.id,
                alert.transaction.id,
                alert.score,
                risk_level,
                alert.evaluated_indicators[0].indicator.domain.name
                if alert.evaluated_indicators
                else "UNKNOWN",
                alert.created_at.isoformat(),
                alert.case_id,
                json.dumps(rationales),
            ),
        )
        self.conn.commit()

    def list_alerts(
        self,
        *,
        limit: int = 50,
        domain: str | None = None,
        min_score: float | None = None,
        status: str | None = None,
        since: datetime | None = None,
    ) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        query = "SELECT * FROM alerts"
        conditions: list[str] = []
        params: list[object] = []
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if min_score is not None:
            conditions.append("score >= ?")
            params.append(min_score)
        if status:
            conditions.append("risk_level = ?")
            params.append(status)
        if since:
            conditions.append("datetime(created_at) >= ?")
            params.append(since.isoformat())
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        return cursor.fetchall()

    def list_cases(self, *, status: str | None = None) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        query = "SELECT * FROM cases"
        params: list[object] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY datetime(updated_at) DESC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_case(self, case_id: str) -> sqlite3.Row | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
        return cursor.fetchone()

    def alerts_for_case(self, case_id: str) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM alerts WHERE case_id = ? ORDER BY datetime(created_at) DESC", (case_id,)
        )
        return cursor.fetchall()

    def case_notes(self, case_id: str) -> List[CaseNote]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM case_notes WHERE case_id = ? ORDER BY datetime(created_at) ASC", (case_id,))
        rows = cursor.fetchall()
        return [
            CaseNote(author=row["author"], message=row["message"], created_at=datetime.fromisoformat(row["created_at"]))
            for row in rows
        ]

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
            device_id=row["device_id"],
            card_present=bool(row["card_present"]) if row["card_present"] is not None else None,
        )
