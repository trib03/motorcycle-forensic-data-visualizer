# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Motorcycle Forensic Data Visualizer** — a single-file Python desktop app (`App.py`) for loading, plotting, and exporting forensic motorcycle sensor data from CSV files. Packaged as a Windows installer via PyInstaller + Inno Setup.

## Development Commands

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run the app locally
python App.py

# Install dependencies
pip install -r Requirements.txt

# Clean old build artifacts
Remove-Item -Recurse -Force build, dist, installer_output -ErrorAction SilentlyContinue

# Build Windows executable
pyinstaller --noconfirm --windowed --icon=assets/icon.ico --name "Motorcycle Forensic Data Visualizer" App.py
```

After rebuilding the executable, open `installer.iss` in **Inno Setup Compiler** and press **F9** to produce `installer_output/MotorcycleForensicDataVisualizer-Setup.exe`.

## Architecture

All application code lives in a single file, `App.py`, organized into clearly separated sections:

- **`SIGNALS` dict** — the canonical registry of every plottable signal. Each entry declares `label`, `unit`, `color`, `preferred_headers` (exact CSV column name matches), and `fallback_headers` (substring/alias matches). Adding a new signal means adding one entry here; the rest of the app adapts automatically.

- **`load_csv` / `find_column` / `parse_float_column`** — CSV parsing layer. `find_column` does normalized exact-match first, then substring fallback, making header matching tolerant of casing and spacing variations.

- **`LoadedCSV` dataclass** — parsed data container: raw headers/rows, the time array `x`, and a `series` dict mapping signal keys to numpy arrays.

- **`CSVTableModel` / `SignalStatsTableModel`** — Qt table models wrapping `QAbstractTableModel` to display raw CSV data and per-signal Min/Avg/Max statistics.

- **`MainWindow`** — the entire UI in one class. Key design points:
  - Uses **three independent pyqtgraph `ViewBox`es** (left, right1, right2) to support up to three different unit groups (e.g., m/s², deg, km/h) on separate Y-axes simultaneously.
  - `unit_order` list (max 3 entries) drives which viewbox each unit maps to via `get_slot_for_unit`.
  - Right-axis grid lines are manually drawn as `pg.InfiniteLine` objects (stored in `right_axis_grids`) because pyqtgraph's built-in grid only tracks the main viewbox.
  - `resource_path()` handles both dev and PyInstaller-bundled (`sys._MEIPASS`) asset paths.

## Release Workflow

1. Test locally with `python App.py`
2. Clean `build/`, `dist/`, `installer_output/`
3. Run PyInstaller (command above)
4. Update `AppVersion` in `installer.iss`
5. Compile installer in Inno Setup (F9)
6. Distribute `installer_output/MotorcycleForensicDataVisualizer-Setup.exe`

**Do not distribute** the bare `.exe` from `dist/` — it depends on all sibling files in that folder.
