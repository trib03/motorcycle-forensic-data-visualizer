"""Tests for motoviz.processing — pure-function coverage."""

import numpy as np
import pytest

from motoviz.processing import (
    apply_imu_mounting_offset,
    butterworth,
    detect_gaps,
    estimate_sample_rate,
    fill_nan,
    integrate_gyro_to_angle_deg,
)


# ---- fill_nan ----

def test_fill_nan_no_nans_returns_copy():
    y = np.array([1.0, 2.0, 3.0])
    out = fill_nan(y)
    assert np.array_equal(out, y)
    # Mutating the result must not touch the input
    out[0] = 99.0
    assert y[0] == 1.0


def test_fill_nan_interpolates_interior_nans():
    y = np.array([1.0, np.nan, np.nan, 4.0])
    out = fill_nan(y)
    assert np.allclose(out, [1.0, 2.0, 3.0, 4.0])


def test_fill_nan_with_only_one_finite_returns_unchanged():
    y = np.array([np.nan, 1.0, np.nan])
    out = fill_nan(y)
    # No interpolation possible with < 2 finite points
    assert np.isnan(out[0]) and np.isnan(out[2])
    assert out[1] == 1.0


# ---- butterworth ----

def test_butterworth_lowpass_attenuates_high_freq():
    sr = 1000.0
    t = np.arange(0, 1.0, 1 / sr)
    y = np.sin(2 * np.pi * 5 * t) + np.sin(2 * np.pi * 200 * t)
    out = butterworth(y, sr, 20.0, order=4, btype="low")
    # The high-frequency component should be heavily attenuated
    high = np.sin(2 * np.pi * 200 * t)
    assert np.std(out - np.sin(2 * np.pi * 5 * t)) < 0.2 * np.std(high)


def test_butterworth_rejects_cutoff_above_nyquist():
    with pytest.raises(ValueError):
        butterworth(np.zeros(100), sample_rate=100.0, cutoff_hz=60.0, btype="low")


def test_butterworth_bandpass_requires_low_below_high():
    with pytest.raises(ValueError):
        butterworth(np.zeros(100), sample_rate=100.0,
                    cutoff_hz=(10.0, 5.0), btype="band")


# ---- gyro integration ----

def test_gyro_integration_zero_input_yields_zero_angle():
    sr = 100.0
    rate = np.zeros(1000)
    rate_filt, angle = integrate_gyro_to_angle_deg(rate, sample_rate=sr)
    assert rate_filt.shape == rate.shape
    assert angle.shape == rate.shape
    assert np.allclose(rate_filt, 0.0)
    assert np.allclose(angle, 0.0, atol=1e-8)


def test_gyro_integration_shapes_match_input():
    sr = 100.0
    rate = np.sin(np.linspace(0, 4 * np.pi, 1000))
    rate_filt, angle = integrate_gyro_to_angle_deg(rate, sample_rate=sr)
    assert rate_filt.shape == rate.shape
    assert angle.shape == rate.shape


def test_gyro_integration_rejects_zero_sample_rate():
    with pytest.raises(ValueError):
        integrate_gyro_to_angle_deg(np.zeros(100), sample_rate=0.0)


# ---- IMU mounting ----

def test_imu_mounting_zero_offset_is_identity():
    pitch = np.array([1.0, 2.0, 3.0])
    roll = np.array([0.5, 1.0, 1.5])
    p, r = apply_imu_mounting_offset(pitch, roll, 0.0, 0.0)
    assert np.allclose(p, pitch) and np.allclose(r, roll)


def test_imu_mounting_handles_none_inputs():
    p, r = apply_imu_mounting_offset(None, np.array([1.0]), 0.0, 5.0)
    assert p is None
    assert r is not None


# ---- sample-rate / gap analysis ----

def test_estimate_sample_rate_uniform():
    x = np.linspace(0, 1, 101)  # 100 Hz
    assert abs(estimate_sample_rate(x) - 100.0) < 1.0


def test_detect_gaps_finds_jump():
    x = np.concatenate([np.linspace(0, 1, 101), np.linspace(2, 3, 101)])
    max_dt, gaps = detect_gaps(x, ratio=3.0)
    assert len(gaps) == 1
    assert max_dt > 0.9


def test_detect_gaps_uniform_returns_empty():
    x = np.linspace(0, 1, 101)
    _, gaps = detect_gaps(x)
    assert gaps == []
