"""Reusable plot add-ons that span one *or many* stacked PlotItems.

* ``MultiPlotCrosshair`` — one vertical line per plot, all at the same x; each
  plot prints the values of its own visible curves.
* ``MirroredRegionSelector`` — a draggable region on the master plot is
  mirrored as visual bands on all other plots.
* ``GapShader`` — faint red bands over sample-rate gaps, applied per plot.
"""

from typing import Callable, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor


CurveSource = Callable[[], List[Tuple[str, np.ndarray, np.ndarray, str]]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_at(xs: np.ndarray, ys: np.ndarray, x_val: float) -> Optional[float]:
    if xs is None or ys is None or len(xs) == 0 or len(ys) == 0:
        return None
    if x_val < xs[0] or x_val > xs[-1]:
        return None
    idx = int(np.searchsorted(xs, x_val))
    if idx <= 0:
        return float(ys[0]) if np.isfinite(ys[0]) else None
    if idx >= len(xs):
        return float(ys[-1]) if np.isfinite(ys[-1]) else None
    x0, x1 = xs[idx - 1], xs[idx]
    y0, y1 = ys[idx - 1], ys[idx]
    if not (np.isfinite(y0) and np.isfinite(y1)):
        if np.isfinite(y0):
            return float(y0)
        if np.isfinite(y1):
            return float(y1)
        return None
    if x1 == x0:
        return float(y0)
    t = (x_val - x0) / (x1 - x0)
    return float(y0 + t * (y1 - y0))


# ---------------------------------------------------------------------------
# Multi-plot crosshair
# ---------------------------------------------------------------------------

class MultiPlotCrosshair(QObject):
    """A crosshair that spans several stacked PlotItems.

    Each plot gets its own vertical line and per-plot value-readout label,
    but they all share the same x position so the user can read a single
    moment in time across all signals at once.
    """

    def __init__(self,
                 plot_items: List[pg.PlotItem],
                 curve_sources: List[CurveSource],
                 parent=None):
        super().__init__(parent)
        self._plot_items = list(plot_items)
        self._curve_sources = list(curve_sources)
        self._enabled = False
        self._text_color = "#FFFFFF"

        self._lines: List[pg.InfiniteLine] = []
        self._labels: List[pg.TextItem] = []
        self._proxies = []

        for pi in self._plot_items:
            line = pg.InfiniteLine(angle=90, movable=False,
                                   pen=pg.mkPen("#888", width=1,
                                                style=Qt.DashLine))
            line.setZValue(50)
            label = pg.TextItem(anchor=(0, 0))
            label.setZValue(60)
            label.setColor(QColor(self._text_color))
            self._lines.append(line)
            self._labels.append(label)
            proxy = pg.SignalProxy(pi.scene().sigMouseMoved,
                                   rateLimit=60,
                                   slot=lambda ev, src=pi: self._on_move(ev, src))
            self._proxies.append(proxy)

    # ---- Public ----

    def set_enabled(self, on: bool):
        if on and not self._enabled:
            for pi, line, label in zip(self._plot_items, self._lines, self._labels):
                pi.addItem(line, ignoreBounds=True)
                pi.addItem(label, ignoreBounds=True)
            self._enabled = True
        elif not on and self._enabled:
            for pi, line, label in zip(self._plot_items, self._lines, self._labels):
                try:
                    pi.removeItem(line)
                    pi.removeItem(label)
                except Exception:
                    pass
            self._enabled = False

    def set_text_color(self, color: str):
        self._text_color = color
        for label in self._labels:
            label.setColor(QColor(color))

    def dispose(self):
        self.set_enabled(False)
        self._proxies = []

    # ---- Internal ----

    def _on_move(self, ev, source_plot):
        if not self._enabled:
            return
        pos = ev[0]
        if not source_plot.sceneBoundingRect().contains(pos):
            return
        view_pt = source_plot.vb.mapSceneToView(pos)
        x_val = float(view_pt.x())

        for pi, line, label, curve_src in zip(self._plot_items, self._lines,
                                              self._labels, self._curve_sources):
            line.setPos(x_val)
            lines = [f"<span><b>t = {x_val:.4g}</b></span>"]
            for sig_label, xs, ys, color in curve_src():
                v = _sample_at(xs, ys, x_val)
                if v is None:
                    continue
                lines.append(
                    f"<span style='color: {color};'>● {sig_label}: {v:.4g}</span>"
                )
            label.setHtml("<br>".join(lines))
            x_range, y_range = pi.vb.viewRange()
            label.setPos(x_range[0], y_range[1])


# ---------------------------------------------------------------------------
# Mirrored region selector
# ---------------------------------------------------------------------------

class MirroredRegionSelector(QObject):
    """A draggable LinearRegionItem on the master plot mirrored read-only on
    every other plot."""

    regionChanged = Signal(float, float)
    regionCleared = Signal()

    def __init__(self, plot_items: List[pg.PlotItem], parent=None):
        super().__init__(parent)
        self._plot_items = list(plot_items)
        self._enabled = False

        self._master = pg.LinearRegionItem(
            brush=pg.mkBrush(80, 160, 255, 40),
            pen=pg.mkPen("#3399FF", width=1),
        )
        self._master.setZValue(20)
        self._master.sigRegionChanged.connect(self._on_master_changed)
        self._master.sigRegionChangeFinished.connect(self._emit_changed)

        self._mirrors: List[pg.LinearRegionItem] = []
        for _ in plot_items[1:]:
            mirror = pg.LinearRegionItem(
                brush=pg.mkBrush(80, 160, 255, 30),
                pen=pg.mkPen("#3399FF", width=1, style=Qt.DotLine),
                movable=False,
            )
            mirror.setZValue(20)
            self._mirrors.append(mirror)

    def set_enabled(self, on: bool,
                    default_span: Optional[Tuple[float, float]] = None):
        if not self._plot_items:
            return
        if on and not self._enabled:
            if default_span is None:
                xr = self._plot_items[0].vb.viewRange()[0]
                w = xr[1] - xr[0]
                default_span = (xr[0] + 0.4 * w, xr[0] + 0.6 * w)
            self._master.setRegion(default_span)
            self._plot_items[0].addItem(self._master, ignoreBounds=True)
            for pi, mirror in zip(self._plot_items[1:], self._mirrors):
                mirror.setRegion(default_span)
                pi.addItem(mirror, ignoreBounds=True)
            self._enabled = True
            self._emit_changed()
        elif not on and self._enabled:
            try:
                self._plot_items[0].removeItem(self._master)
                for pi, mirror in zip(self._plot_items[1:], self._mirrors):
                    pi.removeItem(mirror)
            except Exception:
                pass
            self._enabled = False
            self.regionCleared.emit()

    def current(self) -> Optional[Tuple[float, float]]:
        if not self._enabled:
            return None
        lo, hi = self._master.getRegion()
        if lo > hi:
            lo, hi = hi, lo
        return float(lo), float(hi)

    def dispose(self):
        self.set_enabled(False)

    # ---- Internal ----

    def _on_master_changed(self):
        lo, hi = self._master.getRegion()
        for mirror in self._mirrors:
            mirror.setRegion((lo, hi))

    def _emit_changed(self):
        if not self._enabled:
            return
        lo, hi = self._master.getRegion()
        if lo > hi:
            lo, hi = hi, lo
        self.regionChanged.emit(float(lo), float(hi))


# ---------------------------------------------------------------------------
# Gap shading (per-plot)
# ---------------------------------------------------------------------------

class GapShader:
    def __init__(self, plot_items: List[pg.PlotItem]):
        self._plot_items = list(plot_items)
        self._items: List[Tuple[pg.PlotItem, pg.LinearRegionItem]] = []

    def set_gaps(self, gaps):
        self.clear()
        for pi in self._plot_items:
            for t0, t1 in gaps:
                region = pg.LinearRegionItem(
                    values=(t0, t1),
                    brush=pg.mkBrush(220, 60, 60, 40),
                    pen=pg.mkPen(0, 0, 0, 0),
                    movable=False,
                )
                region.setZValue(-5)
                pi.addItem(region, ignoreBounds=True)
                self._items.append((pi, region))

    def clear(self):
        for pi, region in self._items:
            try:
                pi.removeItem(region)
            except Exception:
                pass
        self._items = []
