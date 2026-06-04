"""Thin wrapper around QSettings for user preferences and recent files."""

from typing import List, Optional

from PySide6.QtCore import QByteArray, QSettings


_ORG = "HAN"
_APP = "MotoForensicVisualizer"
_RECENT_KEY = "recent_files"
_LAST_DIR_KEY = "last_directory"
_GEOMETRY_KEY = "window/geometry"
_STATE_KEY = "window/state"
_MAIN_SPLIT_KEY = "window/main_splitter"
_TABLE_SPLIT_KEY = "window/tables_splitter"
_DARK_THEME_KEY = "view/dark_theme"
_CROSSHAIR_KEY = "view/crosshair"
_REGION_KEY = "view/region"
_SIGNAL_ASSIGN_KEY = "view/signal_assignment"
_ASSIGN_VERSION_KEY = "view/signal_assignment_version"

# Bump this when the unit-based default plot assignment changes so existing
# users get the new defaults applied automatically.
_CURRENT_ASSIGN_VERSION = 2


def _qs() -> QSettings:
    return QSettings(_ORG, _APP)


# ---- Directory / file MRU ----

def last_directory() -> str:
    return str(_qs().value(_LAST_DIR_KEY, "", type=str))


def set_last_directory(path: str) -> None:
    _qs().setValue(_LAST_DIR_KEY, path)


def recent_files(limit: int = 10) -> List[str]:
    raw = _qs().value(_RECENT_KEY, [], type=list)
    out = [str(p) for p in raw if p]
    return out[:limit]


def push_recent_file(path: str, limit: int = 10) -> List[str]:
    if not path:
        return recent_files(limit)
    cur = [p for p in recent_files(limit * 2) if p != path]
    cur.insert(0, path)
    cur = cur[:limit]
    _qs().setValue(_RECENT_KEY, cur)
    return cur


def clear_recent_files() -> None:
    _qs().setValue(_RECENT_KEY, [])


# ---- Window state ----

def save_geometry(geom: QByteArray) -> None:
    _qs().setValue(_GEOMETRY_KEY, geom)


def load_geometry() -> Optional[QByteArray]:
    v = _qs().value(_GEOMETRY_KEY)
    return v if isinstance(v, QByteArray) and not v.isEmpty() else None


def save_state(state: QByteArray) -> None:
    _qs().setValue(_STATE_KEY, state)


def load_state() -> Optional[QByteArray]:
    v = _qs().value(_STATE_KEY)
    return v if isinstance(v, QByteArray) and not v.isEmpty() else None


def save_splitter(key: str, state: QByteArray) -> None:
    _qs().setValue(f"window/{key}", state)


def load_splitter(key: str) -> Optional[QByteArray]:
    v = _qs().value(f"window/{key}")
    return v if isinstance(v, QByteArray) and not v.isEmpty() else None


# ---- View toggles ----

def dark_theme() -> bool:
    return bool(_qs().value(_DARK_THEME_KEY, False, type=bool))


def set_dark_theme(on: bool) -> None:
    _qs().setValue(_DARK_THEME_KEY, bool(on))


def crosshair_enabled() -> bool:
    return bool(_qs().value(_CROSSHAIR_KEY, True, type=bool))


def set_crosshair_enabled(on: bool) -> None:
    _qs().setValue(_CROSSHAIR_KEY, bool(on))


def region_enabled() -> bool:
    return bool(_qs().value(_REGION_KEY, False, type=bool))


def set_region_enabled(on: bool) -> None:
    _qs().setValue(_REGION_KEY, bool(on))


def signal_assignment() -> dict:
    raw = _qs().value(_SIGNAL_ASSIGN_KEY, {})
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except Exception:
            continue
    return out


def set_signal_assignment(assignment: dict) -> None:
    _qs().setValue(_SIGNAL_ASSIGN_KEY,
                   {str(k): int(v) for k, v in assignment.items()})


def maybe_migrate_assignment() -> bool:
    """One-time migration: wipe the stored per-signal plot assignment when
    the unit-based default scheme has changed.  Returns True if a migration
    was performed."""
    try:
        v = int(_qs().value(_ASSIGN_VERSION_KEY, 1))
    except Exception:
        v = 1
    if v < _CURRENT_ASSIGN_VERSION:
        _qs().remove(_SIGNAL_ASSIGN_KEY)
        _qs().setValue(_ASSIGN_VERSION_KEY, _CURRENT_ASSIGN_VERSION)
        return True
    return False
