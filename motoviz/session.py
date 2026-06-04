"""Forensic session export / import.

Captures everything a reviewer needs to reproduce the plotted view from the
raw CSV: which file was loaded (with SHA-256 so they can verify the file
hasn't been modified), the calibration applied, the signals that were
displayed, the time window the user was looking at, the plot layout, the app
version, and a timestamp.

The JSON is human-readable so it can be archived alongside the CSV as a
paper trail.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __app_name__, __version__
from .calibration import Calibration


def sha256_of_file(path: str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def build_session_dict(
    csv_path: Optional[str],
    sample_rate: Optional[float],
    row_count: int,
    calibration: Calibration,
    selected_signals: List[str],
    view_range: Optional[tuple],
    region_range: Optional[tuple] = None,
) -> Dict[str, Any]:
    csv_info: Dict[str, Any] = {
        "path": csv_path,
        "rows": int(row_count),
        "sample_rate_hz": sample_rate,
    }
    if csv_path and Path(csv_path).exists():
        try:
            csv_info["sha256"] = sha256_of_file(csv_path)
            csv_info["size_bytes"] = Path(csv_path).stat().st_size
        except Exception:
            pass

    return {
        "app": __app_name__,
        "app_version": __version__,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "csv": csv_info,
        "calibration": asdict(calibration),
        "selected_signals": list(selected_signals),
        "view_range_s": list(view_range) if view_range else None,
        "region_range_s": list(region_range) if region_range else None,
    }


def save_session(path: str, payload: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_session(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
