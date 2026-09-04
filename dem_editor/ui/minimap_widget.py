"""
dem_editor/ui/minimap_widget.py
Global 2D overview minimap widget showing full DEM as pixel image with an interactive viewport indicator.
"""

from typing import Optional, Tuple
import numpy as np
import matplotlib.pyplot as plt
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QImage, QPixmap, QPen, QBrush, QColor, QFont
from PyQt6.QtWidgets import QWidget

from dem_editor.core.dem_model import DEMModel


class DEMMinimapWidget(QWidget):
    """
    Minimap displaying the full DEM as a colored pixel image.
    Renders an interactive bounding box showing the current table viewport.
    Clicking or dragging updates the table viewport position.
    """

    cellSelected = pyqtSignal(int, int)  # Emits (row, col) when user clicks/drags on minimap

    def __init__(self, dem_model: DEMModel, parent=None):
        super().__init__(parent)
        self._dem = dem_model
        self.setMinimumSize(180, 180)
        self.setMouseTracking(True)

        self.colormap_name = "terrain"
        self._pixmap: Optional[QPixmap] = None
        self._img_rect = QRectF()

        # Viewport boundaries currently visible in table
        self._r_min = 0
        self._r_max = 0
        self._c_min = 0
        self._c_max = 0

        self._is_dragging = False

        # Connect model signals
        self._dem.dataChanged.connect(self.update_pixmap)
        self._dem.metadataChanged.connect(self.update_pixmap)

    def set_colormap(self, name: str):
        if self.colormap_name != name:
            self.colormap_name = name
            self.update_pixmap()

    def set_visible_viewport(self, r_min: int, r_max: int, c_min: int, c_max: int):
        self._r_min = r_min
        self._r_max = r_max
        self._c_min = c_min
        self._c_max = c_max
        self.update()

    def update_pixmap(self):
        """Generates QPixmap from DEM array using matplotlib colormap."""
        data = self._dem.data
        if data.size == 0:
            self._pixmap = None
            self.update()
            return

        nrows, ncols = data.shape

        # Normalize data to [0, 1] ignoring NaNs
        valid_mask = ~np.isnan(data)
        if not np.any(valid_mask):
            norm_data = np.zeros_like(data)
        else:
            vmin = np.nanmin(data)
            vmax = np.nanmax(data)
            if vmin == vmax:
                norm_data = np.zeros_like(data)
            else:
                norm_data = (data - vmin) / (vmax - vmin)

        # Apply colormap
        cmap = plt.get_cmap(self.colormap_name)
        rgba = cmap(norm_data)  # shape (nrows, ncols, 4) in [0, 1]

        # Convert to 8-bit uint8 RGBA
        rgba_uint8 = (rgba * 255).astype(np.uint8)

        # Highlight NaNs in bright magenta: (255, 0, 180, 255)
        rgba_uint8[~valid_mask] = [255, 20, 147, 255]

        # If origin_bottom (FUNWAVE mode), row 0 is at bottom, so flip vertically for image display
        if self._dem.metadata.origin_bottom:
            rgba_uint8 = np.flipud(rgba_uint8)

        h, w, _ = rgba_uint8.shape
        # Create QImage (must use bytes/contiguous buffer)
        contiguous = np.ascontiguousarray(rgba_uint8)
        bytes_per_line = 4 * w
        qimg = QImage(
            contiguous.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_RGBA8888,
        )
        self._pixmap = QPixmap.fromImage(qimg)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Background
        painter.fillRect(self.rect(), QColor(24, 24, 28))

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Sin DEM cargado",
            )
            return

        # Calculate aspect-ratio-preserving rect for the DEM image with small margin
        margin = 14
        available_w = max(10, self.width() - 2 * margin)
        available_h = max(10, self.height() - 2 * margin)

        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()

        scale = min(available_w / pix_w, available_h / pix_h)
        draw_w = pix_w * scale
        draw_h = pix_h * scale
        draw_x = (self.width() - draw_w) / 2.0
        draw_y = (self.height() - draw_h) / 2.0

        self._img_rect = QRectF(draw_x, draw_y, draw_w, draw_h)

        # Draw the DEM map
        painter.drawPixmap(
            int(draw_x),
            int(draw_y),
            int(draw_w),
            int(draw_h),
            self._pixmap,
        )

        # Draw image border
        painter.setPen(QPen(QColor(60, 60, 70), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._img_rect)

        # Draw Viewport Box
        nrows, ncols = self._dem.shape
        if nrows > 0 and ncols > 0:
            origin_bottom = self._dem.metadata.origin_bottom

            # Horizontal bounds: c_min to c_max
            x_min_norm = max(0, self._c_min) / float(ncols)
            x_max_norm = min(ncols, self._c_max + 1) / float(ncols)

            # Vertical bounds
            if origin_bottom:
                # Row 0 is at bottom of image
                y_max_norm = 1.0 - (max(0, self._r_min) / float(nrows))
                y_min_norm = 1.0 - (min(nrows, self._r_max + 1) / float(nrows))
            else:
                y_min_norm = max(0, self._r_min) / float(nrows)
                y_max_norm = min(nrows, self._r_max + 1) / float(nrows)

            box_x = draw_x + x_min_norm * draw_w
            box_y = draw_y + min(y_min_norm, y_max_norm) * draw_h
            box_w = max(3.0, (x_max_norm - x_min_norm) * draw_w)
            box_h = max(3.0, abs(y_max_norm - y_min_norm) * draw_h)

            viewport_rect = QRectF(box_x, box_y, box_w, box_h)

            # Fill with semi-transparent cyan/blue
            painter.setBrush(QBrush(QColor(0, 200, 255, 45)))
            # Pen with high contrast cyan
            painter.setPen(QPen(QColor(0, 230, 255), 1.8, Qt.PenStyle.SolidLine))
            painter.drawRect(viewport_rect)

        # Coordinate annotations
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(180, 180, 195))
        if self._dem.metadata.origin_bottom:
            painter.drawText(
                int(draw_x),
                int(draw_y + draw_h + 12),
                f"Sur (Fila 0) | Dim: {nrows}×{ncols}",
            )
            painter.drawText(
                int(draw_x),
                int(draw_y - 3),
                "Norte (Fila N-1)",
            )
        else:
            painter.drawText(
                int(draw_x),
                int(draw_y - 3),
                f"Fila 0 (Norte) | Dim: {nrows}×{ncols}",
            )
            painter.drawText(
                int(draw_x),
                int(draw_y + draw_h + 12),
                "Fila N-1 (Sur)",
            )

    def _coord_from_pos(self, pos) -> Optional[Tuple[int, int]]:
        """Maps widget (x, y) to DEM (row, col)."""
        if self._dem.data.size == 0 or self._img_rect.width() <= 0 or self._img_rect.height() <= 0:
            return None

        # Clamp to image rect
        rel_x = (pos.x() - self._img_rect.x()) / self._img_rect.width()
        rel_y = (pos.y() - self._img_rect.y()) / self._img_rect.height()

        rel_x = max(0.0, min(1.0, rel_x))
        rel_y = max(0.0, min(1.0, rel_y))

        nrows, ncols = self._dem.shape
        col = int(rel_x * ncols)
        col = min(ncols - 1, max(0, col))

        if self._dem.metadata.origin_bottom:
            row = int((1.0 - rel_y) * nrows)
        else:
            row = int(rel_y * nrows)
        row = min(nrows - 1, max(0, row))

        return row, col

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            coord = self._coord_from_pos(event.position())
            if coord:
                self._is_dragging = True
                self.cellSelected.emit(*coord)
                event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            coord = self._coord_from_pos(event.position())
            if coord:
                self.cellSelected.emit(*coord)
                event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()
