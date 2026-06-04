"""Tests for the SIGNALS registry, Calibration JSON roundtrip, and session
manifest."""

import json

from motoviz.calibration import Calibration
from motoviz.session import build_session_dict, load_session, save_session
from motoviz.signals import SIGNALS, UNIT_AXIS_LABELS, is_derived


# ---- SIGNALS registry sanity ----

def test_every_signal_has_required_keys():
    required = {"label", "unit", "color", "preferred_headers",
                "fallback_headers", "derived"}
    for key, cfg in SIGNALS.items():
        missing = required - set(cfg.keys())
        assert not missing, f"{key} missing {missing}"


def test_every_unit_has_an_axis_label():
    units = {cfg["unit"] for cfg in SIGNALS.values()}
    assert units <= set(UNIT_AXIS_LABELS)


def test_derived_signals_have_no_csv_headers():
    for key, cfg in SIGNALS.items():
        if cfg["derived"]:
            assert not cfg["preferred_headers"]
            assert not cfg["fallback_headers"]


def test_is_derived_returns_correct_value():
    assert is_derived("pitch_from_gyro") is True
    assert is_derived("raw_longitudinal_acceleration") is False
    assert is_derived("nonexistent_key") is False


# ---- Calibration JSON roundtrip ----

def test_calibration_roundtrip():
    cal = Calibration(
        name="MyBike",
        front_wheel_circumference_m=1.95,
        rear_wheel_circumference_m=2.02,
        abs_ring_slots=48,
    )
    text = cal.to_json()
    parsed = Calibration.from_json(text)
    assert parsed.name == "MyBike"
    assert parsed.front_wheel_circumference_m == 1.95
    assert parsed.abs_ring_slots == 48


def test_calibration_ignores_unknown_keys():
    text = json.dumps({"name": "X", "unknown_field": 999,
                       "front_wheel_circumference_m": 1.0})
    cal = Calibration.from_json(text)
    assert cal.name == "X"
    assert cal.front_wheel_circumference_m == 1.0


# ---- Session manifest ----

def test_session_roundtrip(tmp_path):
    sess_path = str(tmp_path / "session.json")
    payload = build_session_dict(
        csv_path=None,
        sample_rate=100.0,
        row_count=1234,
        calibration=Calibration(),
        selected_signals=["raw_longitudinal_acceleration"],
        view_range=(0.0, 10.0),
    )
    save_session(sess_path, payload)
    again = load_session(sess_path)
    assert again["csv"]["sample_rate_hz"] == 100.0
    assert again["selected_signals"] == ["raw_longitudinal_acceleration"]
    assert again["view_range_s"] == [0.0, 10.0]
