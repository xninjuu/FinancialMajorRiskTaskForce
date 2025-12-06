from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.storage.db import Database


def export_case_json(db: Database, case_id: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    case = db.get_case(case_id)
    if not case:
        raise ValueError("Case not found")
    alerts = db.alerts_for_case(case_id)
    notes = db.case_notes(case_id)
    bundle: Dict[str, Any] = {
        "case": dict(case),
        "alerts": [dict(a) for a in alerts],
        "notes": [note.__dict__ for note in notes],
    }
    out_path = output_dir / f"case_{case_id}.json"
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return out_path
