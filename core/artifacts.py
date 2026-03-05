"""Helpers for canonical pipeline artifact persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import get_settings


def artifact_dir_for_run(run_id: str, *, base_dir: Path | None = None) -> Path:
    root = base_dir or (get_settings().runs_dir / "artifacts")
    target = root / run_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json_artifact(
    run_id: str,
    filename: str,
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> Path:
    target_dir = artifact_dir_for_run(run_id, base_dir=base_dir)
    path = target_dir / filename
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return path
