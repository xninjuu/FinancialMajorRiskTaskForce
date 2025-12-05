from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from .domain import Alert, Case, CaseNote, CaseStatus, Task, TaskStatus, Transaction
from .runtime_paths import ensure_parent_dir


class PersistenceLayer:
    SCHEMA_VERSION = 7

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
        cursor.execute("DROP TABLE IF EXISTS forensic_exports")
        cursor.execute("DROP TABLE IF EXISTS evidence")
        cursor.execute("DROP TABLE IF EXISTS sealed_cases")
        cursor.execute("DROP TABLE IF EXISTS correlations")
        cursor.execute("DROP TABLE IF EXISTS baselines")
        cursor.execute("DROP TABLE IF EXISTS tasks")
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
        cursor.execute(
            """
            CREATE TABLE forensic_exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                path TEXT,
                hash TEXT,
                created_at TEXT,
                redacted INTEGER DEFAULT 0,
                watermark TEXT,
                manifest TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                filename TEXT,
                hash TEXT,
                added_by TEXT,
                sealed INTEGER DEFAULT 0,
                created_at TEXT,
                evidence_type TEXT,
                tags TEXT,
                importance TEXT,
                preview_path TEXT,
                ocr_text TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE sealed_cases (
                case_id TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                sealed_at TEXT,
                sealed_by TEXT,
                merkle_root TEXT,
                seal_reason TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT,
                related_id TEXT,
                reason TEXT,
                created_at TEXT,
                confidence REAL,
                reason_token TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE baselines (
                customer_id TEXT PRIMARY KEY,
                avg_amount REAL,
                tx_count INTEGER,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                created_by TEXT,
                assignee TEXT,
                priority TEXT,
                status TEXT,
                related_case_id TEXT,
                related_alert_id TEXT,
                due_at TEXT,
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

    # region Tasks
    def upsert_task(self, task: Task) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO tasks (
                id, title, description, created_by, assignee, priority, status,
                related_case_id, related_alert_id, due_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.title,
                task.description,
                task.created_by,
                task.assignee,
                task.priority,
                task.status.name,
                task.related_case_id,
                task.related_alert_id,
                task.due_at.isoformat() if task.due_at else None,
                task.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def list_tasks(
        self,
        *,
        assignee: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 200,
    ) -> list[Task]:
        cursor = self.conn.cursor()
        query = "SELECT * FROM tasks"
        params: list[str] = []
        clauses: list[str] = []
        if assignee:
            clauses.append("assignee = ?")
            params.append(assignee)
        if status:
            clauses.append("status = ?")
            params.append(status.name)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(str(limit))
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status.name, task_id))
        self.conn.commit()

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        due_at = datetime.fromisoformat(row["due_at"]) if row["due_at"] else None
        created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow()
        status_name = row["status"] or TaskStatus.OPEN.name
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            created_by=row["created_by"],
            assignee=row["assignee"],
            priority=row["priority"],
            status=TaskStatus[status_name] if status_name in TaskStatus.__members__ else TaskStatus.OPEN,
            related_case_id=row["related_case_id"],
            related_alert_id=row["related_alert_id"],
            due_at=due_at,
            created_at=created_at,
        )
    # endregion

    def get_transaction(self, tx_id: str) -> Transaction | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        row = cursor.fetchone()
        return self._row_to_transaction(row) if row else None

    def list_transactions(self, *, limit: int = 200) -> List[Transaction]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM transactions ORDER BY datetime(timestamp) DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def record_export(
        self,
        case_id: str,
        path: str,
        hash_value: str,
        *,
        redacted: bool = False,
        watermark: str | None = None,
        manifest: str | None = None,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO forensic_exports (case_id, path, hash, created_at, redacted, watermark, manifest)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                path,
                hash_value,
                datetime.utcnow().isoformat(),
                int(redacted),
                watermark,
                manifest,
            ),
        )
        self.conn.commit()

    def record_evidence(
        self,
        case_id: str,
        filename: str,
        hash_value: str,
        *,
        added_by: str,
        sealed: bool = False,
        evidence_type: str | None = None,
        tags: str | None = None,
        importance: str | None = None,
        preview_path: str | None = None,
        ocr_text: str | None = None,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO evidence (
                case_id, filename, hash, added_by, sealed, created_at,
                evidence_type, tags, importance, preview_path, ocr_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                filename,
                hash_value,
                added_by,
                int(sealed),
                datetime.utcnow().isoformat(),
                evidence_type,
                tags,
                importance,
                preview_path,
                ocr_text,
            ),
        )
        self.conn.commit()

    def list_evidence(self, case_id: str) -> list[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, filename, hash, added_by, sealed, created_at, evidence_type, tags, importance, preview_path, ocr_text
            FROM evidence
            WHERE case_id = ?
            ORDER BY datetime(created_at) DESC
            """,
            (case_id,),
        )
        return cursor.fetchall()

    def list_evidence_tags(self) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT tags FROM evidence WHERE tags IS NOT NULL")
        tags: set[str] = set()
        for row in cursor.fetchall():
            if not row[0]:
                continue
            for tag in str(row[0]).split(","):
                tag = tag.strip()
                if tag:
                    tags.add(tag)
        return sorted(tags)

    def seal_case(
        self,
        case_id: str,
        hash_value: str,
        *,
        sealed_by: str,
        merkle_root: str | None = None,
        seal_reason: str | None = None,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO sealed_cases (case_id, hash, sealed_at, sealed_by, merkle_root, seal_reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                hash_value,
                datetime.utcnow().isoformat(),
                sealed_by,
                merkle_root,
                seal_reason,
            ),
        )
        self.conn.commit()

    def sealed_case(self, case_id: str) -> sqlite3.Row | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT case_id, hash, sealed_at, sealed_by FROM sealed_cases WHERE case_id = ?", (case_id,))
        return cursor.fetchone()

    def record_correlation(
        self,
        alert_id: str,
        related_id: str,
        reason: str,
        *,
        confidence: float | None = None,
        reason_token: str | None = None,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO correlations (alert_id, related_id, reason, created_at, confidence, reason_token)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (alert_id, related_id, reason, datetime.utcnow().isoformat(), confidence, reason_token),
        )
        self.conn.commit()

    def list_correlations(self, alert_id: str) -> list[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT related_id, reason, created_at, confidence, reason_token
            FROM correlations
            WHERE alert_id = ?
            ORDER BY datetime(created_at) DESC
            """,
            (alert_id,),
        )
        return cursor.fetchall()

    def upsert_baseline(self, customer_id: str, avg_amount: float, tx_count: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO baselines (customer_id, avg_amount, tx_count, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
                avg_amount=excluded.avg_amount,
                tx_count=excluded.tx_count,
                updated_at=excluded.updated_at
            """,
            (customer_id, avg_amount, tx_count, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def fetch_baseline(self, customer_id: str) -> sqlite3.Row | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT customer_id, avg_amount, tx_count, updated_at FROM baselines WHERE customer_id = ?", (customer_id,)
        )
        return cursor.fetchone()

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
