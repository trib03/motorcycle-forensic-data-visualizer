"""CSV loading.

Split deliberately into two phases:

1. ``parse_raw_series`` reads the file and pulls every recognised CSV column
   into a numpy array.  No filtering or integration happens here.
2. ``compute_derived_series`` takes the parsed raw signals and a
   :class:`Calibration` and produces the filtfilt versions, pitch/roll rates
   and integrated angles.

Splitting them means the user can change the calibration profile and re-derive
the signals without re-reading the CSV.
"""

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .calibration import Calibration
from .processing import (
    apply_imu_mounting_offset,
    butterworth,
    detect_gaps,
    estimate_sample_rate,
    fill_nan,
    integrate_gyro_to_angle_deg,
)
from .signals import SIGNALS, TIME_HEADERS, is_derived


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class LoadedCSV:
    headers: List[str]
    rows: List[List[str]]
    x: np.ndarray
    series: Dict[str, np.ndarray]
    sample_rate: Optional[float] = field(default=None)
    gaps: List[Tuple[float, float]] = field(default_factory=list)
    max_dt: float = 0.0
    source_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_name(s: str) -> str:
    allowed = ("_", " ")
    return "".join(ch.lower() for ch in s.strip() if ch.isalnum() or ch in allowed)


def parse_float(value: str) -> float:
    try:
        return float(value.strip().replace(",", "."))
    except Exception:
        return np.nan


def find_column(headers: List[str], candidates: List[str]) -> Optional[int]:
    normalized_headers = [normalize_name(h) for h in headers]
    normalized_candidates = [normalize_name(c) for c in candidates]
    for cand in normalized_candidates:
        for i, h in enumerate(normalized_headers):
            if h == cand:
                return i
    for cand in normalized_candidates:
        for i, h in enumerate(normalized_headers):
            if cand in h:
                return i
    return None


def parse_float_column(rows: List[List[str]], col: int) -> np.ndarray:
    data = np.empty(len(rows), dtype=float)
    for i, row in enumerate(rows):
        data[i] = parse_float(row[col]) if col < len(row) else np.nan
    return data


# ---------------------------------------------------------------------------
# Phase 1: parse the CSV file
# ---------------------------------------------------------------------------

def parse_raw_series(path: str) -> Tuple[List[str], List[List[str]], np.ndarray, Dict[str, np.ndarray]]:
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        all_rows = list(csv.reader(f))
    if len(all_rows) < 2:
        raise ValueError("CSV appears empty or has no data rows.")

    headers = all_rows[0]
    rows = all_rows[1:]

    time_col = find_column(headers, TIME_HEADERS)
    if time_col is not None:
        x = parse_float_column(rows, time_col)
        if np.all(np.isnan(x)):
            x = np.arange(len(rows), dtype=float)
    else:
        x = np.arange(len(rows), dtype=float)

    series: Dict[str, np.ndarray] = {}
    for key, cfg in SIGNALS.items():
        if is_derived(key):
            continue
        col = find_column(headers, cfg["preferred_headers"])
        if col is None:
            col = find_column(headers, cfg["fallback_headers"])
        if col is not None:
            series[key] = parse_float_column(rows, col)

    return headers, rows, x, series


# ---------------------------------------------------------------------------
# Phase 2: compute derived signals from raw series + calibration
# ---------------------------------------------------------------------------

def _convert_hall_to_kmh(series: Dict[str, np.ndarray], cal: Calibration) -> None:
    for key, circ in [
        ("front_wheel_speed", cal.front_wheel_circumference_m),
        ("rear_wheel_speed", cal.rear_wheel_circumference_m),
    ]:
        if key in series and cal.abs_ring_slots > 0:
            series[key] = series[key] / cal.abs_ring_slots * circ * 3.6


def _compute_accel_filtfilt(
    series: Dict[str, np.ndarray], sample_rate: float, cal: Calibration
) -> None:
    pairs = [
        ("raw_longitudinal_acceleration", "raw_longitudinal_acceleration_filtfilt"),
        ("raw_lateral_acceleration", "raw_lateral_acceleration_filtfilt"),
        ("raw_vertical_acceleration", "raw_vertical_acceleration_filtfilt"),
    ]
    for src, dst in pairs:
        if src not in series:
            continue
        try:
            series[dst] = butterworth(
                series[src], sample_rate, cal.accel_filter_cutoff_hz,
                order=cal.filtfilt_order, btype="low",
            )
        except Exception:
            # Cutoff above Nyquist or numerical failure — skip silently but
            # leave the raw signal available.
            pass


