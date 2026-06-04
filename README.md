# Developer Update Guide — Motorcycle Forensic Data Visualizer (Python)

This document explains how to develop, test, rebuild the executable, and create a
new Windows installer.

---

## Project Structure

```text
PythonV1/
├─ App.py                 # thin entry point → motoviz.main_window.main()
├─ Requirements.txt
├─ CLAUDE.md              # architecture notes
├─ packaging/
│  └─ installer.iss       # Inno Setup script (paths relative to repo root)
├─ assets/
│  └─ icon.ico
├─ motoviz/               # application package
│  ├─ __init__.py         # version / app name / publisher
│  ├─ signals.py          # SIGNALS registry, units, time headers
│  ├─ csv_loader.py       # CSV parsing + derived-signal computation
│  ├─ processing.py       # filters, gyro integration, gap analysis
│  ├─ calibration.py      # Calibration profile (JSON load/save)
│  ├─ session.py          # forensic session export/import
│  ├─ settings.py         # QSettings wrapper (prefs, recent files)
│  ├─ main_window.py      # MainWindow + main() entry point
│  └─ widgets/
│     ├─ plot_panel.py    # stacked multi-axis plots
│     ├─ plot_features.py # crosshair, region selector, gap shader
│     ├─ tables.py        # raw-data + statistics table models
│     └─ dialogs.py       # About + Calibration dialogs
├─ tests/                 # pytest unit tests for the core modules
├─ build/                 # PyInstaller work dir (generated)
├─ dist/                  # PyInstaller output (generated)
└─ installer_output/      # Inno Setup output (generated)
```

All application code lives in the `motoviz` package. `App.py` stays at the repo
root because it is the PyInstaller entry script.

---

## Step 1 — Activate the Virtual Environment

### Windows PowerShell

```powershell
.\venv\Scripts\Activate.ps1
```

### Windows CMD

```bat
venv\Scripts\activate
```

To (re)install dependencies:

```powershell
pip install -r Requirements.txt
```

---

## Step 2 — Test the Application

Run the unit tests:

```powershell
python -m pytest
```

Then run the app directly and smoke-test the UI:

```powershell
python App.py
```

Check that:

* the window opens
* CSV loading works
* signals plot correctly
* zoom/pan and the crosshair / region select work
* PNG export works

Fix anything broken here before building.

---

## Step 3 — Clean Old Build Files (Recommended)

```powershell
Remove-Item -Recurse -Force build, dist, installer_output -ErrorAction SilentlyContinue
```

---

## Step 4 — Rebuild the Executable with PyInstaller

```powershell
pyinstaller --noconfirm --windowed --icon=assets/icon.ico --name "Motorcycle Forensic Data Visualizer" App.py
```

This creates the packaged application in:

```text
dist/Motorcycle Forensic Data Visualizer/
```

> The `.exe` depends on the other files in that folder — do not distribute it on its own.

---

## Step 5 — Update the Version Number

Bump the version in **both** places so the About dialog and the installer agree:

* `motoviz/__init__.py` → `__version__`
* `packaging/installer.iss` → `AppVersion`

Versioning guide:

* `1.0.0` → first release
* `1.0.1` → small fix
* `1.1.0` → added feature
* `2.0.0` → major redesign

---

## Step 6 — Rebuild the Installer with Inno Setup

Open `packaging/installer.iss` in **Inno Setup Compiler** and press **F9** (Build → Compile).
The script's paths are relative to `packaging/`, so it reads `..\dist` and `..\assets` and writes to `..\installer_output` at the repo root.

This produces:

```text
installer_output/MotorcycleForensicDataVisualizer-Setup.exe
```

This is the file you distribute.

---

## Typical Update Workflow

1. Activate the virtual environment
2. `python -m pytest` and `python App.py` to verify
3. Clean `build/`, `dist/`, `installer_output/`
4. Rebuild the executable with PyInstaller
5. Bump `__version__` (in `motoviz/__init__.py`) and `AppVersion` (in `packaging/installer.iss`)
6. Compile the installer in Inno Setup (F9)
7. Install and test on your own machine before sending it out

---

## If the Installer Fails

Check:

* `dist/Motorcycle Forensic Data Visualizer/` exists
* `packaging/installer.iss` points to the correct `..\dist` folder
* `assets/icon.ico` exists

Common fix: delete `build/`, `dist/`, and `installer_output/`, then rebuild from scratch.
