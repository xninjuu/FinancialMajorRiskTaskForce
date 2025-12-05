from __future__ import annotations

import re
from typing import Optional


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


def sanitize_text(value: str, *, max_length: int = 512, allow_newlines: bool = False) -> str:
    """Trim and strip control characters to reduce injection/formatting risk."""

    if value is None:
        return ""
    text = value.strip()
    if not allow_newlines:
        text = " ".join(text.splitlines())
    # remove non-printable/control chars
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:max_length]


def validate_username(username: str) -> bool:
    return bool(username) and bool(USERNAME_PATTERN.match(username))


def validate_password_policy(password: str, *, min_length: int = 12) -> tuple[bool, Optional[str]]:
    if not password:
        return False, "Password required"
    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters"
    return True, None
