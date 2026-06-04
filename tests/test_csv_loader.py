"""Tests for motoviz.csv_loader."""

import csv
import os

import numpy as np

from motoviz.calibration import Calibration
from motoviz.csv_loader import (
    find_column,
    load_csv,
    normalize_name,
    parse_float,
)


def test_normalize_name_lowercases_and_filters():
    assert normalize_name("  Raw_AX MPS2  ") == "raw_ax mps2"
    assert normalize_name("Speed[km/h]") == "speedkmh"


def test_parse_float_accepts_comma_decimal():
    assert parse_float("1,5") == 1.5
    assert parse_float("  3.25 ") == 3.25
    assert np.isnan(parse_float("not a number"))


def test_find_column_exact_match_first():
    headers = ["time", "raw_ax_mps2", "raw_ax_corr_mps2"]
    idx = find_column(headers, ["raw_ax_mps2", "raw_ax_corr_mps2"])
    assert idx == 1


def test_find_column_substring_fallback():
    headers = ["seconds", "lateral_acceleration_mps2"]
    idx = find_column(headers, ["lateral_acceleration"])
    assert idx == 1


def test_find_column_no_match():
    assert find_column(["a", "b"], ["c"]) is None


def _write_csv(tmp_path, rows):
    path = os.path.join(tmp_path, "log.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)
    return path


def test_load_csv_basic(tmp_path):
    rows = [
        ["time", "raw_ax_mps2", "hall_f"],
    ]
    for i in range(100):
        rows.append([i * 0.01, 0.1 * np.sin(i / 5), 100.0])
    path = _write_csv(tmp_path, rows)
    loaded = load_csv(path, calibration=Calibration())

    assert "raw_longitudinal_acceleration" in loaded.series
    assert "front_wheel_speed" in loaded.series
    # Front wheel speed should be the constant Hz value converted into km/h
    expected_kmh = 100.0 / 40 * 1.89 * 3.6
    assert abs(loaded.series["front_wheel_speed"][0] - expected_kmh) < 1e-6
    assert loaded.sample_rate is not None
    assert abs(loaded.sample_rate - 100.0) < 1.0


def test_load_csv_with_gap(tmp_path):
    rows = [["time", "raw_ax_mps2"]]
    for i in range(50):
        rows.append([i * 0.01, 0.0])
    for i in range(50):
        rows.append([1.0 + i * 0.01, 0.0])  # 0.5s gap
    path = _write_csv(tmp_path, rows)
    loaded = load_csv(path)
    assert len(loaded.gaps) >= 1
    assert loaded.max_dt > 0.4


def test_load_csv_alternate_calibration(tmp_path):
    rows = [["time", "hall_r"]]
    for i in range(50):
        rows.append([i * 0.01, 200.0])
    path = _write_csv(tmp_path, rows)
    cal = Calibration(rear_wheel_circumference_m=2.0, abs_ring_slots=50)
    loaded = load_csv(path, calibration=cal)
    expected = 200.0 / 50 * 2.0 * 3.6
    assert abs(loaded.series["rear_wheel_speed"][0] - expected) < 1e-6
