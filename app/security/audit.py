from __future__ import annotations

from app.storage.db import Database


class AuditLogger:
    def __init__(self, db: Database) -> None:
        self.db = db

    def log(self, username: str, action: str, target: str | None = None, details: str | None = None) -> None:
        self.db.record_audit(username=username, action=action, target=target, details=details)

    def recent(self, limit: int = 200):
        return self.db.fetch_audit(limit=limit)
