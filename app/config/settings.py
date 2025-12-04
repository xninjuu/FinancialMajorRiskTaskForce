from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from app.runtime_paths import resolve_config_path, runtime_dir, ensure_parent_dir


@dataclass
class AppSettings:
    db_path: Path
    indicators_path: Path
    thresholds_path: Path
    session_timeout_minutes: int = 15


class SettingsLoader:
    @staticmethod
    def _resolve_file(filename: str, *, required: bool = True) -> Path:
        resolved = resolve_config_path(filename)
        if not resolved:
            if required:
                raise FileNotFoundError(
                    f"Required config file '{filename}' not found. Place it in ./config or alongside the executable."
                )
            runtime_candidate = runtime_dir() / "config" / filename
            ensure_parent_dir(runtime_candidate)
            return runtime_candidate
        return resolved

    @classmethod
    def load(cls) -> AppSettings:
        indicators_path = cls._resolve_file("indicators.json")
        thresholds_path = cls._resolve_file("thresholds.json")
        db_path = Path(os.getenv("CODEX_DB_PATH", runtime_dir() / "codex.db"))
        ensure_parent_dir(db_path)
        return AppSettings(
            db_path=db_path,
            indicators_path=indicators_path,
            thresholds_path=thresholds_path,
            session_timeout_minutes=int(os.getenv("CODEX_SESSION_TIMEOUT_MINUTES", "15")),
        )

    @staticmethod
    def load_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
