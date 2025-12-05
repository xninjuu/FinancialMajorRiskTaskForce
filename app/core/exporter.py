from __future__ import annotations

import hashlib
import hashlib
import json
import hashlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from app.storage.db import Database


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _redact_value(value: str) -> str:
    if not value:
        return value
    return f"***{hashlib.sha256(value.encode('utf-8')).hexdigest()[:10]}"


def _redact_record(record: Dict[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    sanitized = dict(record)
    for field in fields:
        if field in sanitized:
            sanitized[field] = _redact_value(str(sanitized[field]))
    return sanitized


def export_case_bundle(
    db: Database,
    case_id: str,
    export_dir: Path,
    *,
    redacted: bool = False,
    watermark: str | None = None,
) -> tuple[Path, str]:
    export_dir.mkdir(parents=True, exist_ok=True)
    case = db.get_case(case_id)
    if not case:
        raise ValueError("Case not found")

    alerts = [dict(row) for row in db.alerts_for_case(case_id)]
    timeline = db.case_timeline(case_id)
    audit = [dict(row) for row in db.audit_for_target(case_id)]
    evidence = [dict(row) for row in db.list_evidence(case_id)]
    correlations = [dict(row) for row in db.list_correlations(alert["id"]) for alert in alerts]

    if redacted:
        alerts = [_redact_record(alert, {"transaction_id", "case_id"}) for alert in alerts]
        timeline = [_redact_record(event, {"description"}) for event in timeline]
        audit = [_redact_record(row, {"details", "username"}) for row in audit]
        evidence = [_redact_record(item, {"filename", "hash", "added_by"}) for item in evidence]

    bundle: Dict[str, Any] = {
        "case": dict(case),
        "alerts": alerts,
        "timeline": timeline,
        "audit": audit,
        "evidence": evidence,
        "correlations": correlations,
        "watermark": watermark,
        "redacted": redacted,
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
    if watermark:
        html_lines.append(f"<p style='color:red;'>Watermark: {watermark}</p>")
    html_lines.append("<h3>Evidence</h3><ul>")
    for ev in evidence:
        html_lines.append(f"<li>{ev.get('filename')} ({ev.get('hash')})</li>")
    html_lines.append("</ul>")
    html_lines.append("</body></html>")

    json_bytes = json.dumps(bundle, default=_serialize, indent=2).encode("utf-8")
    html_bytes = "\n".join(html_lines).encode("utf-8")

    filename = export_dir / f"case_{case_id}.zip"
    with zipfile.ZipFile(filename, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("case.json", json_bytes)
        zf.writestr("case.html", html_bytes)
    hash_value = _sha256_bytes(json_bytes + html_bytes)
    manifest = json.dumps(
        {
            "case_id": case_id,
            "hash": hash_value,
            "redacted": redacted,
            "watermark": watermark,
            "evidence_count": len(evidence),
            "correlation_edges": len(correlations),
        },
        indent=2,
    )
    db.record_export(case_id, str(filename), hash_value, redacted=redacted, watermark=watermark, manifest=manifest)
    return filename, hash_value
