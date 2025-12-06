from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from enum import Enum

from app.core.validation import coerce_limit
from app.storage.db import Database


class AuditAction(str, Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    CASE_STATUS_CHANGE = "CASE_STATUS_CHANGE"
    CASE_NOTE_ADDED = "CASE_NOTE_ADDED"
    CASE_OPENED = "CASE_OPENED"
    CASE_ASSIGNED = "CASE_ASSIGNED"
    CASE_EXPORTED = "CASE_EXPORTED"
    CASE_POLICY_TRIGGERED = "CASE_POLICY_TRIGGERED"
    SETTINGS_CHANGE = "SETTINGS_CHANGE"
    SESSION_LOCK = "SESSION_LOCK"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    CASE_SEALED = "CASE_SEALED"


class AuditLogger:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._executor = ThreadPoolExecutor(max_workers=2)

    def log(self, username: str, action: str, target: str | None = None, details: str | None = None) -> None:
        self.db.record_audit(username=username, action=action, target=target, details=details)

    def log_async(self, username: str, action: str, target: str | None = None, details: str | None = None) -> None:
        self._executor.submit(self.log, username, action, target, details)

    def log_case_action(
        self,
        username: str,
        action: str,
        case_id: str,
        *,
        role: str | None = None,
        details: str | None = None,
    ) -> None:
        detail_str = details or ""
        if role:
            detail_str = f"role={role}; {detail_str}" if detail_str else f"role={role}"
        self.log_async(username=username, action=action, target=case_id, details=detail_str)

    def recent(self, limit: int = 200):
        safe_limit = coerce_limit(limit)
        return self.db.fetch_audit(limit=safe_limit)
