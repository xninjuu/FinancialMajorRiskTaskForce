from __future__ import annotations

from enum import Enum

from app.core.validation import coerce_limit
from app.storage.db import Database


class AuditAction(str, Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    CASE_STATUS_CHANGE = "CASE_STATUS_CHANGE"
    CASE_NOTE_ADDED = "CASE_NOTE_ADDED"
    SETTINGS_CHANGE = "SETTINGS_CHANGE"
    SESSION_LOCK = "SESSION_LOCK"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    CASE_SEALED = "CASE_SEALED"


class AuditLogger:
    def __init__(self, db: Database) -> None:
        self.db = db

    def log(self, username: str, action: str, target: str | None = None, details: str | None = None) -> None:
        self.db.record_audit(username=username, action=action, target=target, details=details)

    def recent(self, limit: int = 200):
        safe_limit = coerce_limit(limit)
        return self.db.fetch_audit(limit=safe_limit)
