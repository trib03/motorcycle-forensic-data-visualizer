"""Multi-plot panel for the Raw Signals tab.

* ``PlotView`` is the building block — one pyqtgraph plot with up to four
  Y-axes (still supports the original multi-unit layout).
* ``PlotPanel`` is the container: a vertical splitter of N PlotViews with a
  shared toolbar, crosshair that spans every plot, mirrored region selector,
  and gap shading.

The number of stacked plots is chosen by the user via a spinbox in the
toolbar.  Each signal is assigned to a specific plot through a per-row
spinbox in the MainWindow's left panel.
"""

from typing import Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..csv_loader import LoadedCSV
from ..signals import SIGNALS, UNIT_AXIS_LABELS
from .plot_features import (
    GapShader,
    MirroredRegionSelector,
    MultiPlotCrosshair,
)


# Items in pyqtgraph's right-click "Plot Options" submenu we want to hide.
_HIDDEN_PLOT_MENU_ITEMS = {"transforms", "downsample", "average",
                          "alpha", "points"}

# Fixed width (px) for the left Y-axis on every plot.  Forcing this means the
# y=0 line of plot 1 and plot 2 line up vertically — pyqtgraph otherwise sizes
# each plot's left axis based on its own tick label widths.
_LEFT_AXIS_WIDTH_PX = 60


# ---------------------------------------------------------------------------
# Single plot view
# ---------------------------------------------------------------------------

