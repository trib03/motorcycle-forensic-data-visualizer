"""Table models for the Data tab.

``SignalStatsTableModel`` can compute either whole-file stats or just the
stats for a user-selected time region (the "zoom to event" workflow).
"""

from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ..csv_loader import LoadedCSV
from ..signals import SIGNALS


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
        self._loaded: Optional[LoadedCSV] = None
        self._region: Optional[Tuple[float, float]] = None

    # ---- Public ----

    def set_loaded_csv(self, loaded: Optional[LoadedCSV]):
        self._loaded = loaded
        self._region = None
        self._rebuild()

    def set_region(self, region: Optional[Tuple[float, float]]):
        self._region = region
        self._rebuild()

    # ---- Internal ----

    def _rebuild(self):
        self.beginResetModel()
        self._rows = []
        if self._loaded is not None:
            if self._region is not None:
                xmin, xmax = self._region
                mask = (self._loaded.x >= xmin) & (self._loaded.x <= xmax)
            else:
                mask = np.ones_like(self._loaded.x, dtype=bool)
            for key in SIGNALS:
                if key not in self._loaded.series:
                    continue
                label = SIGNALS[key]["label"]
                y = self._loaded.series[key][mask]
                finite = y[np.isfinite(y)]
                if finite.size == 0:
                    self._rows.append([label, "-", "-", "-"])
                else:
                    self._rows.append([
                        label,
                        f"{float(np.min(finite)):.3f}",
                        f"{float(np.mean(finite)):.3f}",
                        f"{float(np.max(finite)):.3f}",
                    ])
            if self._region is not None:
                header = self._col_headers[0] + f"  [t={self._region[0]:.3f}..{self._region[1]:.3f}s]"
            else:
                header = "Signal"
            self._col_headers = [header, "Min", "Avg", "Max"]
        else:
            self._col_headers = ["Signal", "Min", "Avg", "Max"]
        self.endResetModel()

    # ---- QAbstractTableModel ----

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
