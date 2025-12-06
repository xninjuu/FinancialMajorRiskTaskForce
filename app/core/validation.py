from __future__ import annotations

import re
from typing import Optional

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
ALLOWED_ROLES = {"ANALYST", "LEAD", "ADMIN"}
ALLOWED_DOMAINS = {"AML", "FRAUD", "TF", "TAX"}


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


def sanitize_filter(value: str, *, max_length: int = 128) -> str:
    """Sanitize short filter/search strings for table filters."""

    return sanitize_text(value, max_length=max_length, allow_newlines=False)


def validate_username(username: str) -> bool:
    return bool(username) and bool(USERNAME_PATTERN.match(username))


def validate_password_policy(password: str, *, min_length: int = 12) -> tuple[bool, Optional[str]]:
    if not password:
        return False, "Password required"
    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters"
    return True, None


def validate_role(role: str) -> bool:
    return role in ALLOWED_ROLES


def validate_domain(domain: str) -> bool:
    return domain in ALLOWED_DOMAINS


def coerce_limit(value: Optional[str | int], *, default: int = 200, maximum: int = 500) -> int:
    """Force user-provided limits into a safe bounded integer."""

    try:
        limit = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if limit <= 0:
        return default
    return min(limit, maximum)