class PlotView(QWidget):
    """One pyqtgraph plot with up to four independent Y-axes."""

    def __init__(self):
        super().__init__()
        self.curves: Dict[str, Dict] = {}
        self.unit_order: List[str] = []
        self._right_grids: Dict[str, List[pg.InfiniteLine]] = {
            "right1": [], "right2": [], "right3": [],
        }

        self.plot_widget = pg.PlotWidget()
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=True, alpha=0.2)
        # Place legend on the right so it doesn't collide with the
        # top-left crosshair readout.
        self.plot_item.addLegend(offset=(-10, 10))

        self.main_vb = self.plot_item.vb
        self.left_axis = self.plot_item.getAxis("left")
        # Pin the left axis to a fixed width so stacked plots align vertically.
        self.left_axis.setStyle(autoExpandTextSpace=False)
        self.left_axis.setWidth(_LEFT_AXIS_WIDTH_PX)

        self.right_axis_1 = pg.AxisItem("right")
        self.right_axis_2 = pg.AxisItem("right")
        self.right_axis_3 = pg.AxisItem("right")
        self.plot_item.layout.addItem(self.right_axis_1, 2, 3)
        self.plot_item.layout.addItem(self.right_axis_2, 2, 4)
        self.plot_item.layout.addItem(self.right_axis_3, 2, 5)

        self.right_vb_1 = pg.ViewBox()
        self.right_vb_2 = pg.ViewBox()
        self.right_vb_3 = pg.ViewBox()
        self.plot_item.scene().addItem(self.right_vb_1)
        self.plot_item.scene().addItem(self.right_vb_2)
        self.plot_item.scene().addItem(self.right_vb_3)

        self.right_axis_1.linkToView(self.right_vb_1)
        self.right_axis_2.linkToView(self.right_vb_2)
        self.right_axis_3.linkToView(self.right_vb_3)
        self.right_vb_1.setXLink(self.main_vb)
        self.right_vb_2.setXLink(self.main_vb)
        self.right_vb_3.setXLink(self.main_vb)

        self.axis_slots = {
            "left":   {"axis": self.left_axis,    "viewbox": self.main_vb},
            "right1": {"axis": self.right_axis_1, "viewbox": self.right_vb_1},
            "right2": {"axis": self.right_axis_2, "viewbox": self.right_vb_2},
            "right3": {"axis": self.right_axis_3, "viewbox": self.right_vb_3},
        }

        self.main_vb.sigResized.connect(self._sync_views)
        self.main_vb.sigYRangeChanged.connect(lambda *_: self._update_all_grids())
        self.right_vb_1.sigYRangeChanged.connect(lambda *_: self._update_grid("right1"))
        self.right_vb_2.sigYRangeChanged.connect(lambda *_: self._update_grid("right2"))
        self.right_vb_3.sigYRangeChanged.connect(lambda *_: self._update_grid("right3"))

        self._strip_plot_menu()
        self._hide_all_axes()
        self._sync_views()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

    # ---- pyqtgraph context-menu pruning ----

    def _strip_plot_menu(self):
        """Hide the Transform/Downsample/Average/Alpha/Points entries from the
        pyqtgraph plot-options submenu."""
        try:
            menu = self.plot_item.ctrlMenu
        except Exception:
            return
        for action in menu.actions():
            text = (action.text() or "").lower()
            if any(bad in text for bad in _HIDDEN_PLOT_MENU_ITEMS):
                action.setVisible(False)

    # ---- view / axis management ----

    def _sync_views(self):
        rect = self.main_vb.sceneBoundingRect()
        self.right_vb_1.setGeometry(rect)
        self.right_vb_2.setGeometry(rect)
        self.right_vb_3.setGeometry(rect)
        self.right_vb_1.linkedViewChanged(self.main_vb, self.right_vb_1.XAxis)
        self.right_vb_2.linkedViewChanged(self.main_vb, self.right_vb_2.XAxis)
        self.right_vb_3.linkedViewChanged(self.main_vb, self.right_vb_3.XAxis)
        self._update_all_grids()

    def _update_all_grids(self):
        for s in ("right1", "right2", "right3"):
            self._update_grid(s)

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
        for s in ("right1", "right2", "right3"):
            self._clear_grid(s)

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
        slots = ["left", "right1", "right2", "right3"]
        if unit not in self.unit_order:
            return None
        idx = self.unit_order.index(unit)
        return slots[idx] if idx < len(slots) else None

    def _vb_for_unit(self, unit: str) -> pg.ViewBox:
        slot = self._slot_for_unit(unit)
        return self.axis_slots[slot]["viewbox"] if slot else self.main_vb

    # ---- curve management ----

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

    def auto_range(self, x: Optional[np.ndarray]):
        if x is not None:
            x_finite = x[np.isfinite(x)]
            if x_finite.size:
                self.main_vb.setXRange(float(x_finite.min()),
                                       float(x_finite.max()), padding=0.02)
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

    def curve_snapshot(self):
        """Return list of (label, x, y, color_hex) for visible curves."""
        out = []
        for key, item in self.curves.items():
            data = item["curve"].getData()
            if data[0] is None or data[1] is None:
                continue
            out.append((SIGNALS[key]["label"], data[0], data[1],
                        SIGNALS[key]["color"]))
        return out

    # ---- public API ----

    def refresh(self, loaded: Optional[LoadedCSV], active_keys: List[str]):
        self._clear_curves()
        self.unit_order = []
        self._hide_all_axes()
        self._rebuild_legend()

        if loaded is None or not active_keys:
            return

        for key in active_keys:
            if key not in loaded.series:
                continue
            unit = SIGNALS[key]["unit"]
            if unit not in self.unit_order:
                self.unit_order.append(unit)
        self.unit_order = self.unit_order[:4]

        self._show_active_axes()

        for key in active_keys:
            if key not in loaded.series:
                continue
            unit = SIGNALS[key]["unit"]
            if unit not in self.unit_order:
                continue
            y = loaded.series[key]
            vb = self._vb_for_unit(unit)
            pen = pg.mkPen(color=SIGNALS[key]["color"], width=2)
            curve = pg.PlotDataItem(loaded.x, y, pen=pen,
                                    name=SIGNALS[key]["label"])
            vb.addItem(curve)
            self.curves[key] = {"curve": curve, "viewbox": vb, "unit": unit}

        self._rebuild_legend()
        self.auto_range(loaded.x)

    def clear(self):
        self._clear_curves()
        self.unit_order = []
        self._hide_all_axes()
        self._rebuild_legend()

    def set_bottom_axis_visible(self, on: bool):
        ax = self.plot_item.getAxis("bottom")
        if on:
            ax.setStyle(showValues=True)
            ax.setLabel("Time (s) / Index")
            ax.show()
        else:
            ax.setStyle(showValues=False)
            ax.setLabel("")

    # ---- theme ----

    def apply_theme(self, dark: bool, text_color: str):
        self.plot_widget.setBackground("#101216" if dark else "w")
        for axis_name in ("left", "bottom"):
            self.plot_item.getAxis(axis_name).setTextPen(text_color)
            self.plot_item.getAxis(axis_name).setPen(text_color)
        for axis in (self.right_axis_1, self.right_axis_2, self.right_axis_3):
            axis.setTextPen(text_color)
            axis.setPen(text_color)


