"""About and Calibration dialogs."""

import platform
import sys
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .. import __app_name__, __publisher__, __version__
from ..calibration import (
    Calibration,
    calibration_presets_dir,
    save_default_calibration,
)


class AboutDialog(QDialog):
    def __init__(self, parent=None, icon_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"About {__app_name__}")
        self.setMinimumWidth(420)

        title = QLabel(f"<h2>{__app_name__}</h2>")
        version = QLabel(f"<b>Version:</b> {__version__}")
        publisher = QLabel(f"<b>Publisher:</b> {__publisher__}")

        # Pull dependency versions at runtime so the dialog stays accurate
        deps_lines = []
        for pkg in ("PySide6", "pyqtgraph", "numpy", "scipy"):
            try:
                mod = __import__(pkg)
                v = getattr(mod, "__version__", "?")
                deps_lines.append(f"{pkg}: {v}")
            except Exception:
                deps_lines.append(f"{pkg}: not available")
        env = QLabel(
            "<b>Runtime:</b><br>"
            f"Python: {sys.version.split()[0]}<br>"
            f"OS: {platform.platform()}<br><br>"
            "<b>Dependencies:</b><br>" + "<br>".join(deps_lines)
        )
        env.setTextFormat(Qt.RichText)

        layout = QVBoxLayout(self)

        if icon_path and Path(icon_path).exists():
            pix = QPixmap(icon_path).scaledToWidth(64, Qt.SmoothTransformation)
            icon_label = QLabel()
            icon_label.setPixmap(pix)
            layout.addWidget(icon_label, alignment=Qt.AlignHCenter)

        layout.addWidget(title, alignment=Qt.AlignHCenter)
        layout.addWidget(version)
        layout.addWidget(publisher)
        layout.addSpacing(8)
        layout.addWidget(env)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class CalibrationDialog(QDialog):
    """Edit the active calibration profile and optionally save it as a preset."""

    def __init__(self, calibration: Calibration, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibration Profile")
        self.setMinimumWidth(440)

        self._cal = Calibration(**{f.name: getattr(calibration, f.name)
                                   for f in fields(Calibration)})

        # ---- Geometry group ----
        geom = QGroupBox("Wheel geometry")
        gf = QFormLayout(geom)
        self.front_circ = self._double(0.1, 5.0, 3, " m", self._cal.front_wheel_circumference_m)
        self.rear_circ = self._double(0.1, 5.0, 3, " m", self._cal.rear_wheel_circumference_m)
        self.abs_slots = self._int(1, 1000, self._cal.abs_ring_slots, " slots")
        gf.addRow("Front wheel circumference:", self.front_circ)
        gf.addRow("Rear wheel circumference:", self.rear_circ)
        gf.addRow("ABS ring slots:", self.abs_slots)

        # ---- Filtering group ----
        filt = QGroupBox("Default filter cutoffs")
        ff = QFormLayout(filt)
        self.accel_cut = self._double(0.01, 1000.0, 3, " Hz", self._cal.accel_filter_cutoff_hz)
        self.gyro_cut = self._double(0.01, 1000.0, 3, " Hz", self._cal.gyro_filter_cutoff_hz)
        self.order = self._int(1, 10, self._cal.filtfilt_order)
        ff.addRow("Acceleration low-pass:", self.accel_cut)
        ff.addRow("Gyro low-pass:", self.gyro_cut)
        ff.addRow("Filter order:", self.order)

        # ---- Drift group ----
        drift = QGroupBox("Gyro drift correction")
        df = QFormLayout(drift)
        self.drift_hp = self._double(0.001, 100.0, 4, " Hz", self._cal.gyro_drift_hp_hz)
        self.anchor = self._double(0.05, 60.0, 3, " s", self._cal.gyro_drift_anchor_sec)
        df.addRow("High-pass cutoff:", self.drift_hp)
        df.addRow("Anchor window:", self.anchor)

        # ---- Preset buttons ----
        preset_row = QHBoxLayout()
        load_btn = QPushButton("Load preset…")
        load_btn.clicked.connect(self._on_load_preset)
        save_btn = QPushButton("Save preset…")
        save_btn.clicked.connect(self._on_save_preset)
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._on_reset)
        preset_row.addWidget(load_btn)
        preset_row.addWidget(save_btn)
        preset_row.addWidget(reset_btn)

        # ---- Apply / Cancel ----
        bb = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Apply | QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self._on_save_and_close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)

        layout = QVBoxLayout(self)
        layout.addWidget(geom)
        layout.addWidget(filt)
        layout.addWidget(drift)
        layout.addLayout(preset_row)
        layout.addWidget(bb)

        self._result_cal = None

    # ---- Helpers ----

    def _double(self, lo, hi, decimals, suffix, value):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
        w.setSuffix(suffix)
        w.setValue(value)
        return w

    def _int(self, lo, hi, value, suffix=""):
        w = QSpinBox()
        w.setRange(lo, hi)
        if suffix:
            w.setSuffix(suffix)
        w.setValue(value)
        return w

    def _read_into(self, cal: Calibration):
        cal.front_wheel_circumference_m = self.front_circ.value()
        cal.rear_wheel_circumference_m = self.rear_circ.value()
        cal.abs_ring_slots = self.abs_slots.value()
        cal.accel_filter_cutoff_hz = self.accel_cut.value()
        cal.gyro_filter_cutoff_hz = self.gyro_cut.value()
        cal.filtfilt_order = self.order.value()
        cal.gyro_drift_hp_hz = self.drift_hp.value()
        cal.gyro_drift_anchor_sec = self.anchor.value()
        return cal

    def _write_from(self, cal: Calibration):
        self.front_circ.setValue(cal.front_wheel_circumference_m)
        self.rear_circ.setValue(cal.rear_wheel_circumference_m)
        self.abs_slots.setValue(cal.abs_ring_slots)
        self.accel_cut.setValue(cal.accel_filter_cutoff_hz)
        self.gyro_cut.setValue(cal.gyro_filter_cutoff_hz)
        self.order.setValue(cal.filtfilt_order)
        self.drift_hp.setValue(cal.gyro_drift_hp_hz)
        self.anchor.setValue(cal.gyro_drift_anchor_sec)

    # ---- Slots ----

    def _on_apply(self):
        self._read_into(self._cal)
        self._result_cal = Calibration(**{f.name: getattr(self._cal, f.name)
                                          for f in fields(Calibration)})

    def _on_save_and_close(self):
        self._on_apply()
        try:
            save_default_calibration(self._cal)
        except Exception as e:
            QMessageBox.warning(self, "Save failed",
                                f"Could not persist calibration:\n{e}")
        self.accept()

    def _on_load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load calibration preset",
            str(calibration_presets_dir()),
            "Calibration JSON (*.json)",
        )
        if not path:
            return
        try:
            cal = Calibration.load(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Load failed", str(e))
            return
        self._cal = cal
        self._write_from(cal)

    def _on_save_preset(self):
        self._read_into(self._cal)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save calibration preset",
            str(calibration_presets_dir() / f"{self._cal.name}.json"),
            "Calibration JSON (*.json)",
        )
        if not path:
            return
        try:
            self._cal.save(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_reset(self):
        self._cal = Calibration()
        self._write_from(self._cal)

    # ---- Public ----

    def result_calibration(self):
        return self._result_cal or self._cal
