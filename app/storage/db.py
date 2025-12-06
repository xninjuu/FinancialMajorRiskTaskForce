from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.validation import sanitize_text, validate_role
from app.domain import CaseNote, Task, TaskStatus, Transaction
from app.persistence import PersistenceLayer


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.persistence = PersistenceLayer(str(db_path))
        self.conn: sqlite3.Connection = self.persistence.conn
        self._init_security_tables()
        self._timeline_cache: dict[str, list[dict]] = {}

    def _init_security_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                username TEXT NOT NULL,
                pref_key TEXT NOT NULL,
                pref_value TEXT NOT NULL,
                PRIMARY KEY (username, pref_key)
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
        self._ensure_user_security_columns(cursor)

    def create_user(self, *, username: str, password_hash: str, role: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (username, password_hash, role, failed_attempts, locked_until) VALUES (?, ?, ?, 0, NULL)",
            (username, password_hash, role),
        )
        self.conn.commit()

    def _ensure_user_security_columns(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cursor.fetchall()}
        if "failed_attempts" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0")
        if "locked_until" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN locked_until TEXT")
        self.conn.commit()

    def get_user_pref(self, username: str, pref_key: str, default: str | None = None) -> str | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT pref_value FROM user_preferences WHERE username = ? AND pref_key = ?",
            (username, pref_key),
        )
        row = cursor.fetchone()
        return row[0] if row else default

    def set_user_pref(self, username: str, pref_key: str, value: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_preferences (username, pref_key, pref_value) VALUES (?, ?, ?)",
            (username, pref_key, value),
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
        cursor.execute(
            "SELECT username, password_hash, role, failed_attempts, locked_until FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        role = row[2]
        if not validate_role(role):
            return None
        return {
            "username": row[0],
            "password_hash": row[1],
            "role": role,
            "failed_attempts": row[3],
            "locked_until": row[4],
        }

    def record_login_failure(self, username: str, *, threshold: int, lock_minutes: int) -> None:
        user = self.get_user(username)
        if not user:
            return
        attempts = (user.get("failed_attempts") or 0) + 1
        locked_until = None
        if attempts >= threshold:
            locked_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
            (attempts, locked_until.isoformat() if locked_until else None, username),
        )
        self.conn.commit()

    def record_login_success(self, username: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
            (username,),
        )
        self.conn.commit()

    def record_audit(self, username: str, action: str, target: str | None = None, details: str | None = None) -> None:
        username = sanitize_text(username, max_length=64)
        action = sanitize_text(action, max_length=64)
        target = sanitize_text(target, max_length=128) if target else None
        details = sanitize_text(details, max_length=512) if details else None
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

    def _invalidate_timeline(self, case_id: str | None) -> None:
        if case_id:
            self._timeline_cache.pop(case_id, None)
        else:
            self._timeline_cache.clear()

    def record_alert(self, alert, risk_level: str) -> None:
        self.persistence.record_alert(alert, risk_level)
        self._invalidate_timeline(getattr(alert, "case_id", None))

    def record_case(self, case, *args, **kwargs) -> None:
        self.persistence.record_case(case, *args, **kwargs)
        self._invalidate_timeline(getattr(case, "id", None))

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

    def get_transaction(self, tx_id: str):
        return self.persistence.get_transaction(tx_id)

    # Tasks
    def upsert_task(self, task: Task) -> None:
        self.persistence.upsert_task(task)

    def list_tasks(self, *, assignee: str | None = None, status: TaskStatus | None = None, limit: int = 200):
        return self.persistence.list_tasks(assignee=assignee, status=status, limit=limit)

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        self.persistence.update_task_status(task_id, status)

    def list_transactions(self, *, limit: int = 200):
        return self.persistence.list_transactions(limit=limit)

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
        self.persistence.record_export(
            case_id,
            path,
            hash_value,
            redacted=redacted,
            watermark=watermark,
            manifest=manifest,
        )

    # Extended investigative helpers
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
        filename = sanitize_text(filename, max_length=256)
        added_by = sanitize_text(added_by, max_length=64)
        self.persistence.record_evidence(
            case_id,
            filename,
            hash_value,
            added_by=added_by,
            sealed=sealed,
            evidence_type=evidence_type,
            tags=tags,
            importance=importance,
            preview_path=preview_path,
            ocr_text=ocr_text,
        )

    def list_evidence(self, case_id: str):
        return self.persistence.list_evidence(case_id)

    def list_evidence_tags(self) -> list[str]:
        return self.persistence.list_evidence_tags()

    def seal_case(
        self,
        case_id: str,
        hash_value: str,
        *,
        sealed_by: str,
        merkle_root: str | None = None,
        seal_reason: str | None = None,
    ) -> None:
        sealed_by = sanitize_text(sealed_by, max_length=64)
        self.persistence.seal_case(
            case_id,
            hash_value,
            sealed_by=sealed_by,
            merkle_root=merkle_root,
            seal_reason=seal_reason,
        )

    def sealed_case(self, case_id: str):
        return self.persistence.sealed_case(case_id)

    def record_correlation(
        self,
        alert_id: str,
        related_id: str,
        reason: str,
        *,
        confidence: float | None = None,
        reason_token: str | None = None,
    ) -> None:
        reason = sanitize_text(reason, max_length=200)
        self.persistence.record_correlation(
            alert_id,
            related_id,
            reason,
            confidence=confidence,
            reason_token=reason_token,
        )

    def list_correlations(self, alert_id: str, *, limit: int = 200):
        return self.persistence.list_correlations(alert_id, limit=limit)

    def correlation_metrics(self, alert_ids: list[str], *, max_rows: int = 500):
        return self.persistence.correlation_metrics(alert_ids, max_rows=max_rows)

    def upsert_baseline(self, customer_id: str, avg_amount: float, tx_count: int) -> None:
        self.persistence.upsert_baseline(customer_id, avg_amount, tx_count)

    def fetch_baseline(self, customer_id: str):
        return self.persistence.fetch_baseline(customer_id)

    def audit_for_target(self, target: str, *, limit: int = 200):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, username, action, target, details
            FROM audit_log
            WHERE target = ?
            ORDER BY datetime(timestamp) ASC
            LIMIT ?
            """,
            (target, limit),
        )
        return cursor.fetchall()

    def case_timeline(self, case_id: str, limit: int | None = 400):
        cached = self._timeline_cache.get(case_id)
        if cached:
            return cached[-limit:] if limit else list(cached)

        events: list[dict] = []
        for alert_row in self.alerts_for_case(case_id):
            alert = dict(alert_row)
            created = alert.get("created_at") or ""
            risk_level = alert.get("risk_level") or "Unknown"
            events.append(
                {
                    "timestamp": created,
                    "type": "Alert",
                    "description": f"Alert {alert.get('id', '')} ({risk_level})",
                    "risk_level": risk_level,
                    "metadata": alert,
                }
            )
            tx_id = alert.get("transaction_id")
            tx = self.get_transaction(tx_id) if tx_id else None
            if tx:
                events.append(
                    {
                        "timestamp": tx.timestamp.isoformat(),
                        "type": "Transaction",
                        "description": f"Transaction {tx.amount:.2f} {tx.currency} via {tx.channel}",
                        "metadata": tx,
                    }
                )
        for note in self.case_notes(case_id):
            events.append(
                {
                    "timestamp": note.created_at.isoformat(),
                    "type": "Note",
                    "risk_level": None,
                    "description": f"{note.author}: {note.message}",
                    "metadata": note,
                }
            )
        for audit_row in self.audit_for_target(case_id):
            audit = dict(audit_row)
            events.append(
                {
                    "timestamp": audit.get("timestamp", ""),
                    "type": "Audit",
                    "risk_level": None,
                    "description": f"{audit.get('action', '')} by {audit.get('username', '')}",
                    "metadata": audit,
                }
            )
        events.sort(key=lambda e: e.get("timestamp") or "")

        if limit:
            cached_events = events[-800:]
            self._timeline_cache[case_id] = cached_events
            return events[-limit:]

        self._timeline_cache[case_id] = events
        return events

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

    def set_case_policy(self, case_id: str, band: str, triggers: list[str], explanations: list[str]) -> None:
        self.persistence.update_case_policy(case_id, band, triggers, explanations)
        self._invalidate_timeline(case_id)

    def assign_case(self, case_id: str, assignee: str | None) -> None:
        self.persistence.update_case_assignee(case_id, assignee)
        self._invalidate_timeline(case_id)

    def set_case_policy_flag(self, case_id: str, flagged: bool) -> None:
        self.persistence.set_case_policy_flag(case_id, flagged)
        self._invalidate_timeline(case_id)

    def update_case_status(self, case_id: str, status: str, label: str | None = None) -> None:
        row = self.get_case(case_id)
        if not row:
            return
        from app.domain import Case, CaseStatus, CaseLabel

        if status not in CaseStatus.__members__:
            return
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
        self._invalidate_timeline(case_id)