# ---------------------------------------------------------------------------
# Multi-plot container
# ---------------------------------------------------------------------------

class PlotPanel(QWidget):
    """N stacked PlotView widgets with linked X-axis and shared toolbar."""

    MAX_PLOTS = 4

    regionChanged = Signal(object)        # (lo, hi) or None

    def __init__(self):
        super().__init__()
        self._loaded: Optional[LoadedCSV] = None
        self._plot_views: List[PlotView] = []
        self._assignment: Dict[str, int] = {}
        self._dark = False
        self._text_color = "#202020"

        self._crosshair: Optional[MultiPlotCrosshair] = None
        self._region: Optional[MirroredRegionSelector] = None
        self._gaps: Optional[GapShader] = None

        # ---- Toolbar ----
        # The number of stacked plots is derived from the per-signal plot
        # assignment in MainWindow — no explicit spinbox here.
        self.reset_btn = QPushButton("Reset View")
        self.reset_btn.clicked.connect(self._on_reset_view)
        self.reset_btn.setEnabled(False)

        self.crosshair_cb = QCheckBox("Crosshair")
        self.crosshair_cb.setToolTip(
            "Vertical cursor across every plot that prints each visible "
            "signal's value at the mouse x position."
        )
        self.crosshair_cb.toggled.connect(self._on_crosshair_toggled)

        self.region_cb = QCheckBox("Region select")
        self.region_cb.setToolTip(
            "Drag the highlighted band to select a time window. The Data tab's "
            "stats update to match the selection."
        )
        self.region_cb.toggled.connect(self._on_region_toggled)

        self.export_btn = QPushButton("Export as PNG")
        self.export_btn.clicked.connect(self._on_export)
        self.export_btn.setEnabled(False)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.reset_btn)
        toolbar.addWidget(self.crosshair_cb)
        toolbar.addWidget(self.region_cb)
        toolbar.addStretch()
        toolbar.addWidget(self.export_btn)

        # ---- Splitter for stacked plots ----
        self.splitter = QSplitter(Qt.Vertical)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self.splitter, stretch=1)

        # Start with one plot
        self._set_plot_count_internal(1)

    # ------------------------------------------------------------------
    # Plot count / addons rebuild
    # ------------------------------------------------------------------

    def _set_plot_count_internal(self, n: int):
        n = max(1, min(self.MAX_PLOTS, int(n)))
        # Add
        while len(self._plot_views) < n:
            pv = PlotView()
            self._plot_views.append(pv)
            self.splitter.addWidget(pv)
        # Remove from the end
        while len(self._plot_views) > n:
            pv = self._plot_views.pop()
            pv.setParent(None)
            pv.deleteLater()

        # Link X-axes to plot 0
        for i, pv in enumerate(self._plot_views):
            pv.main_vb.setXLink(self._plot_views[0].main_vb if i > 0 else None)
            # Bottom axis only on the last view to save vertical space
            pv.set_bottom_axis_visible(i == len(self._plot_views) - 1)

        # Equal stretch
        for i in range(len(self._plot_views)):
            self.splitter.setStretchFactor(i, 1)

        self._rebuild_addons()
        self._apply_theme_to_views()

    def _rebuild_addons(self):
        if self._crosshair is not None:
            self._crosshair.dispose()
        if self._region is not None:
            self._region.dispose()
        if self._gaps is not None:
            self._gaps.clear()

        plot_items = [pv.plot_item for pv in self._plot_views]
        curve_sources = [pv.curve_snapshot for pv in self._plot_views]

        self._crosshair = MultiPlotCrosshair(plot_items, curve_sources, parent=self)
        self._region = MirroredRegionSelector(plot_items, parent=self)
        self._region.regionChanged.connect(
            lambda lo, hi: self.regionChanged.emit((lo, hi))
        )
        self._region.regionCleared.connect(
            lambda: self.regionChanged.emit(None)
        )
        self._gaps = GapShader(plot_items)

        # Restore enabled states
        self._crosshair.set_text_color(self._text_color)
        if self.crosshair_cb.isChecked():
            self._crosshair.set_enabled(True)
        if self.region_cb.isChecked() and self._loaded is not None:
            self._region.set_enabled(True)
        if self._loaded is not None:
            self._gaps.set_gaps(self._loaded.gaps)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_plot_count(self, n: int):
        self._set_plot_count_internal(int(n))

    def plot_count(self) -> int:
        return len(self._plot_views)

    def refresh(self, loaded: Optional[LoadedCSV],
                signal_assignment: Dict[str, int]):
        """Re-plot using a {signal_key: plot_index} map (1-based indices)."""
        self._loaded = loaded
        self._assignment = dict(signal_assignment or {})
        self._refresh_views()
        self.reset_btn.setEnabled(loaded is not None)
        self.export_btn.setEnabled(loaded is not None)
        if loaded is not None:
            self._gaps.set_gaps(loaded.gaps)

    def clear(self):
        self._loaded = None
        self._assignment = {}
        for pv in self._plot_views:
            pv.clear()
        if self._gaps:
            self._gaps.clear()
        self.reset_btn.setEnabled(False)
        self.export_btn.setEnabled(False)

    def current_region(self):
        return self._region.current() if self._region else None

    def set_crosshair_enabled(self, on: bool):
        self.crosshair_cb.setChecked(on)

    def set_region_enabled(self, on: bool):
        self.region_cb.setChecked(on)

    # Convenience: expose the master view's viewBox for x-range save/restore.
    @property
    def main_vb(self):
        return self._plot_views[0].main_vb if self._plot_views else None

    # ------------------------------------------------------------------
    # Refresh internals
    # ------------------------------------------------------------------

    def _refresh_views(self):
        # Group signals per plot index
        per_plot: Dict[int, List[str]] = {}
        n = len(self._plot_views)
        for key, plot_idx in self._assignment.items():
            # Clamp to currently-available plot indices
            idx = max(1, min(n, int(plot_idx)))
            per_plot.setdefault(idx - 1, []).append(key)

        for i, pv in enumerate(self._plot_views):
            keys = per_plot.get(i, [])
            pv.refresh(self._loaded, keys)

    # ------------------------------------------------------------------
    # Toolbar slots
    # ------------------------------------------------------------------

    def _on_reset_view(self):
        for pv in self._plot_views:
            pv.auto_range(self._loaded.x if self._loaded is not None else None)

    def _on_crosshair_toggled(self, on: bool):
        if self._crosshair:
            self._crosshair.set_enabled(on)

    def _on_region_toggled(self, on: bool):
        if self._loaded is None:
            # Don't enable the region until data is loaded
            if on:
                self.region_cb.blockSignals(True)
                self.region_cb.setChecked(False)
                self.region_cb.blockSignals(False)
            return
        if self._region:
            self._region.set_enabled(on)

    def _on_export(self):
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot as PNG", "plot.png", "PNG Image (*.png)"
        )
        if not out_path:
            return
        try:
            pix: QPixmap = self.splitter.grab()
            if not pix.save(out_path, "PNG"):
                raise RuntimeError("QPixmap.save returned False")
        except Exception as e:
            QMessageBox.critical(self, "Export error",
                                 f"Failed to export PNG:\n{e}")
            return
        QMessageBox.information(self, "Exported", f"Saved:\n{out_path}")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, dark: bool):
        self._dark = dark
        self._text_color = "#EEEEEE" if dark else "#202020"
        self._apply_theme_to_views()
        if self._crosshair:
            self._crosshair.set_text_color(self._text_color)

    def _apply_theme_to_views(self):
        for pv in self._plot_views:
            pv.apply_theme(self._dark, self._text_color)
