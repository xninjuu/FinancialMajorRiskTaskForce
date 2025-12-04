from __future__ import annotations

import os
from typing import Optional, Tuple

import bcrypt

from app.storage.db import Database


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    def bootstrap_admin(self) -> Optional[str]:
        env_password = os.getenv("CODEX_ADMIN_PASSWORD")
        generated_password: Optional[str] = None

        def _callback(generated: str) -> str:
            nonlocal generated_password
            generated_password = generated
            return self.hash_password(generated)

        self.db.ensure_admin(password_hash=self.hash_password(env_password) if env_password else None, generated_password_callback=_callback)
        return generated_password

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        user = self.db.get_user(username)
        if not user:
            return False, None
        if self.verify_password(password, user["password_hash"]):
            return True, user["role"]
        return False, None
