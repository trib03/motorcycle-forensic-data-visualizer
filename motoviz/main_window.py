"""Top-level QMainWindow: menu bar, shortcuts, drag-and-drop, recent files,
calibration, theme, session IO."""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __app_name__, __version__
from .calibration import Calibration, load_default_calibration
from .csv_loader import LoadedCSV, load_csv, recompute_with_calibration
from .session import build_session_dict, load_session, save_session
from .signals import SIGNALS
from . import settings
from .widgets.dialogs import AboutDialog, CalibrationDialog
from .widgets.plot_panel import PlotPanel
from .widgets.tables import CSVTableModel, SignalStatsTableModel


# Default plot index for each unit group.  Applied when the user has no
# persisted choice for a signal — see settings.maybe_migrate_assignment for
# how stale assignments are cleared when this mapping changes.
UNIT_DEFAULT_PLOT = {
    "m/s²": 1,
    "deg": 2,
    "km/h": 3,
    "rad/s": 4,
}


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    elif getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.dirname(base_path)  # parent of motoviz package
    return os.path.join(base_path, relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
        self.setAcceptDrops(True)

        self.loaded: Optional[LoadedCSV] = None
        self.calibration: Calibration = load_default_calibration()
        self.checkboxes: Dict[str, QCheckBox] = {}
        # Per-signal plot picker (QComboBox).  Each item's userData is the
        # 1-based plot index (1..MAX_PLOTS).
        self.plot_combos: Dict[str, QComboBox] = {}
        # One-time wipe of old "everything-on-P1" assignments so the unit-based
        # defaults below take effect for existing users.
        settings.maybe_migrate_assignment()
        self._persisted_assignment: Dict[str, int] = settings.signal_assignment()

        # ---- Left panel ----
        self.load_btn = QPushButton("Load CSV File…")
        self.load_btn.clicked.connect(self.on_load_csv)

        self.status_lbl = QLabel("No file loaded.")
        self.status_lbl.setWordWrap(True)

        checkbox_widget = QWidget()
        cb_layout = QVBoxLayout(checkbox_widget)
        cb_layout.setAlignment(Qt.AlignTop)
        cb_layout.setSpacing(2)
        for key, cfg in SIGNALS.items():
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)

            cb = QCheckBox(cfg["label"])
            cb.setEnabled(False)
            cb.stateChanged.connect(self.on_signal_toggled)

            combo = QComboBox()
            for i in range(1, PlotPanel.MAX_PLOTS + 1):
                combo.addItem(f"P{i}", i)
            combo.setFixedWidth(60)
            combo.setEnabled(False)
            combo.setToolTip(
                "Which plot window this signal is drawn in. "
                "Picking a number higher than the current plot count "
                "automatically adds that many plot panes."
            )
            unit_default = UNIT_DEFAULT_PLOT.get(cfg["unit"], 1)
            initial = self._persisted_assignment.get(key, unit_default)
            initial = min(PlotPanel.MAX_PLOTS, max(1, initial))
            combo.setCurrentIndex(initial - 1)
            combo.currentIndexChanged.connect(self._on_assignment_changed)

            rl.addWidget(cb, stretch=1)
            rl.addWidget(combo)

            self.checkboxes[key] = cb
            self.plot_combos[key] = combo
            cb_layout.addWidget(row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(checkbox_widget)

        select_all_btn = QPushButton("All")
        select_all_btn.setFixedWidth(50)
        select_all_btn.clicked.connect(self.select_all_signals)
        deselect_btn = QPushButton("None")
        deselect_btn.setFixedWidth(50)
        deselect_btn.clicked.connect(self.deselect_all_signals)

        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Select:"))
        sel_row.addWidget(select_all_btn)
        sel_row.addWidget(deselect_btn)
        sel_row.addStretch()

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(self.load_btn)
        left_layout.addWidget(self.status_lbl)
        left_layout.addSpacing(8)
        left_layout.addWidget(QLabel("Signals:"))
        left_layout.addLayout(sel_row)
        left_layout.addWidget(scroll, stretch=1)

        # ---- Raw tab ----
        self.raw_panel = PlotPanel()
        # Plot count is derived from checked signal assignments (see
        # _sync_plot_count_and_refresh); start with a single empty plot.
        self.raw_panel.set_plot_count(1)
        self.raw_panel.regionChanged.connect(self._on_region_changed)
        self.raw_panel.set_crosshair_enabled(settings.crosshair_enabled())
        self.raw_panel.set_region_enabled(settings.region_enabled())

        raw_tab = QWidget()
        raw_tab_layout = QVBoxLayout(raw_tab)
        raw_tab_layout.setContentsMargins(4, 4, 4, 4)
        raw_tab_layout.addWidget(self.raw_panel)

        # ---- Data tab ----
        self.raw_table = QTableView()
        self.raw_table.setSortingEnabled(False)
        self.raw_table_model = CSVTableModel()
        self.raw_table.setModel(self.raw_table_model)

        self.stats_table = QTableView()
        self.stats_table.setSortingEnabled(False)
        self.stats_table_model = SignalStatsTableModel()
        self.stats_table.setModel(self.stats_table_model)

        raw_tbl_wrap = QWidget()
        rtl = QVBoxLayout(raw_tbl_wrap)
        rtl.setContentsMargins(0, 0, 0, 0)
        rtl.addWidget(QLabel("Raw CSV Data"))
        rtl.addWidget(self.raw_table)

        stats_tbl_wrap = QWidget()
        stl = QVBoxLayout(stats_tbl_wrap)
        stl.setContentsMargins(0, 0, 0, 0)
        stl.addWidget(QLabel("Signal Statistics (use Region Select on the Raw tab to scope these)"))
        stl.addWidget(self.stats_table)

        self.tables_splitter = QSplitter(Qt.Horizontal)
        self.tables_splitter.addWidget(raw_tbl_wrap)
        self.tables_splitter.addWidget(stats_tbl_wrap)
        self.tables_splitter.setStretchFactor(0, 3)
        self.tables_splitter.setStretchFactor(1, 2)
        self.tables_splitter.setSizes([700, 400])

        data_tab = QWidget()
        data_tab_layout = QVBoxLayout(data_tab)
        data_tab_layout.setContentsMargins(4, 4, 4, 4)
        data_tab_layout.addWidget(self.tables_splitter)

        # ---- Tab widget ----
        self.tabs = QTabWidget()
        self.tabs.addTab(raw_tab, "Raw Signals")
        self.tabs.addTab(data_tab, "Data")

        # ---- Main splitter ----
        self.main_splitter = QSplitter()
        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(self.tabs)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([290, 990])

        self.setCentralWidget(self.main_splitter)

        # ---- Menu bar + status bar ----
        self._build_menu_bar()
        self.statusBar().showMessage("Ready.")

        # ---- Restore persisted state ----
        geom = settings.load_geometry()
        if geom:
            self.restoreGeometry(geom)
        state = settings.load_state()
        if state:
            self.restoreState(state)
        ms = settings.load_splitter("main_splitter")
        if ms:
            self.main_splitter.restoreState(ms)
        ts = settings.load_splitter("tables_splitter")
        if ts:
            self.tables_splitter.restoreState(ts)

        # Theme last so widgets are constructed
        self._apply_theme(settings.dark_theme())

    # ------------------------------------------------------------------
    # Menu / actions
    # ------------------------------------------------------------------

    def _build_menu_bar(self):
        menubar = self.menuBar()

        # ----- File -----
        file_menu = menubar.addMenu("&File")

        open_act = QAction("&Open CSV…", self)
        open_act.setShortcut(QKeySequence.Open)
        open_act.triggered.connect(self.on_load_csv)
        file_menu.addAction(open_act)

        self.recent_menu = QMenu("Open &Recent", self)
        file_menu.addMenu(self.recent_menu)
        self._refresh_recent_menu()

        file_menu.addSeparator()

        save_session_act = QAction("&Save JSON…", self)
        save_session_act.setShortcut(QKeySequence("Ctrl+S"))
        save_session_act.triggered.connect(self.on_save_session)
        file_menu.addAction(save_session_act)

        load_session_act = QAction("&Load JSON…", self)
        load_session_act.triggered.connect(self.on_load_session)
        file_menu.addAction(load_session_act)

        file_menu.addSeparator()

        export_act = QAction("&Export PNG", self)
        export_act.setShortcut(QKeySequence("Ctrl+E"))
        export_act.triggered.connect(lambda: self.raw_panel._on_export())
        file_menu.addAction(export_act)

        file_menu.addSeparator()

        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence("Ctrl+Q"))
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # ----- View -----
        view_menu = menubar.addMenu("&View")

        self.reset_view_act = QAction("&Reset Raw Plot View", self)
        self.reset_view_act.setShortcut(QKeySequence("Ctrl+R"))
        self.reset_view_act.triggered.connect(lambda: self.raw_panel._on_reset_view())
        view_menu.addAction(self.reset_view_act)

        view_menu.addSeparator()

        self.crosshair_act = QAction("&Crosshair", self, checkable=True)
        self.crosshair_act.setShortcut(QKeySequence("Ctrl+H"))
        self.crosshair_act.setChecked(settings.crosshair_enabled())
        self.crosshair_act.toggled.connect(self._on_crosshair_toggled)
        view_menu.addAction(self.crosshair_act)

        self.region_act = QAction("&Region Select", self, checkable=True)
        self.region_act.setShortcut(QKeySequence("Ctrl+G"))
        self.region_act.setChecked(settings.region_enabled())
        self.region_act.toggled.connect(self._on_region_act_toggled)
        view_menu.addAction(self.region_act)

        view_menu.addSeparator()

        self.dark_theme_act = QAction("&Dark Theme", self, checkable=True)
        self.dark_theme_act.setChecked(settings.dark_theme())
        self.dark_theme_act.toggled.connect(self._on_theme_toggled)
        view_menu.addAction(self.dark_theme_act)

        # ----- Tools -----
        tools_menu = menubar.addMenu("&Tools")

        cal_act = QAction("&Calibration Profile…", self)
        cal_act.triggered.connect(self.on_calibration_dialog)
        tools_menu.addAction(cal_act)

        # ----- Help -----
        help_menu = menubar.addMenu("&Help")

        about_act = QAction("&About", self)
        about_act.triggered.connect(self.on_about)
        help_menu.addAction(about_act)

    def _refresh_recent_menu(self):
        self.recent_menu.clear()
        files = settings.recent_files()
        if not files:
            empty = QAction("(no recent files)", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return
        for path in files:
            act = QAction(path, self)
            act.triggered.connect(lambda checked=False, p=path: self._load_csv_path(p))
            self.recent_menu.addAction(act)
        self.recent_menu.addSeparator()
        clear_act = QAction("Clear list", self)
        clear_act.triggered.connect(self._on_clear_recent)
        self.recent_menu.addAction(clear_act)

    def _on_clear_recent(self):
        settings.clear_recent_files()
        self._refresh_recent_menu()

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith(".csv"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            p = url.toLocalFile()
            if p.lower().endswith(".csv"):
                self._load_csv_path(p)
                break

    # ------------------------------------------------------------------
    # CSV loading
    # ------------------------------------------------------------------

    def on_load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV Log File", settings.last_directory(),
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        self._load_csv_path(path)

    def _load_csv_path(self, path: str):
        try:
            loaded = load_csv(path, calibration=self.calibration)
        except Exception as e:
            QMessageBox.critical(self, "Load error", f"Failed to load CSV:\n{e}")
            return

        self.loaded = loaded
        settings.set_last_directory(os.path.dirname(path))
        settings.push_recent_file(path)
        self._refresh_recent_menu()

        self._update_status_from_loaded()

        self.raw_table_model.set_csv_data(loaded.headers, loaded.rows)
        self.raw_table.resizeColumnsToContents()
        self.stats_table_model.set_loaded_csv(loaded)
        self.stats_table.resizeColumnsToContents()

        any_signal = False
        for key, cb in self.checkboxes.items():
            present = key in loaded.series
            cb.blockSignals(True)
            cb.setEnabled(present)
            cb.setChecked(False)
            cb.blockSignals(False)
            combo = self.plot_combos.get(key)
            if combo is not None:
                combo.setEnabled(present)
            any_signal = any_signal or present

        self.raw_panel.clear()
        self.raw_panel.refresh(loaded, {})

        if not any_signal:
            QMessageBox.warning(
                self, "No signals found",
                "No expected signal columns were found in this CSV.\n"
                "Please verify the file is from the HAN datalogger.",
            )

    def _update_status_from_loaded(self):
        if self.loaded is None:
            self.status_lbl.setText("No file loaded.")
            self.statusBar().showMessage("Ready.")
            return
        sr_text = (f"  |  ~{self.loaded.sample_rate:.0f} Hz"
                   if self.loaded.sample_rate else "")
        path = self.loaded.source_path or ""
        bits = [f"{os.path.basename(path)}", f"{len(self.loaded.rows)} rows{sr_text}"]
        if self.loaded.gaps:
            bits.append(
                f"⚠ {len(self.loaded.gaps)} sample-rate gap(s); "
                f"max Δt = {self.loaded.max_dt:.3f}s"
            )
        self.status_lbl.setText("\n".join(bits))
        if self.loaded.gaps:
            self.statusBar().showMessage(
                f"Loaded {os.path.basename(path)} with "
                f"{len(self.loaded.gaps)} sample-rate gap(s) — see red bands on the plot."
            )
        else:
            self.statusBar().showMessage(
                f"Loaded {os.path.basename(path)} — "
                f"{len(self.loaded.rows)} rows, sample rate "
                f"{self.loaded.sample_rate:.2f} Hz"
                if self.loaded.sample_rate else f"Loaded {os.path.basename(path)}"
            )

    # ------------------------------------------------------------------
    # Signal toggles
    # ------------------------------------------------------------------

    def _active_keys(self) -> List[str]:
        return [k for k, cb in self.checkboxes.items() if cb.isEnabled() and cb.isChecked()]

    def _signal_assignment(self) -> Dict[str, int]:
        """Map of selected signal_key → 1-based plot index."""
        out: Dict[str, int] = {}
        for key in self._active_keys():
            combo = self.plot_combos.get(key)
            out[key] = int(combo.currentData()) if combo is not None else 1
        return out

    def _persist_assignment(self):
        # Save the full assignment (including currently-disabled signals) so
        # the choices are remembered across CSV reloads.
        snapshot = dict(self._persisted_assignment)
        for key, combo in self.plot_combos.items():
            snapshot[key] = int(combo.currentData())
        self._persisted_assignment = snapshot
        settings.set_signal_assignment(snapshot)

    def _needed_plot_count(self) -> int:
        """Highest plot index used by any currently-checked signal, min 1."""
        indices = [int(self.plot_combos[k].currentData())
                   for k, cb in self.checkboxes.items() if cb.isChecked()]
        return max(indices) if indices else 1

    def _sync_plot_count_and_refresh(self):
        """Resize the stacked plot grid to fit the current signal assignment,
        then redraw."""
        if not self.loaded:
            return
        needed = self._needed_plot_count()
        if needed != self.raw_panel.plot_count():
            self.raw_panel.set_plot_count(needed)
        self._refresh_panel()

    def _refresh_panel(self):
        self.raw_panel.refresh(self.loaded, self._signal_assignment())

    def _on_assignment_changed(self, *_):
        self._persist_assignment()
        self._sync_plot_count_and_refresh()

    def on_signal_toggled(self):
        if not self.loaded:
            return

        # Check unit-group limit *per plot*: each plot can show up to 4
        # different unit groups.
        units_per_plot: Dict[int, set] = {}
        assignment = self._signal_assignment()
        for key, plot_idx in assignment.items():
            u = SIGNALS[key]["unit"]
            units_per_plot.setdefault(plot_idx, set()).add(u)

        offender = None
        for plot_idx, units in units_per_plot.items():
            if len(units) > 4:
                offender = plot_idx
                break

        if offender is not None:
            sender = self.sender()
            if isinstance(sender, QCheckBox):
                sender.blockSignals(True)
                sender.setChecked(False)
                sender.blockSignals(False)
            QMessageBox.warning(
                self, "Too many unit groups",
                f"Plot {offender} already shows four different unit groups "
                "(m/s², deg, km/h, rad/s). Move this signal to a different "
                "plot using its P-dropdown.",
            )
            return

        self._sync_plot_count_and_refresh()

    def select_all_signals(self):
        if not self.loaded:
            return
        # Group enabled signals by their assigned plot.
        units_per_plot: Dict[int, List[str]] = {}
        skipped: List[str] = []
        for key, cb in self.checkboxes.items():
            if not cb.isEnabled():
                continue
            plot_idx = int(self.plot_combos[key].currentData())
            unit = SIGNALS[key]["unit"]
            current = units_per_plot.setdefault(plot_idx, [])
            if unit in current or len(current) < 4:
                if unit not in current:
                    current.append(unit)
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)
            else:
                skipped.append(SIGNALS[key]["label"])
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
        self._sync_plot_count_and_refresh()
        if skipped:
            QMessageBox.information(
                self, "Skipped some signals",
                "Each plot can show up to four different unit groups. "
                "These signals were skipped — assign them to a less-crowded "
                "plot first:\n - " + "\n - ".join(skipped),
            )

    def deselect_all_signals(self):
        for cb in self.checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._sync_plot_count_and_refresh()

    # ------------------------------------------------------------------
    # View toggles
    # ------------------------------------------------------------------

    def _on_crosshair_toggled(self, on: bool):
        settings.set_crosshair_enabled(on)
        self.raw_panel.set_crosshair_enabled(on)

    def _on_region_act_toggled(self, on: bool):
        settings.set_region_enabled(on)
        self.raw_panel.set_region_enabled(on)

    def _on_region_changed(self, region):
        self.stats_table_model.set_region(region)
        self.stats_table.resizeColumnsToContents()

    def _on_theme_toggled(self, on: bool):
        settings.set_dark_theme(on)
        self._apply_theme(on)

    def _apply_theme(self, dark: bool):
        app = QApplication.instance()
        if app is None:
            return
        if dark:
            pg.setConfigOption("background", "#101216")
            pg.setConfigOption("foreground", "#EEEEEE")
            app.setStyleSheet(
                "QWidget { background-color: #1A1D22; color: #EEEEEE; }"
                "QGroupBox { border: 1px solid #444; margin-top: 8px; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
                "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableView, QTextEdit { "
                "  background-color: #23272E; color: #EEEEEE; border: 1px solid #444;"
                "}"
                "QPushButton { background-color: #2C313A; border: 1px solid #444; padding: 4px 10px; }"
                "QPushButton:hover { background-color: #364048; }"
                "QHeaderView::section { background-color: #2C313A; color: #EEEEEE; }"
                "QMenuBar, QMenu { background-color: #1A1D22; color: #EEEEEE; }"
                "QMenu::item:selected { background-color: #364048; }"
                "QTabBar::tab { background: #2C313A; color: #EEEEEE; padding: 6px 12px; }"
                "QTabBar::tab:selected { background: #3B4250; }"
            )
        else:
            pg.setConfigOption("background", "w")
            pg.setConfigOption("foreground", "k")
            app.setStyleSheet("")
        self.raw_panel.apply_theme(dark)

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def on_calibration_dialog(self):
        dlg = CalibrationDialog(self.calibration, self)
        dlg.exec()
        new_cal = dlg.result_calibration()
        if not new_cal:
            return
        self.calibration = new_cal
        # Re-derive signals if a file is loaded
        if self.loaded is not None:
            try:
                self.loaded = recompute_with_calibration(self.loaded, self.calibration)
            except Exception as e:
                QMessageBox.warning(self, "Recompute failed", str(e))
                return
            self.stats_table_model.set_loaded_csv(self.loaded)
            self._refresh_panel()
            self._update_status_from_loaded()

    # ------------------------------------------------------------------
    # Session export / import
    # ------------------------------------------------------------------

    def on_save_session(self):
        if self.loaded is None:
            QMessageBox.information(self, "No data", "Load a CSV first.")
            return
        default_name = "session.json"
        if self.loaded.source_path:
            default_name = Path(self.loaded.source_path).stem + "_session.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Forensic Session",
            str(Path(settings.last_directory()) / default_name) if settings.last_directory() else default_name,
            "Session JSON (*.json)"
        )
        if not path:
            return
        view_range = self.raw_panel.main_vb.viewRange()[0] if self.loaded else None
        payload = build_session_dict(
            csv_path=self.loaded.source_path,
            sample_rate=self.loaded.sample_rate,
            row_count=len(self.loaded.rows),
            calibration=self.calibration,
            selected_signals=self._active_keys(),
            view_range=tuple(view_range) if view_range else None,
            region_range=self.raw_panel.current_region(),
        )
        payload["plot_count"] = self.raw_panel.plot_count()
        payload["signal_assignment"] = self._signal_assignment()
        try:
            save_session(path, payload)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        QMessageBox.information(self, "Session saved", f"Saved:\n{path}")

    def on_load_session(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Forensic Session", settings.last_directory(),
            "Session JSON (*.json)"
        )
        if not path:
            return
        try:
            payload = load_session(path)
        except Exception as e:
            QMessageBox.critical(self, "Load failed", str(e))
            return

        # Restore calibration
        cal_dict = payload.get("calibration") or {}
        try:
            self.calibration = Calibration(**{k: v for k, v in cal_dict.items()
                                             if k in Calibration.__dataclass_fields__})
        except Exception:
            self.calibration = Calibration()

        # Load CSV if path still valid
        csv_info = payload.get("csv") or {}
        csv_path = csv_info.get("path")
        if csv_path and Path(csv_path).exists():
            self._load_csv_path(csv_path)
        elif csv_path:
            new_path, _ = QFileDialog.getOpenFileName(
                self,
                f"Original CSV not found at '{csv_path}'. Locate it:",
                settings.last_directory(),
                "CSV Files (*.csv);;All Files (*)",
            )
            if new_path:
                self._load_csv_path(new_path)
            else:
                return

        # Restore plot count + per-signal assignment first
        plot_count = int(payload.get("plot_count", self.raw_panel.plot_count()))
        self.raw_panel.set_plot_count(plot_count)
        assignment = payload.get("signal_assignment") or {}
        for key, idx in assignment.items():
            combo = self.plot_combos.get(key)
            if combo is not None:
                combo.blockSignals(True)
                combo.setCurrentIndex(max(0, min(PlotPanel.MAX_PLOTS - 1,
                                                 int(idx) - 1)))
                combo.blockSignals(False)

        # Apply selected signals
        for key, cb in self.checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(key in (payload.get("selected_signals") or []) and cb.isEnabled())
            cb.blockSignals(False)
        self._refresh_panel()
        self._persist_assignment()

        # Restore view + region
        view_range = payload.get("view_range_s")
        if view_range and len(view_range) == 2 and self.raw_panel.main_vb is not None:
            self.raw_panel.main_vb.setXRange(float(view_range[0]), float(view_range[1]),
                                             padding=0)
        region = payload.get("region_range_s")
        if region and len(region) == 2:
            self.region_act.setChecked(True)

        self.statusBar().showMessage(f"Loaded session from {Path(path).name}")

    def on_about(self):
        dlg = AboutDialog(self, icon_path=resource_path("assets/icon.ico"))
        dlg.exec()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        settings.save_geometry(self.saveGeometry())
        settings.save_state(self.saveState())
        settings.save_splitter("main_splitter", self.main_splitter.saveState())
        settings.save_splitter("tables_splitter", self.tables_splitter.saveState())
        super().closeEvent(event)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    pg.setConfigOptions(antialias=True)
    app = QApplication([])
    app.setApplicationName(__app_name__)
    app.setOrganizationName("HAN")
    app.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    app.exec()
