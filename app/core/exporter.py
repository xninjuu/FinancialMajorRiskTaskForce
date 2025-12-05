from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.storage.db import Database


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def export_case_bundle(db: Database, case_id: str, export_dir: Path) -> tuple[Path, str]:
    export_dir.mkdir(parents=True, exist_ok=True)
    case = db.get_case(case_id)
    if not case:
        raise ValueError("Case not found")

    alerts = [dict(row) for row in db.alerts_for_case(case_id)]
    timeline = db.case_timeline(case_id)
    audit = [dict(row) for row in db.audit_for_target(case_id)]

    bundle: Dict[str, Any] = {
        "case": dict(case),
        "alerts": alerts,
        "timeline": timeline,
        "audit": audit,
        "exported_at": datetime.utcnow().isoformat(),
    }

    html_lines = ["<html><body><h2>Case Export</h2>"]
    html_lines.append(f"<p>Case ID: {case_id}</p>")
    html_lines.append("<h3>Timeline</h3><ul>")
    for event in timeline:
        html_lines.append(
            f"<li>{event['timestamp']} - {event['type']}: {event['description']}</li>"
        )
    html_lines.append("</ul>")
    html_lines.append("</body></html>")

    json_bytes = json.dumps(bundle, default=_serialize, indent=2).encode("utf-8")
    html_bytes = "\n".join(html_lines).encode("utf-8")

    filename = export_dir / f"case_{case_id}.zip"
    with zipfile.ZipFile(filename, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("case.json", json_bytes)
        zf.writestr("case.html", html_bytes)
    hash_value = _sha256_bytes(json_bytes + html_bytes)
    db.record_export(case_id, str(filename), hash_value)
    return filename, hash_value
