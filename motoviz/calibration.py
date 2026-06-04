"""Calibration profile: bike geometry + IMU offsets + filter cutoffs.

The values here used to be hard-coded constants buried in the loader.  Pulling
them out into an editable JSON profile means a different bike / different ABS
ring count produces correct values without recompiling, and means each
forensic session can record which calibration was used.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths


@dataclass
class Calibration:
    name: str = "Default"

    # Wheel geometry — used to convert hall-sensor Hz into km/h
    front_wheel_circumference_m: float = 1.89
    rear_wheel_circumference_m: float = 1.98
    abs_ring_slots: int = 40

    # IMU mounting compensation (small-angle).  Set to 0 for an ideally mounted IMU.
    imu_pitch_offset_deg: float = 0.0
    imu_roll_offset_deg: float = 0.0

    # Default filter cutoffs for the precomputed signals (Hz)
    accel_filter_cutoff_hz: float = 5.0
    gyro_filter_cutoff_hz: float = 8.0
    filtfilt_order: int = 4

    # Gyro drift correction
    gyro_drift_hp_hz: float = 0.1
    gyro_drift_anchor_sec: float = 1.0

    # ---- IO ----
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Calibration":
        data = json.loads(text)
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        return cls.from_json(path.read_text(encoding="utf-8"))


# ---- App-data location helpers ----

def app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = str(Path.home() / ".motoviz")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_calibration_path() -> Path:
    return app_data_dir() / "calibration.json"


def load_default_calibration() -> Calibration:
    path = default_calibration_path()
    if path.exists():
        try:
            return Calibration.load(path)
        except Exception:
            pass
    return Calibration()


def save_default_calibration(cal: Calibration) -> None:
    cal.save(default_calibration_path())


def calibration_presets_dir() -> Path:
    d = app_data_dir() / "calibration_presets"
    d.mkdir(parents=True, exist_ok=True)
    return d
