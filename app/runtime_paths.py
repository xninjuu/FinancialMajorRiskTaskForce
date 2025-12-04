from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List


def _candidate_config_dirs() -> List[Path]:
    env_dir = os.getenv("CODEX_CONFIG_DIR")
    candidates: List[Path] = []
    if env_dir:
        candidates.append(Path(env_dir))

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "config")
        bundle_dir = Path(getattr(sys, "_MEIPASS", exe_dir))
        candidates.append(bundle_dir / "config")

    project_root = Path(__file__).resolve().parent.parent
    candidates.append(project_root / "config")
    return candidates


def resolve_config_path(filename: str) -> Path | None:
    for base in _candidate_config_dirs():
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_runtime_file(name: str) -> Path:
    return runtime_dir() / name


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
