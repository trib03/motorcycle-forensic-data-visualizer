"""Signal registry, unit-axis labels and time-column candidates.

Every plottable quantity gets one entry here.  The `derived` flag separates
quantities read straight from the CSV (`derived=False`) from those computed
later (filtfilt versions, integrated angles).  Header lookup is skipped for
derived signals — they are populated by `csv_loader` after the raw columns
have been parsed.
"""

from typing import Dict, List

SignalConfig = Dict[str, object]

SIGNALS: Dict[str, SignalConfig] = {
    "raw_longitudinal_acceleration": {
        "label": "Raw Longitudinal Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#9A9BC1",
        "preferred_headers": ["raw_ax_mps2"],
        "fallback_headers": ["raw_ax_corr_mps2", "longitudinal_acceleration"],
        "derived": False,
    },
    "raw_longitudinal_acceleration_filtfilt": {
        "label": "Filtered Longitudinal Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#FF0000",
        "preferred_headers": [],
        "fallback_headers": [],
        "derived": True,
    },
    "raw_lateral_acceleration": {
        "label": "Raw Lateral Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#FFA0D3",
        "preferred_headers": ["raw_ay_mps2"],
        "fallback_headers": ["raw_ay_corr_mps2", "lateral_acceleration"],
        "derived": False,
    },
    "raw_lateral_acceleration_filtfilt": {
        "label": "Filtered Lateral Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#80ff00",
        "preferred_headers": [],
        "fallback_headers": [],
        "derived": True,
    },
    "raw_vertical_acceleration": {
        "label": "Raw Vertical Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#9BF6FB",
        "preferred_headers": ["raw_az_mps2"],
        "fallback_headers": ["raw_az_corr_mps2", "vertical_acceleration"],
        "derived": False,
    },
    "raw_vertical_acceleration_filtfilt": {
        "label": "Filtered Vertical Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#00FFFF",
        "preferred_headers": [],
        "fallback_headers": [],
        "derived": True,
    },
    "pitch_from_gyro": {
        "label": "Pitch angle (deg)",
        "unit": "deg",
        "color": "#642BD4",
        "preferred_headers": [],
        "fallback_headers": [],
        "derived": True,
    },
    "roll_from_gyro": {
        "label": "Roll angle (deg)",
        "unit": "deg",
        "color": "#19B078",
        "preferred_headers": [],
        "fallback_headers": [],
        "derived": True,
    },
    "pitch_rate_rads": {
        "label": "Pitch Rate (rad/s)",
        "unit": "rad/s",
        "color": "#B47DED",
        "preferred_headers": [],
        "fallback_headers": [],
        "derived": True,
    },
    "roll_rate_rads": {
        "label": "Roll Rate (rad/s)",
        "unit": "rad/s",
        "color": "#34D399",
        "preferred_headers": [],
        "fallback_headers": [],
        "derived": True,
    },
    "rear_wheel_speed": {
        "label": "Rear Wheel Speed (km/h)",
        "unit": "km/h",
        "color": "#984EA3",
        "preferred_headers": ["hall_r"],
        "fallback_headers": [
            "hall_rear", "rear wheel speed", "rear_wheel_speed",
            "v_rear", "rear_speed", "rear_kmh",
        ],
        "derived": False,
    },
    "front_wheel_speed": {
        "label": "Front Wheel Speed (km/h)",
        "unit": "km/h",
        "color": "#FF7F00",
        "preferred_headers": ["hall_f"],
        "fallback_headers": [
            "hall_front", "front wheel speed", "front_wheel_speed",
            "v_front", "front_speed", "front_kmh",
        ],
        "derived": False,
    },
    "gps_speed": {
        "label": "GPS Speed (km/h)",
        "unit": "km/h",
        "color": "#FF1493",
        "preferred_headers": ["speed_kmh"],
        "fallback_headers": ["gps_speed", "gps_speed_kmh", "gps_speed_km/h", "gps_speed_kph"],
        "derived": False,
    },
}

TIME_HEADERS: List[str] = ["time", "timestamp", "t", "sec", "seconds"]

UNIT_AXIS_LABELS: Dict[str, str] = {
    "m/s²": "Acceleration (m/s²)",
    "deg": "Angle (deg)",
    "km/h": "Speed (km/h)",
    "rad/s": "Angular Rate (rad/s)",
}


def is_derived(key: str) -> bool:
    return bool(SIGNALS.get(key, {}).get("derived", False))
