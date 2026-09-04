"""
dem_editor/ui/profile_widget.py
Real-time 1D Cross-Section (Transect) profile viewer along active row / column.
"""

from typing import Optional
import numpy as np
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel

from dem_editor.core.dem_model import DEMModel


class ProfilePlotWidget(QWidget):
    """Draws 1D transect curve."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.profile_data: Optional[np.ndarray] = None
        self.active_idx: int = 0
        self.title: str = "Perfil 1D"
        self.coord_label: str = "X"

    def set_data(self, profile: np.ndarray, active_idx: int, title: str, coord_label: str):
        self.profile_data = profile
        self.active_idx = active_idx
        self.title = title
        self.coord_label = coord_label
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Background
        painter.fillRect(self.rect(), QColor(20, 20, 24))

        if self.profile_data is None or len(self.profile_data) == 0:
            painter.setPen(QColor(120, 120, 130))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Selecciona una celda para ver el perfil")
            return

        w = self.width()
        h = self.height()
        pad_l, pad_r, pad_t, pad_b = 48, 15, 26, 20
        plot_w = max(10, w - pad_l - pad_r)
        plot_h = max(10, h - pad_t - pad_b)

        # Filter valid numbers for min/max
        valid = self.profile_data[~np.isnan(self.profile_data)]
        if len(valid) == 0:
            vmin, vmax = -1.0, 1.0
        else:
            vmin = float(np.min(valid))
            vmax = float(np.max(valid))
            if vmin == vmax:
                vmin -= 1.0
                vmax += 1.0

        n = len(self.profile_data)

        # Title and stats
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        painter.setPen(QColor(180, 200, 240))
        cur_val = self.profile_data[self.active_idx] if 0 <= self.active_idx < n else np.nan
        cur_str = "NaN" if np.isnan(cur_val) else f"{cur_val:.3f}"
        painter.drawText(pad_l, 17, f"{self.title}  [{self.coord_label}={self.active_idx} | Z={cur_str}]")

        # Plot axes border
        painter.setPen(QPen(QColor(50, 50, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(pad_l, pad_t, plot_w, plot_h)

        # Y axis ticks
        painter.setFont(QFont("Arial", 8))
        painter.setPen(QColor(130, 130, 140))
        painter.drawText(5, pad_t + 10, f"{vmax:.1f}")
        painter.drawText(5, pad_t + plot_h, f"{vmin:.1f}")

        # Zero line if in range
        if vmin < 0 < vmax:
            y_zero = pad_t + (1.0 - (0.0 - vmin) / (vmax - vmin)) * plot_h
            painter.setPen(QPen(QColor(80, 80, 90), 1, Qt.PenStyle.DashLine))
            painter.drawLine(pad_l, int(y_zero), pad_l + plot_w, int(y_zero))

        # Plot polyline
        line_pen = QPen(QColor(80, 180, 255), 1.8)
        nan_pen = QPen(QColor(255, 60, 120), 1.5, Qt.PenStyle.DotLine)

        points = []
        for i, val in enumerate(self.profile_data):
            x = pad_l + (i / max(1, n - 1)) * plot_w
            if np.isnan(val):
                if len(points) > 1:
                    painter.setPen(line_pen)
                    for j in range(len(points) - 1):
                        painter.drawLine(points[j], points[j + 1])
                points = []
            else:
                y = pad_t + (1.0 - (val - vmin) / (vmax - vmin)) * plot_h
                points.append(QPointF(x, y))

        if len(points) > 1:
            painter.setPen(line_pen)
            for j in range(len(points) - 1):
                painter.drawLine(points[j], points[j + 1])

        # Draw active cell marker
        if 0 <= self.active_idx < n:
            act_x = pad_l + (self.active_idx / max(1, n - 1)) * plot_w
            act_val = self.profile_data[self.active_idx]
            if not np.isnan(act_val):
                act_y = pad_t + (1.0 - (act_val - vmin) / (vmax - vmin)) * plot_h
                painter.setPen(QPen(QColor(255, 230, 0), 2))
                painter.setBrush(QBrush(QColor(255, 230, 0)))
                painter.drawEllipse(QPointF(act_x, act_y), 4.0, 4.0)

            # Vertical guide line
            painter.setPen(QPen(QColor(255, 230, 0, 120), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(act_x), pad_t, int(act_x), pad_t + plot_h)


class DEMProfileWidget(QWidget):
    """Container widget with toggle buttons for X and Y cross-sections."""

    def __init__(self, dem_model: DEMModel, parent=None):
        super().__init__(parent)
        self._dem = dem_model
        self.mode = "X"  # 'X' for row transect (along cols), 'Y' for col transect (along rows)
        self.cur_r = 0
        self.cur_c = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_x = QPushButton("Perfil X (Fila)")
        self.btn_x.setCheckable(True)
        self.btn_x.setChecked(True)
        self.btn_x.clicked.connect(self._select_x)

        self.btn_y = QPushButton("Perfil Y (Columna)")
        self.btn_y.setCheckable(True)
        self.btn_y.setChecked(False)
        self.btn_y.clicked.connect(self._select_y)

        header_layout.addWidget(self.btn_x)
        header_layout.addWidget(self.btn_y)
        header_layout.addStretch()

        self.plot_widget = ProfilePlotWidget(self)

        layout.addLayout(header_layout)
        layout.addWidget(self.plot_widget)

        self._dem.dataChanged.connect(self.refresh)

    def _select_x(self):
        self.mode = "X"
        self.btn_x.setChecked(True)
        self.btn_y.setChecked(False)
        self.refresh()

    def _select_y(self):
        self.mode = "Y"
        self.btn_x.setChecked(False)
        self.btn_y.setChecked(True)
        self.refresh()

    def update_cell(self, row: int, col: int):
        self.cur_r = row
        self.cur_c = col
        self.refresh()

    def refresh(self):
        data = self._dem.data
        if data.size == 0:
            self.plot_widget.set_data(np.array([]), 0, "", "")
            return

        nrows, ncols = data.shape
        r = max(0, min(nrows - 1, self.cur_r))
        c = max(0, min(ncols - 1, self.cur_c))

        if self.mode == "X":
            # Transect along row r (varying cols)
            profile = data[r, :]
            title = f"Transecto Horizontal (Fila {r})"
            self.plot_widget.set_data(profile, c, title, "Columna")
        else:
            # Transect along col c (varying rows)
            profile = data[:, c]
            title = f"Transecto Vertical (Columna {c})"
            self.plot_widget.set_data(profile, r, title, "Fila")
