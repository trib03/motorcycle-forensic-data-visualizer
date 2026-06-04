"""Signal processing primitives: NaN handling, smoothing, filtering, gyro
integration with drift correction.

All functions are pure and side-effect-free so they are trivially testable.
"""

from typing import Optional, Tuple

import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.signal import butter, filtfilt, sosfiltfilt


# ---------------------------------------------------------------------------
# NaN handling
# ---------------------------------------------------------------------------

def fill_nan(y: np.ndarray) -> np.ndarray:
    """Replace NaN values with linear interpolation.

    Always returns a fresh array, even when the input has no NaNs, so callers
    can safely mutate the result.  If the input is too short to interpolate
    (zero or one finite sample) the NaNs are left in place.
    """
    out = np.asarray(y, dtype=float).copy()
    if not np.isnan(out).any():
        return out
    nans = np.isnan(out)
    idx = np.where(~nans)[0]
    if idx.size < 2:
        return out
    out[nans] = np.interp(np.where(nans)[0], idx, out[idx])
    return out


# ---------------------------------------------------------------------------
# Butterworth filters
# ---------------------------------------------------------------------------

def butterworth(
    y: np.ndarray,
    sample_rate: float,
    cutoff_hz,
    order: int = 4,
    btype: str = "low",
) -> np.ndarray:
    """Apply a zero-phase Butterworth filter (filtfilt) to ``y``.

    ``cutoff_hz`` is a scalar for "low"/"high" and a 2-tuple for "band"/"bandstop".
    Raises ``ValueError`` if any cutoff is outside (0, Nyquist).
    """
    if sample_rate is None or sample_rate <= 0:
        raise ValueError("A positive sample rate is required for Butterworth filtering.")
    nyq = sample_rate / 2.0

    if btype in ("low", "high"):
        if cutoff_hz <= 0 or cutoff_hz >= nyq:
            raise ValueError(
                f"Cutoff ({cutoff_hz} Hz) must be in (0, {nyq:.3f} Hz)."
            )
        wn = cutoff_hz / nyq
    elif btype in ("band", "bandstop"):
        low, high = cutoff_hz
        if low <= 0 or high >= nyq or low >= high:
            raise ValueError(
                f"Band cutoffs ({low}, {high}) Hz must satisfy 0 < low < high < {nyq:.3f}."
            )
        wn = [low / nyq, high / nyq]
    else:
        raise ValueError(f"Unknown filter type: {btype}")

    b, a = butter(order, wn, btype=btype)
    return filtfilt(b, a, fill_nan(y))


# ---------------------------------------------------------------------------
# Gyro integration with drift correction
# ---------------------------------------------------------------------------

def integrate_gyro_to_angle_deg(
    gyro_rads: np.ndarray,
    sample_rate: float,
    lowpass_cutoff_hz: float = 8.0,
    hp_drift_cutoff_hz: float = 0.1,
    anchor_window_sec: float = 1.0,
    filter_order: int = 4,
) -> Tuple[np.ndarray, np.ndarray]:
    """Low-pass a gyro stream, then integrate it (uniform 1/sr grid) into an
    angle in degrees, and remove integration drift with a high-pass.

    Returns ``(filtered_rate_rads, angle_deg)``.

    The uniform time grid avoids the small bias you get when integrating
    against an interpolated CSV timestamp column that has occasional gaps.
    """
    if sample_rate is None or sample_rate <= 0:
        raise ValueError("Gyro integration requires a positive sample rate.")
    nyq = sample_rate / 2.0
    dt = 1.0 / sample_rate

    gyro = fill_nan(gyro_rads)
    if lowpass_cutoff_hz < nyq:
        rate_filt = butterworth(gyro, sample_rate, lowpass_cutoff_hz,
                                order=filter_order, btype="low")
    else:
        rate_filt = gyro

    angle_rad = cumulative_trapezoid(rate_filt, dx=dt, initial=0.0)
    angle_deg = np.rad2deg(angle_rad)

    if hp_drift_cutoff_hz < nyq:
        sos = butter(2, hp_drift_cutoff_hz / nyq, btype="high", output="sos")
        hp = sosfiltfilt(sos, angle_deg)
        anchor_n = max(5, min(int(round(anchor_window_sec * sample_rate)), len(hp) // 6))
        angle_out = hp - float(np.mean(hp[:anchor_n]))
    else:
        # Fallback: subtract linear endpoint drift
        drift = np.linspace(0.0, angle_deg[-1], len(angle_deg))
        angle_out = angle_deg - drift

    return rate_filt, angle_out


# ---------------------------------------------------------------------------
# IMU mounting compensation
# ---------------------------------------------------------------------------

def apply_imu_mounting_offset(
    gyro_pitch_rads: Optional[np.ndarray],
    gyro_roll_rads: Optional[np.ndarray],
    pitch_offset_deg: float,
    roll_offset_deg: float,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Small-angle compensation for IMU mounting offsets.

    Treats the offsets as a rotation in the bike's frame: an IMU rotated by a
    small angle picks up cross-talk between its sensed axes.  For typical
    mounting errors (a few degrees) the small-angle approximation is well
    within the noise floor of the signals.
    """
    if pitch_offset_deg == 0.0 and roll_offset_deg == 0.0:
        return gyro_pitch_rads, gyro_roll_rads

    c_p = np.cos(np.deg2rad(pitch_offset_deg))
    s_p = np.sin(np.deg2rad(pitch_offset_deg))
    c_r = np.cos(np.deg2rad(roll_offset_deg))
    s_r = np.sin(np.deg2rad(roll_offset_deg))

    new_pitch = None
    new_roll = None
    if gyro_pitch_rads is not None and gyro_roll_rads is not None:
        # 2D rotation: combined small rotation about the heading axis
        new_pitch = c_r * gyro_pitch_rads - s_r * gyro_roll_rads
        new_roll = s_p * gyro_pitch_rads + c_p * gyro_roll_rads
    elif gyro_pitch_rads is not None:
        new_pitch = c_r * gyro_pitch_rads
    elif gyro_roll_rads is not None:
        new_roll = c_p * gyro_roll_rads
    return new_pitch, new_roll


# ---------------------------------------------------------------------------
# Sample-rate / gap analysis
# ---------------------------------------------------------------------------

def estimate_sample_rate(x: np.ndarray) -> Optional[float]:
    finite = x[np.isfinite(x)]
    if finite.size < 2:
        return None
    diffs = np.diff(finite)
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        return None
    dt = float(np.median(diffs))
    return 1.0 / dt if dt > 0 else None


def detect_gaps(x: np.ndarray, ratio: float = 3.0) -> Tuple[float, list]:
    """Find time-axis gaps where dt exceeds ``ratio`` times the median dt.

    Returns ``(max_dt, [(t_start, t_end), ...])`` with one entry per gap.
    """
    finite_mask = np.isfinite(x)
    finite = x[finite_mask]
    if finite.size < 3:
        return 0.0, []
    diffs = np.diff(finite)
    positive = diffs[diffs > 0]
    if positive.size == 0:
        return 0.0, []
    med = float(np.median(positive))
    if med <= 0:
        return float(np.max(diffs)) if diffs.size else 0.0, []
    threshold = med * ratio
    gap_indices = np.where(diffs > threshold)[0]
    gaps = [(float(finite[i]), float(finite[i + 1])) for i in gap_indices]
    return float(np.max(diffs)) if diffs.size else 0.0, gaps
