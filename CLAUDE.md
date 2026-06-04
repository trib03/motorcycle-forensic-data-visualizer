# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Motorcycle Forensic Data Visualizer** — a PySide6 desktop app for loading, plotting, and exporting forensic motorcycle sensor data from CSV files. Packaged as a Windows installer via PyInstaller + Inno Setup.

`App.py` is a thin entry point that calls `motoviz.main_window.main()`; all application code lives in the `motoviz` package. `App.py` stays at the repo root because it is the PyInstaller entry script referenced from the `.spec`.

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

After rebuilding the executable, open `packaging/installer.iss` in **Inno Setup Compiler** and press **F9** to produce `installer_output/MotorcycleForensicDataVisualizer-Setup.exe`. Paths inside the script are relative to `packaging/`, so the PyInstaller build still runs from the repo root.

## Architecture

The `motoviz` package is split into a pure data/processing core and a Qt UI layer. The core modules (`signals`, `processing`, `csv_loader`, `calibration`, `session`) have no Qt dependency beyond `QSettings`/`QStandardPaths` and are unit-tested in `tests/`.

**Core modules:**

- **`signals.py`** — the `SIGNALS` dict, the canonical registry of every plottable signal. Each entry declares `label`, `unit`, `color`, `preferred_headers` (exact CSV column matches), `fallback_headers` (substring/alias matches), and a `derived` flag (raw CSV column vs. computed signal). Adding a signal means adding one entry here; the rest of the app adapts. Also holds `TIME_HEADERS` and `UNIT_AXIS_LABELS`.

- **`csv_loader.py`** — CSV parsing in two phases: `parse_raw_series` reads the file and pulls recognised columns into numpy arrays; `compute_derived_series` applies a `Calibration` to produce filtered/integrated signals. Splitting them lets a calibration change re-derive signals without re-reading the file (`recompute_with_calibration`). `find_column` does normalized exact-match first, then substring fallback. The `LoadedCSV` dataclass is the parsed-data container (headers/rows, time array `x`, `series` dict, sample rate, gaps).

- **`processing.py`** — pure signal-processing primitives: NaN-aware smoothing, Butterworth/median filters, gyro integration with high-pass drift correction, IMU mounting-offset compensation, and sample-rate/gap analysis.

- **`calibration.py`** — the `Calibration` dataclass (bike geometry, IMU offsets, filter cutoffs) with JSON load/save and app-data-dir helpers for the default profile and presets.

- **`session.py`** — forensic session export/import (JSON with CSV SHA-256, calibration, selected signals, view/region ranges) so a plotted view is reproducible from the raw CSV.

- **`settings.py`** — thin `QSettings` wrapper for user prefs, recent files, window state, and the per-signal plot assignment (with a versioned migration).

**UI layer:**

- **`main_window.py`** — `MainWindow` (menu bar, shortcuts, drag-and-drop, recent files, theme, session IO) plus the `main()` entry point and `resource_path()` (handles dev vs. PyInstaller `sys._MEIPASS`/`sys.frozen` asset paths). Each signal has a per-row plot picker; the number of stacked plots is derived from the assignment.

- **`widgets/plot_panel.py`** — `PlotView` is one pyqtgraph plot supporting up to **four independent `ViewBox`es** (left, right1–3) so up to four unit groups (m/s², deg, km/h, rad/s) share one plot on separate Y-axes; `unit_order` maps each unit to a slot. Right-axis grid lines are drawn manually as `pg.InfiniteLine`s because pyqtgraph's built-in grid only tracks the main viewbox. `PlotPanel` stacks up to `MAX_PLOTS` `PlotView`s with a linked X-axis and shared toolbar.

- **`widgets/plot_features.py`** — reusable add-ons spanning the stacked plots: `MultiPlotCrosshair`, `MirroredRegionSelector`, `GapShader`.

- **`widgets/tables.py`** — `CSVTableModel` / `SignalStatsTableModel` (`QAbstractTableModel` subclasses) for the Data tab; stats can be scoped to a selected time region.

- **`widgets/dialogs.py`** — the About and Calibration dialogs.

## Release Workflow

1. Test locally with `python App.py`
2. Clean `build/`, `dist/`, `installer_output/`
3. Run PyInstaller (command above)
4. Update `AppVersion` in `packaging/installer.iss` (and `__version__` in `motoviz/__init__.py`)
5. Compile installer in Inno Setup (F9)
6. Distribute `installer_output/MotorcycleForensicDataVisualizer-Setup.exe`

**Do not distribute** the bare `.exe` from `dist/` — it depends on all sibling files in that folder.
