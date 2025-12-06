from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Tuple

try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except Exception:  # noqa: BLE001
    pytesseract = None
    Image = None

try:
    import PyPDF2  # type: ignore
except Exception:  # noqa: BLE001
    PyPDF2 = None

from app.storage.db import Database
from app.core.validation import sanitize_text
from app.runtime_paths import ensure_parent_dir, runtime_dir


def hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def add_evidence(
    db: Database,
    case_id: str,
    file_path: Path,
    added_by: str,
    *,
    evidence_type: str | None = None,
    tags: Iterable[str] | None = None,
    importance: str | None = None,
) -> Tuple[str, str]:
    sanitized_case = sanitize_text(case_id, max_length=128)
    if not sanitized_case:
        raise ValueError("Case ID required")
    file_path = file_path.expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Evidence file not found: {file_path}")
    digest = hash_file(file_path)
    tag_string = ",".join(sorted({sanitize_text(tag, max_length=32) for tag in tags})) if tags else None
    preview_path = None
    ocr_text = None
    suffix = file_path.suffix.lower()
    if Image and suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
        try:
            preview_path = runtime_dir() / "evidence_previews" / f"{file_path.stem}_thumb.png"
            ensure_parent_dir(preview_path)
            with Image.open(file_path) as img:
                img.thumbnail((256, 256))
                img.save(preview_path)
            if pytesseract:
                try:
                    ocr_text = pytesseract.image_to_string(Image.open(file_path))
                except Exception:  # noqa: BLE001
                    ocr_text = None
        except Exception:  # noqa: BLE001
            preview_path = None
    if PyPDF2 and suffix == ".pdf":
        try:
            reader = PyPDF2.PdfReader(str(file_path))
            if reader.pages:
                first_page = reader.pages[0]
                extracted = first_page.extract_text() or ""
                ocr_text = sanitize_text(extracted, max_length=4000)
        except Exception:  # noqa: BLE001
            ocr_text = ocr_text
    db.record_evidence(
        sanitized_case,
        file_path.name,
        digest,
        added_by=added_by,
        sealed=False,
        evidence_type=evidence_type or "document",
        tags=tag_string,
        importance=importance or "medium",
        preview_path=str(preview_path) if preview_path else None,
        ocr_text=ocr_text,
    )
    return file_path.name, digest


def list_evidence(db: Database, case_id: str):
    return db.list_evidence(case_id)
