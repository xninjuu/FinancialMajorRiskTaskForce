from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Tuple

import bcrypt

from app.core.validation import validate_password_policy, validate_role, validate_username
from app.storage.db import Database


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.lock_threshold = 5
        self.lock_minutes = 5
        self.min_password_length = 12

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

        if env_password:
            ok, reason = validate_password_policy(env_password, min_length=self.min_password_length)
            if not ok:
                raise ValueError(f"CODEX_ADMIN_PASSWORD policy failure: {reason}")
        self.db.ensure_admin(
            password_hash=self.hash_password(env_password) if env_password else None, generated_password_callback=_callback
        )
        return generated_password

    def ensure_demo_user(self) -> tuple[str, str]:
        """Ensure a demo analyst account exists for quick onboarding.

        Returns a tuple of (username, password) for documentation/UX messaging. Password is
        hashed before persistence and only returned so the caller can surface it to the user
        in a controlled way (e.g., login dialog hint, README note).
        """
        username = os.getenv("CODEX_DEMO_USER", "analyst_demo")
        password = os.getenv("CODEX_DEMO_PASSWORD", "FMRdemo!2025")
        if not validate_username(username):
            username = "analyst_demo"
        ok, reason = validate_password_policy(password, min_length=self.min_password_length)
        if not ok:
            # fall back to a generated compliant password but still expose a value to the caller
            password = os.getenv("CODEX_DEMO_PASSWORD_FALLBACK", "FMRdemo!2025-Longer")
        if not self.db.get_user(username):
            self.db.create_user(username=username, password_hash=self.hash_password(password), role="ANALYST")
        return username, password

    def register_user(self, *, username: str, password: str, role: str = "ANALYST") -> tuple[bool, str]:
        if not validate_username(username):
            return False, "Ungültiger Benutzername (3-64 Zeichen)"
        ok, reason = validate_password_policy(password, min_length=self.min_password_length)
        if not ok:
            return False, reason
        if not validate_role(role):
            return False, "Rolle nicht erlaubt"
        if self.db.get_user(username):
            return False, "Benutzer existiert bereits"
        self.db.create_user(username=username, password_hash=self.hash_password(password), role=role)
        return True, "Benutzer angelegt"

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[str]]:
        if not validate_username(username):
            return False, None, "Ungültiger Benutzername"
        ok, reason = validate_password_policy(password, min_length=self.min_password_length)
        if not ok:
            return False, None, reason
        user = self.db.get_user(username)
        if not user:
            return False, None, "Unknown user"
        locked_until = user.get("locked_until")
        if locked_until:
            try:
                until_dt = datetime.fromisoformat(locked_until)
                if until_dt > datetime.utcnow():
                    return False, None, f"Account locked until {until_dt.isoformat()}"
            except ValueError:
                pass
        if not validate_role(user.get("role", "")):
            return False, None, "User role invalid"
        if self.verify_password(password, user["password_hash"]):
            self.db.record_login_success(username)
            return True, user["role"], None
        self.db.record_login_failure(username, threshold=self.lock_threshold, lock_minutes=self.lock_minutes)
        return False, None, "Invalid credentials"
