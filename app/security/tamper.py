from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import List, Tuple

from app.config.settings import AppSettings
from app.runtime_paths import runtime_dir


class TamperCheckResult:
    def __init__(self, ok: bool, warnings: List[str] | None = None, errors: List[str] | None = None) -> None:
        self.ok = ok
        self.warnings = warnings or []
        self.errors = errors or []


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_executable(settings: AppSettings) -> TamperCheckResult:
    warnings: List[str] = []
    errors: List[str] = []

    exe_path = Path(sys.executable).resolve()
    expected = settings.expected_exe_hash

    if expected:
        actual = _sha256(exe_path)
        if actual.lower() != expected.lower():
            msg = (
                "Executable hash mismatch. Expected {expected} but saw {actual}. "
                "Do not trust this binary."
            ).format(expected=expected, actual=actual)
            if settings.secure_mode:
                errors.append(msg)
            else:
                warnings.append(msg)
    elif settings.secure_mode:
        errors.append("Secure mode enabled but CODEX_EXPECTED_EXE_HASH not provided.")

    db_parent = Path(settings.db_path).resolve().parent
    if db_parent == runtime_dir().resolve():
        warnings.append("Database stored alongside executable; ensure directory permissions are restricted.")

    if not os.access(db_parent, os.W_OK):
        errors.append(f"Database directory {db_parent} not writable.")

    return TamperCheckResult(ok=not errors, warnings=warnings, errors=errors)
