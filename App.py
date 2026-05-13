import csv
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from scipy.integrate import cumulative_trapezoid
from scipy.signal import butter, filtfilt
from pyqtgraph.exporters import ImageExporter

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# =========================================================
# Helpers
# =========================================================


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    elif getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def normalize_name(s: str) -> str:
    return "".join(ch.lower() for ch in s.strip() if ch.isalnum() or ch in ["_", " "])


def parse_float(value: str) -> float:
    try:
        return float(value.strip().replace(",", "."))
    except Exception:
        return np.nan


_FILTFILT_ACCEL_CUTOFF_HZ = 5.0
_FILTFILT_GYRO_CUTOFF_HZ = 10.0
_FILTFILT_ORDER = 4


def _fill_nan(y: np.ndarray) -> np.ndarray:
    """Replace NaN values with linear interpolation so filtfilt can run."""
    if not np.isnan(y).any():
        return y
    out = y.copy()
    nans = np.isnan(out)
    idx = np.where(~nans)[0]
    if idx.size < 2:
        return out
    out[nans] = np.interp(np.where(nans)[0], idx, out[idx])
    return out


def moving_average(y: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average that ignores NaN values within each window."""
    if window <= 1:
        return y.copy()
    half = window // 2
    n = len(y)
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        seg = y[lo:hi]
        valid = seg[np.isfinite(seg)]
        if valid.size:
            out[i] = valid.mean()
    return out


# =========================================================
# Signal configuration
# =========================================================

SIGNALS = {
    "raw_longitudinal_acceleration": {
        "label": "Raw Longitudinal Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#FF4E50",
        "preferred_headers": ["raw_ax_mps2"],
        "fallback_headers": ["raw_ax_corr_mps2", "longitudinal_acceleration"],
    },
    "raw_longitudinal_acceleration_filtfilt": {
        "label": "Filtered Longitudinal Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#b30000",
        "preferred_headers": [],
        "fallback_headers": [],
    },
    "raw_lateral_acceleration": {
        "label": "Raw Lateral Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#9EFF3D",
        "preferred_headers": ["raw_ay_mps2"],
        "fallback_headers": ["raw_ay_corr_mps2", "lateral_acceleration"],
    },
    "raw_lateral_acceleration_filtfilt": {
        "label": "Filtered Lateral Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#4c9800",
        "preferred_headers": [],
        "fallback_headers": [],
    },
    "raw_vertical_acceleration": {
        "label": "Raw Vertical Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#4bf6ff",
        "preferred_headers": ["raw_az_mps2"],
        "fallback_headers": ["raw_az_corr_mps2", "vertical_acceleration"],
    },
    "raw_vertical_acceleration_filtfilt": {
        "label": "Filtered Vertical Acceleration (m/s²)",
        "unit": "m/s²",
        "color": "#01A7A7",
        "preferred_headers": [],
        "fallback_headers": [],
    },
    "pitch_from_gyro": {
        "label": "Pitch angle (deg)",
        "unit": "deg",
        "color": "#642bd4",
        "preferred_headers": [],
        "fallback_headers": [],
    },
    "roll_from_gyro": {
        "label": "Roll angle (deg)",
        "unit": "deg",
        "color": "#19b078",
        "preferred_headers": [],
        "fallback_headers": [],
    },
    "rear_wheel_speed": {
        "label": "Rear Wheel Speed (km/h)",
        "unit": "km/h",
        "color": "#984ea3",
        "preferred_headers": ["hall_r"],
        "fallback_headers": ["hall_rear", "rear wheel speed", "rear_wheel_speed", "v_rear", "rear_speed", "rear_kmh"],
    },
    "front_wheel_speed": {
        "label": "Front Wheel Speed (km/h)",
        "unit": "km/h",
        "color": "#ff7f00",
        "preferred_headers": ["hall_f"],
        "fallback_headers": ["hall_front", "front wheel speed", "front_wheel_speed", "v_front", "front_speed", "front_kmh"],
    },
    "gps_speed": {
        "label": "GPS Speed (km/h)",
        "unit": "km/h",
        "color": "#ff1493",
        "preferred_headers": ["speed_kmh"],
        "fallback_headers": ["gps_speed", "gps_speed_kmh", "gps_speed_km/h", "gps_speed_kph"],
    },
}

TIME_HEADERS = ["time", "timestamp", "t", "sec", "seconds"]

UNIT_AXIS_LABELS = {
    "m/s²": "Acceleration (m/s²)",
    "deg": "Angle (deg)",
    "km/h": "Speed (km/h)",
}


# =========================================================
# Data model
# =========================================================

@dataclass
class LoadedCSV:
    headers: List[str]
    rows: List[List[str]]
    x: np.ndarray
    series: Dict[str, np.ndarray]
    sample_rate: Optional[float] = field(default=None)


def find_column(headers: List[str], candidates: List[str]) -> Optional[int]:
    normalized_headers = [normalize_name(h) for h in headers]
    normalized_candidates = [normalize_name(c) for c in candidates]
    for candidate in normalized_candidates:
        for i, header in enumerate(normalized_headers):
            if header == candidate:
                return i
    for candidate in normalized_candidates:
        for i, header in enumerate(normalized_headers):
            if candidate in header:
                return i
    return None


def parse_float_column(rows: List[List[str]], col: int) -> np.ndarray:
    data = []
    for row in rows:
        data.append(parse_float(row[col]) if col < len(row) else np.nan)
    return np.array(data, dtype=float)


def load_csv(path: str) -> LoadedCSV:
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        all_rows = list(csv.reader(f))

    if len(all_rows) < 2:
        raise ValueError("CSV appears empty or has no data rows.")

    headers = all_rows[0]
    rows = all_rows[1:]

    time_col = find_column(headers, TIME_HEADERS)
    if time_col is not None:
        x = parse_float_column(rows, time_col)
        if np.all(np.isnan(x)):
            x = np.arange(len(rows), dtype=float)
    else:
        x = np.arange(len(rows), dtype=float)

    series: Dict[str, np.ndarray] = {}
    for key, config in SIGNALS.items():
        col = find_column(headers, config["preferred_headers"])
        if col is None:
            col = find_column(headers, config["fallback_headers"])
        if col is not None:
            series[key] = parse_float_column(rows, col)

    x_finite = x[np.isfinite(x)]
    sample_rate: Optional[float] = None
    if len(x_finite) > 1:
        dt = float(np.median(np.diff(x_finite)))
        if dt > 0:
            sample_rate = 1.0 / dt

    if sample_rate is not None and sample_rate > 0:
        nyq = sample_rate / 2.0
        x_clean = _fill_nan(x)

        # Filtfilt versions of the three raw acceleration signals (5 Hz cutoff)
        if _FILTFILT_ACCEL_CUTOFF_HZ < nyq:
            b_acc, a_acc = butter(_FILTFILT_ORDER, _FILTFILT_ACCEL_CUTOFF_HZ / nyq, btype="low")
            for src_key, dst_key in [
                ("raw_longitudinal_acceleration", "raw_longitudinal_acceleration_filtfilt"),
                ("raw_lateral_acceleration",      "raw_lateral_acceleration_filtfilt"),
                ("raw_vertical_acceleration",     "raw_vertical_acceleration_filtfilt"),
            ]:
                if src_key in series:
                    try:
                        series[dst_key] = filtfilt(b_acc, a_acc, _fill_nan(series[src_key]))
                    except Exception:
                        pass

        # Gyro integration with linear drift correction → pitch and roll angles (10 Hz cutoff)
        if _FILTFILT_GYRO_CUTOFF_HZ < nyq:
            b_gyro, a_gyro = butter(_FILTFILT_ORDER, _FILTFILT_GYRO_CUTOFF_HZ / nyq, btype="low")
            for gyro_header, dst_key in [
                ("gyro_y_rads", "pitch_from_gyro"),
                ("gyro_x_rads", "roll_from_gyro"),
            ]:
                col = find_column(headers, [gyro_header])
                if col is not None:
                    try:
                        gyro = _fill_nan(parse_float_column(rows, col))
                        gyro_filt = filtfilt(b_gyro, a_gyro, gyro)
                        angle_rad = cumulative_trapezoid(gyro_filt, x_clean, initial=0)
                        angle_deg = np.rad2deg(angle_rad)
                        drift = np.linspace(0, angle_deg[-1], len(angle_deg))
                        series[dst_key] = angle_deg - drift
                    except Exception:
                        pass

    return LoadedCSV(headers=headers, rows=rows, x=x, series=series, sample_rate=sample_rate)


# =========================================================
# Table models
# =========================================================

class CSVTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._headers: List[str] = []
        self._rows: List[List[str]] = []

    def set_csv_data(self, headers: List[str], rows: List[List[str]]):
        self.beginResetModel()
        self._headers = headers
        self._rows = rows
        self.endResetModel()

    def clear(self):
        self.set_csv_data([], [])

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            r, c = index.row(), index.column()
            if r < len(self._rows) and c < len(self._rows[r]):
                return self._rows[r][c]
            return ""
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self._headers):
            return self._headers[section]
        if orientation == Qt.Vertical:
            return str(section)
        return None


class SignalStatsTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._col_headers = ["Signal", "Min", "Avg", "Max"]
        self._rows: List[List[str]] = []

    def set_loaded_csv(self, loaded: LoadedCSV):
        self.beginResetModel()
        self._rows = []
        for key in SIGNALS:
            if key not in loaded.series:
                continue
            y = loaded.series[key]
            finite = y[np.isfinite(y)]
            if finite.size == 0:
                self._rows.append([SIGNALS[key]["label"], "-", "-", "-"])
            else:
                self._rows.append([
                    SIGNALS[key]["label"],
                    f"{float(np.min(finite)):.3f}",
                    f"{float(np.mean(finite)):.3f}",
                    f"{float(np.max(finite)):.3f}",
                ])
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._col_headers)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return self._rows[index.row()][index.column()]
        if role == Qt.TextAlignmentRole:
            if index.column() == 0:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignCenter | Qt.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self._col_headers):
            return self._col_headers[section]
        if orientation == Qt.Vertical:
            return str(section)
        return None


# =========================================================
# Plot panel (reusable multi-axis plot widget)
# =========================================================

class PlotPanel(QWidget):
    """Self-contained plot widget with up to three independent Y-axes."""

    def __init__(self):
        super().__init__()

        self._loaded: Optional[LoadedCSV] = None
        self.curves: Dict[str, Dict] = {}
        self.unit_order: List[str] = []
        self._right_grids: Dict[str, List[pg.InfiniteLine]] = {"right1": [], "right2": []}

        pg.setConfigOptions(antialias=True)

        self.plot_widget = pg.PlotWidget()
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=True, alpha=0.2)
        self.plot_item.setLabel("bottom", "Time (s) / Index")
        self.plot_item.addLegend(offset=(10, 10))

        self.main_vb = self.plot_item.vb
        self.left_axis = self.plot_item.getAxis("left")

        self.right_axis_1 = pg.AxisItem("right")
        self.right_axis_2 = pg.AxisItem("right")
        self.plot_item.layout.addItem(self.right_axis_1, 2, 3)
        self.plot_item.layout.addItem(self.right_axis_2, 2, 4)

        self.right_vb_1 = pg.ViewBox()
        self.right_vb_2 = pg.ViewBox()
        self.plot_item.scene().addItem(self.right_vb_1)
        self.plot_item.scene().addItem(self.right_vb_2)

        self.right_axis_1.linkToView(self.right_vb_1)
        self.right_axis_2.linkToView(self.right_vb_2)
        self.right_vb_1.setXLink(self.main_vb)
        self.right_vb_2.setXLink(self.main_vb)

        self.axis_slots = {
            "left":   {"axis": self.left_axis,    "viewbox": self.main_vb},
            "right1": {"axis": self.right_axis_1,  "viewbox": self.right_vb_1},
            "right2": {"axis": self.right_axis_2,  "viewbox": self.right_vb_2},
        }

        self.main_vb.sigResized.connect(self._sync_views)
        self.main_vb.sigYRangeChanged.connect(lambda *_: self._update_all_grids())
        self.right_vb_1.sigYRangeChanged.connect(lambda *_: self._update_grid("right1"))
        self.right_vb_2.sigYRangeChanged.connect(lambda *_: self._update_grid("right2"))

        self._hide_all_axes()
        self._sync_views()

        self.export_btn = QPushButton("Export as PNG")
        self.export_btn.clicked.connect(self._on_export)
        self.export_btn.setEnabled(False)

        self.reset_btn = QPushButton("Reset View")
        self.reset_btn.clicked.connect(self._on_reset_view)
        self.reset_btn.setEnabled(False)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.export_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget, stretch=1)
        layout.addLayout(btn_row)

    # --- view / axis management ---

    def _sync_views(self):
        rect = self.main_vb.sceneBoundingRect()
        self.right_vb_1.setGeometry(rect)
        self.right_vb_2.setGeometry(rect)
        self.right_vb_1.linkedViewChanged(self.main_vb, self.right_vb_1.XAxis)
        self.right_vb_2.linkedViewChanged(self.main_vb, self.right_vb_2.XAxis)
        self._update_all_grids()

    def _update_all_grids(self):
        self._update_grid("right1")
        self._update_grid("right2")

    def _clear_grid(self, slot_name: str):
        for line in self._right_grids[slot_name]:
            try:
                self.plot_item.removeItem(line)
            except Exception:
                pass
        self._right_grids[slot_name].clear()

    def _update_grid(self, slot_name: str):
        self._clear_grid(slot_name)
        active_slots = {self._slot_for_unit(u) for u in self.unit_order}
        if slot_name not in active_slots:
            return
        axis = self.axis_slots[slot_name]["axis"]
        vb = self.axis_slots[slot_name]["viewbox"]
        ticks = axis.tickValues(*vb.viewRange()[1], 400)
        if not ticks:
            return
        y_min, y_max = self.main_vb.viewRange()[1]
        for tick_val in ticks[0][1]:
            scene_pt = vb.mapViewToScene(pg.Point(0, tick_val))
            mapped_y = self.main_vb.mapSceneToView(scene_pt).y()
            if np.isfinite(mapped_y) and y_min <= mapped_y <= y_max:
                line = pg.InfiniteLine(
                    pos=mapped_y, angle=0, movable=False,
                    pen=pg.mkPen((160, 160, 160, 90), width=1),
                )
                self.plot_item.addItem(line)
                self._right_grids[slot_name].append(line)

    def _hide_all_axes(self):
        for slot in self.axis_slots.values():
            axis = slot["axis"]
            axis.setStyle(showValues=False)
            axis.setLabel("")
            if axis is self.left_axis:
                axis.show()
            else:
                axis.hide()
        self._clear_grid("right1")
        self._clear_grid("right2")

    def _show_active_axes(self):
        self._hide_all_axes()
        for unit in self.unit_order:
            slot_name = self._slot_for_unit(unit)
            if slot_name is None:
                continue
            axis = self.axis_slots[slot_name]["axis"]
            axis.setStyle(showValues=True)
            axis.setLabel(UNIT_AXIS_LABELS.get(unit, unit))
            axis.show()
        self._update_all_grids()

    def _slot_for_unit(self, unit: str) -> Optional[str]:
        slots = ["left", "right1", "right2"]
        if unit not in self.unit_order:
            return None
        idx = self.unit_order.index(unit)
        return slots[idx] if idx < len(slots) else None

    def _vb_for_unit(self, unit: str) -> pg.ViewBox:
        slot = self._slot_for_unit(unit)
        return self.axis_slots[slot]["viewbox"] if slot else self.main_vb

    # --- curve management ---

    def _clear_curves(self):
        for item in self.curves.values():
            try:
                item["viewbox"].removeItem(item["curve"])
            except Exception:
                pass
        self.curves.clear()

    def _rebuild_legend(self):
        legend = self.plot_item.legend
        if legend:
            legend.clear()
            for key, item in self.curves.items():
                legend.addItem(item["curve"], SIGNALS[key]["label"])

    def _auto_range(self):
        if self._loaded is None:
            return
        x_finite = self._loaded.x[np.isfinite(self._loaded.x)]
        if x_finite.size:
            self.main_vb.setXRange(float(x_finite.min()), float(x_finite.max()), padding=0.02)

        for unit in self.unit_order:
            vb = self._vb_for_unit(unit)
            all_y = []
            for item in self.curves.values():
                if item["unit"] == unit:
                    y_data = item["curve"].getData()[1]
                    if y_data is not None:
                        finite = y_data[np.isfinite(y_data)]
                        if finite.size:
                            all_y.append(finite)
            if not all_y:
                continue
            combined = np.concatenate(all_y)
            y_min, y_max = float(combined.min()), float(combined.max())
            if y_min == y_max:
                pad = 1.0 if y_min == 0 else abs(y_min) * 0.1
            else:
                pad = (y_max - y_min) * 0.05
            vb.setYRange(y_min - pad, y_max + pad, padding=0)

        self._sync_views()

    # --- public API ---

    def refresh(self, loaded: Optional[LoadedCSV], active_keys: List[str], window: int = 1):
        """Re-draw all active signals. Pass window > 1 to apply a moving average."""
        self._loaded = loaded
        self._clear_curves()
        self.unit_order = []
        self._hide_all_axes()
        self._rebuild_legend()

        if loaded is None or not active_keys:
            self.export_btn.setEnabled(False)
            self.reset_btn.setEnabled(False)
            return

        for key in active_keys:
            unit = SIGNALS[key]["unit"]
            if unit not in self.unit_order:
                self.unit_order.append(unit)
        self.unit_order = self.unit_order[:3]

        self._show_active_axes()

        for key in active_keys:
            unit = SIGNALS[key]["unit"]
            if unit not in self.unit_order:
                continue
            y = loaded.series[key]
            if window > 1:
                y = moving_average(y, window)
            vb = self._vb_for_unit(unit)
            pen = pg.mkPen(color=SIGNALS[key]["color"], width=2)
            curve = pg.PlotDataItem(loaded.x, y, pen=pen, name=SIGNALS[key]["label"])
            vb.addItem(curve)
            self.curves[key] = {"curve": curve, "viewbox": vb, "unit": unit}

        self._rebuild_legend()
        self._auto_range()
        self.export_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)

    def clear(self):
        self._loaded = None
        self._clear_curves()
        self.unit_order = []
        self._hide_all_axes()
        self._rebuild_legend()
        self.export_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)

    def _on_reset_view(self):
        self._auto_range()

    def _on_export(self):
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot as PNG", "plot.png", "PNG Image (*.png)"
        )
        if not out_path:
            return
        try:
            exporter = ImageExporter(self.plot_widget.plotItem)
            exporter.parameters()["width"] = 2000
            exporter.export(out_path)
        except Exception as e:
            QMessageBox.critical(self, "Export error", f"Failed to export PNG:\n{e}")
            return
        QMessageBox.information(self, "Exported", f"Saved:\n{out_path}")


# =========================================================
# Main window
# =========================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Motorcycle Forensic Data Visualizer")
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))

        self.loaded: Optional[LoadedCSV] = None
        self._last_dir: str = ""
        self.checkboxes: Dict[str, QCheckBox] = {}

        # ---- Left panel ----
        self.load_btn = QPushButton("Load CSV File…")
        self.load_btn.clicked.connect(self.on_load_csv)

        self.status_lbl = QLabel("No file loaded.")
        self.status_lbl.setWordWrap(True)

        checkbox_widget = QWidget()
        cb_layout = QVBoxLayout(checkbox_widget)
        cb_layout.setAlignment(Qt.AlignTop)
        cb_layout.setSpacing(4)
        for key, cfg in SIGNALS.items():
            cb = QCheckBox(cfg["label"])
            cb.setEnabled(False)
            cb.stateChanged.connect(self.on_signal_toggled)
            self.checkboxes[key] = cb
            cb_layout.addWidget(cb)

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

        self.raw_table = QTableView()
        self.raw_table.setSortingEnabled(False)
        self.raw_table_model = CSVTableModel()
        self.raw_table.setModel(self.raw_table_model)

        self.stats_table = QTableView()
        self.stats_table.setSortingEnabled(False)
        self.stats_table_model = SignalStatsTableModel()
        self.stats_table.setModel(self.stats_table_model)

        raw_tab = QWidget()
        raw_tab_layout = QVBoxLayout(raw_tab)
        raw_tab_layout.setContentsMargins(4, 4, 4, 4)
        raw_tab_layout.addWidget(self.raw_panel)

        # ---- Data tab ----
        raw_tbl_wrap = QWidget()
        rtl = QVBoxLayout(raw_tbl_wrap)
        rtl.setContentsMargins(0, 0, 0, 0)
        rtl.addWidget(QLabel("Raw CSV Data"))
        rtl.addWidget(self.raw_table)

        stats_tbl_wrap = QWidget()
        stl = QVBoxLayout(stats_tbl_wrap)
        stl.setContentsMargins(0, 0, 0, 0)
        stl.addWidget(QLabel("Signal Statistics"))
        stl.addWidget(self.stats_table)

        tables_splitter = QSplitter(Qt.Horizontal)
        tables_splitter.addWidget(raw_tbl_wrap)
        tables_splitter.addWidget(stats_tbl_wrap)
        tables_splitter.setStretchFactor(0, 3)
        tables_splitter.setStretchFactor(1, 2)
        tables_splitter.setSizes([700, 400])

        data_tab = QWidget()
        data_tab_layout = QVBoxLayout(data_tab)
        data_tab_layout.setContentsMargins(4, 4, 4, 4)
        data_tab_layout.addWidget(tables_splitter)

        # ---- Tab widget ----
        self.tabs = QTabWidget()
        self.tabs.addTab(raw_tab, "Raw Signals")
        self.tabs.addTab(data_tab, "Data")

        # ---- Main splitter ----
        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 990])

        self.setCentralWidget(splitter)

    # ---- Helpers ----

    def _active_keys(self) -> List[str]:
        return [k for k, cb in self.checkboxes.items() if cb.isEnabled() and cb.isChecked()]

    def _refresh_panel(self):
        self.raw_panel.refresh(self.loaded, self._active_keys())

    # ---- Slots ----

    def on_load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV Log File", self._last_dir, "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return

        try:
            self.loaded = load_csv(path)
        except Exception as e:
            QMessageBox.critical(self, "Load error", f"Failed to load CSV:\n{e}")
            return

        self._last_dir = os.path.dirname(path)

        sr_text = f"  |  ~{self.loaded.sample_rate:.0f} Hz" if self.loaded.sample_rate else ""
        self.status_lbl.setText(
            f"{os.path.basename(path)}\n{len(self.loaded.rows)} rows{sr_text}"
        )

        self.raw_table_model.set_csv_data(self.loaded.headers, self.loaded.rows)
        self.raw_table.resizeColumnsToContents()
        self.stats_table_model.set_loaded_csv(self.loaded)
        self.stats_table.resizeColumnsToContents()

        any_signal = False
        for key, cb in self.checkboxes.items():
            present = key in self.loaded.series
            cb.blockSignals(True)
            cb.setEnabled(present)
            cb.setChecked(False)
            cb.blockSignals(False)
            any_signal = any_signal or present

        self.raw_panel.clear()

        if not any_signal:
            QMessageBox.warning(
                self, "No signals found",
                "No expected signal columns were found in this CSV.\n"
                "Please verify the file is from the HAN datalogger.",
            )

    def on_signal_toggled(self):
        if not self.loaded:
            return

        active = self._active_keys()
        units: List[str] = []
        for key in active:
            u = SIGNALS[key]["unit"]
            if u not in units:
                units.append(u)

        if len(units) > 3:
            sender = self.sender()
            if isinstance(sender, QCheckBox):
                sender.blockSignals(True)
                sender.setChecked(False)
                sender.blockSignals(False)
            QMessageBox.warning(
                self, "Too many unit groups",
                "Only three different unit groups (m/s², deg, km/h) can be shown at once.",
            )
            return

        self._refresh_panel()

    def select_all_signals(self):
        if not self.loaded:
            return
        for cb in self.checkboxes.values():
            if cb.isEnabled():
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)
        self._refresh_panel()

    def deselect_all_signals(self):
        for cb in self.checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._refresh_panel()


# =========================================================
# Main
# =========================================================

def main():
    app = QApplication([])
    app.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