def _compute_gyro_signals(
    headers: List[str],
    rows: List[List[str]],
    series: Dict[str, np.ndarray],
    sample_rate: float,
    cal: Calibration,
) -> None:
    pitch_col = find_column(headers, ["gyro_y_rads"])
    roll_col = find_column(headers, ["gyro_x_rads"])

    pitch_raw = parse_float_column(rows, pitch_col) if pitch_col is not None else None
    roll_raw = parse_float_column(rows, roll_col) if roll_col is not None else None

    if pitch_raw is None and roll_raw is None:
        return

    pitch_raw_filled = fill_nan(pitch_raw) if pitch_raw is not None else None
    roll_raw_filled = fill_nan(roll_raw) if roll_raw is not None else None

    pitch_raw_filled, roll_raw_filled = apply_imu_mounting_offset(
        pitch_raw_filled, roll_raw_filled,
        cal.imu_pitch_offset_deg, cal.imu_roll_offset_deg,
    )

    if pitch_raw_filled is not None:
        try:
            rate, angle = integrate_gyro_to_angle_deg(
                pitch_raw_filled,
                sample_rate=sample_rate,
                lowpass_cutoff_hz=cal.gyro_filter_cutoff_hz,
                hp_drift_cutoff_hz=cal.gyro_drift_hp_hz,
                anchor_window_sec=cal.gyro_drift_anchor_sec,
                filter_order=cal.filtfilt_order,
            )
            series["pitch_rate_rads"] = rate
            series["pitch_from_gyro"] = angle
        except Exception:
            pass

    if roll_raw_filled is not None:
        try:
            rate, angle = integrate_gyro_to_angle_deg(
                roll_raw_filled,
                sample_rate=sample_rate,
                lowpass_cutoff_hz=cal.gyro_filter_cutoff_hz,
                hp_drift_cutoff_hz=cal.gyro_drift_hp_hz,
                anchor_window_sec=cal.gyro_drift_anchor_sec,
                filter_order=cal.filtfilt_order,
            )
            series["roll_rate_rads"] = rate
            series["roll_from_gyro"] = angle
        except Exception:
            pass


def compute_derived_series(
    headers: List[str],
    rows: List[List[str]],
    x: np.ndarray,
    raw_series: Dict[str, np.ndarray],
    cal: Calibration,
) -> Tuple[Dict[str, np.ndarray], Optional[float]]:
    """Apply calibration to raw series and produce the filtered/derived ones."""
    series = {k: np.array(v, copy=True) for k, v in raw_series.items()}

    _convert_hall_to_kmh(series, cal)

    sample_rate = estimate_sample_rate(x)
    if sample_rate is not None and sample_rate > 0:
        _compute_accel_filtfilt(series, sample_rate, cal)
        _compute_gyro_signals(headers, rows, series, sample_rate, cal)

    return series, sample_rate


# ---------------------------------------------------------------------------
# Public one-shot loader
# ---------------------------------------------------------------------------

def load_csv(path: str, calibration: Optional[Calibration] = None) -> LoadedCSV:
    cal = calibration or Calibration()
    headers, rows, x, raw_series = parse_raw_series(path)
    series, sample_rate = compute_derived_series(headers, rows, x, raw_series, cal)
    max_dt, gaps = detect_gaps(x)
    return LoadedCSV(
        headers=headers,
        rows=rows,
        x=x,
        series=series,
        sample_rate=sample_rate,
        gaps=gaps,
        max_dt=max_dt,
        source_path=path,
    )


def recompute_with_calibration(loaded: LoadedCSV, cal: Calibration) -> LoadedCSV:
    """Re-derive signals after a calibration change, without re-reading the CSV."""
    raw_series = {
        k: v for k, v in loaded.series.items() if not is_derived(k)
    }
    # Re-source the wheel speeds: we stored them already in km/h, so we have to
    # work back to the raw column (or just re-parse).  Simpler: re-parse just
    # the raw columns from the rows.
    if loaded.headers and loaded.rows:
        for key in ("front_wheel_speed", "rear_wheel_speed"):
            cfg = SIGNALS[key]
            col = find_column(loaded.headers, cfg["preferred_headers"])
            if col is None:
                col = find_column(loaded.headers, cfg["fallback_headers"])
            if col is not None:
                raw_series[key] = parse_float_column(loaded.rows, col)

    series, sample_rate = compute_derived_series(
        loaded.headers, loaded.rows, loaded.x, raw_series, cal,
    )
    max_dt, gaps = detect_gaps(loaded.x)
    return LoadedCSV(
        headers=loaded.headers,
        rows=loaded.rows,
        x=loaded.x,
        series=series,
        sample_rate=sample_rate,
        gaps=gaps,
        max_dt=max_dt,
        source_path=loaded.source_path,
    )
