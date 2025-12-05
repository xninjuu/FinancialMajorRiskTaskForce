from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple

from app.storage.db import Database
from app.core.validation import sanitize_text


def hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def add_evidence(db: Database, case_id: str, file_path: Path, added_by: str) -> Tuple[str, str]:
    sanitized_case = sanitize_text(case_id, max_length=128)
    if not sanitized_case:
        raise ValueError("Case ID required")
    file_path = file_path.expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Evidence file not found: {file_path}")
    digest = hash_file(file_path)
    db.record_evidence(sanitized_case, file_path.name, digest, added_by=added_by, sealed=False)
    return file_path.name, digest


def list_evidence(db: Database, case_id: str):
    return db.list_evidence(case_id)
