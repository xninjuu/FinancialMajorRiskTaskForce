from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.domain import CaseNote, Transaction
from app.persistence import PersistenceLayer


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.persistence = PersistenceLayer(str(db_path))
        self.conn: sqlite3.Connection = self.persistence.conn
        self._init_security_tables()

    def _init_security_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT,
                action TEXT NOT NULL,
                target TEXT,
                details TEXT
            )
            """
        )
        self.conn.commit()

    def ensure_admin(self, *, password_hash: str | None, generated_password_callback) -> None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        if count == 0:
            if password_hash is None:
                generated = secrets.token_urlsafe(12)
                password_hash = generated_password_callback(generated)
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", password_hash, "ADMIN"),
            )
            self.conn.commit()

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT username, password_hash, role FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return None
        return {"username": row[0], "password_hash": row[1], "role": row[2]}

    def record_audit(self, username: str, action: str, target: str | None = None, details: str | None = None) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO audit_log (timestamp, username, action, target, details) VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), username, action, target, details),
        )
        self.conn.commit()

    def fetch_audit(self, limit: int = 200) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT timestamp, username, action, target, details FROM audit_log ORDER BY datetime(timestamp) DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "timestamp": row[0],
                "username": row[1],
                "action": row[2],
                "target": row[3],
                "details": row[4],
            }
            for row in cursor.fetchall()
        ]

    # Convenience pass-throughs to the persistence layer
    def record_transaction(self, tx: Transaction) -> None:
        self.persistence.record_transaction(tx)

    def record_alert(self, *args, **kwargs) -> None:
        self.persistence.record_alert(*args, **kwargs)

    def record_case(self, *args, **kwargs) -> None:
        self.persistence.record_case(*args, **kwargs)

    def list_alerts(self, *args, **kwargs):
        return self.persistence.list_alerts(*args, **kwargs)

    def list_cases(self, *args, **kwargs):
        return self.persistence.list_cases(*args, **kwargs)

    def get_case(self, *args, **kwargs):
        return self.persistence.get_case(*args, **kwargs)

    def alerts_for_case(self, *args, **kwargs):
        return self.persistence.alerts_for_case(*args, **kwargs)

    def case_notes(self, *args, **kwargs):
        return self.persistence.case_notes(*args, **kwargs)

    def recent_transactions(self, *args, **kwargs):
        return self.persistence.recent_transactions(*args, **kwargs)

    def attach_note(self, case_id: str, note: CaseNote) -> None:
        row = self.get_case(case_id)
        if not row:
            return
        existing_notes = self.case_notes(case_id)
        existing_notes.append(note)
        from app.domain import Case, CaseStatus, CaseLabel

        case = Case(
            id=case_id,
            alerts=[],
            status=CaseStatus[row["status"]],
            label=CaseLabel[row["label"]] if row["label"] else None,
            priority=row["priority"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            notes=existing_notes,
        )
        self.record_case(case)

    def update_case_status(self, case_id: str, status: str, label: str | None = None) -> None:
        row = self.get_case(case_id)
        if not row:
            return
        from app.domain import Case, CaseStatus, CaseLabel

        notes = self.case_notes(case_id)
        case = Case(
            id=case_id,
            alerts=[],
            status=CaseStatus[status],
            label=CaseLabel[label] if label else None,
            priority=row["priority"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.utcnow(),
            notes=notes,
        )
        self.record_case(case)
