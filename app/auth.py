from __future__ import annotations

import hashlib
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple


class AccessScope(Enum):
    PUBLIC = auto()
    INTERNAL_ONLY = auto()


@dataclass
class User:
    id: str
    email: str
    role: str
    access_scope: AccessScope
    password_hash: str
    created_at: datetime


@dataclass
class AuthenticatedSession:
    user: User
    issued_at: datetime

    @property
    def is_internal(self) -> bool:
        return self.user.access_scope == AccessScope.INTERNAL_ONLY


class PasswordGenerator:
    @staticmethod
    def generate(length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits + "!@$%&*#?"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()


class TwoFactorService:
    def __init__(self, lifetime_seconds: int = 300) -> None:
        self.lifetime_seconds = lifetime_seconds
        self.active_codes: Dict[str, Tuple[str, datetime]] = {}

    def generate_code(self, user_id: str) -> str:
        code = "".join(secrets.choice(string.digits) for _ in range(6))
        expires_at = datetime.utcnow() + timedelta(seconds=self.lifetime_seconds)
        self.active_codes[user_id] = (code, expires_at)
        return code

    def verify(self, user_id: str, code: str) -> bool:
        stored = self.active_codes.get(user_id)
        if not stored:
            return False
        value, expires_at = stored
        if datetime.utcnow() > expires_at:
            return False
        return secrets.compare_digest(value, code)


class WelcomeMailer:
    def __init__(self) -> None:
        self.sent_messages: List[str] = []

    def send_welcome_email(self, user: User, password: str, otp_code: str) -> None:
        body = (
            f"Welcome {user.email}!\n"
            f"Generated password: {password}\n"
            f"Your 2FA code: {otp_code}\n"
            "Access scope: INTERNAL ONLY – do not share externally."
        )
        message = f"To: {user.email}\nSubject: Welcome to FMR Codex\n\n{body}"
        self.sent_messages.append(message)
        print(f"[MAIL] Sending welcome email to {user.email}\n{message}")


class AuthService:
    def __init__(self, two_factor: TwoFactorService, mailer: WelcomeMailer) -> None:
        self.two_factor = two_factor
        self.mailer = mailer
        self.users: Dict[str, User] = {}

    def register_user(self, email: str, role: str, access_scope: AccessScope) -> Tuple[User, str, str]:
        password = PasswordGenerator.generate()
        password_hash = PasswordGenerator.hash_password(password)
        user = User(
            id=secrets.token_hex(8),
            email=email,
            role=role,
            access_scope=access_scope,
            password_hash=password_hash,
            created_at=datetime.utcnow(),
        )
        self.users[user.email] = user
        otp = self.two_factor.generate_code(user.id)
        self.mailer.send_welcome_email(user, password, otp)
        return user, password, otp

    def authenticate(self, email: str, password: str) -> Optional[User]:
        user = self.users.get(email)
        if not user:
            return None
        if user.password_hash != PasswordGenerator.hash_password(password):
            return None
        return user

    def verify_2fa(self, user: User, code: str) -> bool:
        return self.two_factor.verify(user.id, code)


class SessionManager:
    def __init__(self, auth_service: AuthService) -> None:
        self.auth_service = auth_service
        self.session: Optional[AuthenticatedSession] = None

    def login(self, email: str, password: str, otp_code: str) -> AuthenticatedSession:
        user = self.auth_service.authenticate(email, password)
        if not user:
            raise PermissionError("Invalid credentials")
        if not self.auth_service.verify_2fa(user, otp_code):
            raise PermissionError("Invalid or expired 2FA code")
        self.session = AuthenticatedSession(user=user, issued_at=datetime.utcnow())
        print(f"[AUTH] Session issued for {user.email} ({user.role})")
        return self.session

    def require_internal_access(self) -> None:
        if not self.session:
            raise PermissionError("No active session")
        if not self.session.is_internal:
            raise PermissionError("Internal-only access required")


class SecurityBootstrap:
    """Sets up a default internal operator and logs in with 2FA for the demo."""

    def __init__(self) -> None:
        self.two_factor = TwoFactorService()
        self.mailer = WelcomeMailer()
        self.auth = AuthService(self.two_factor, self.mailer)
        self.session_manager = SessionManager(self.auth)

    def provision_internal_operator(self) -> AuthenticatedSession:
        user, password, otp = self.auth.register_user(
            email="operator@fmr-taskforce.local",
            role="Investigator",
            access_scope=AccessScope.INTERNAL_ONLY,
        )
        # In a production setting, password and OTP would be entered by the user.
        session = self.session_manager.login(user.email, password, otp)
        print("[AUTH] Internal access granted. Restricted resources unlocked.")
        return session

    def summary(self) -> dict:
        return {
            "users": list(self.auth.users.keys()),
            "mail_log": len(self.mailer.sent_messages),
        }
