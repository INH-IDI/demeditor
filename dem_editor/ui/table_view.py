"""
dem_editor/ui/table_view.py
High-performance virtualized Excel-like grid view for DEM data.
"""

from typing import Optional, Tuple
import numpy as np
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal, QItemSelectionModel
from PyQt6.QtGui import QColor, QKeyEvent, QBrush, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QTableView,
    QAbstractItemView,
    QHeaderView,
    QStyledItemDelegate,
    QLineEdit,
)

from dem_editor.core.dem_model import DEMModel


from dem_editor.core.dem_clipboard import (
    format_block_for_clipboard,
    parse_clipboard_text,
    resolve_paste_shape,
    tile_source,
)


class FloatPrecisionDelegate(QStyledItemDelegate):
    """Custom delegate for formatted editing of floating-point cells."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignmentFlag.AlignRight)
        return editor

    def setEditorData(self, editor, index):
        val = index.model().get_raw_value(index.row(), index.column())
        if np.isnan(val):
            editor.setText("")
        else:
            editor.setText(f"{val:.6g}")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        text = editor.text().strip()
        model.setData(index, text, Qt.ItemDataRole.EditRole)


class DEMTableModel(QAbstractTableModel):
    """Virtualized QAbstractTableModel reading directly from NumPy DEM array."""

    def __init__(self, dem_model: DEMModel):
        super().__init__()
        self._dem = dem_model
        self._dem.dataChanged.connect(self.on_data_updated)
        self._dem.metadataChanged.connect(self.on_meta_updated)
        self.precision_format = "%.4g"
        self.is_dark_mode = True

    def on_data_updated(self):
        self.beginResetModel()
        self.endResetModel()

    def on_meta_updated(self):
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, self.rowCount() - 1)

    def rowCount(self, parent=QModelIndex()) -> int:
        return self._dem.shape[0]

    def columnCount(self, parent=QModelIndex()) -> int:
        return self._dem.shape[1]

    def get_raw_value(self, row: int, col: int) -> float:
        return self._dem.data[row, col]

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        val = self._dem.data[row, col]

        if role == Qt.ItemDataRole.DisplayRole:
            if np.isnan(val):
                return "NaN"
            return self.precision_format % val

        elif role == Qt.ItemDataRole.EditRole:
            if np.isnan(val):
                return ""
            return f"{val:.6g}"

        elif role == Qt.ItemDataRole.BackgroundRole:
            if np.isnan(val):
                # Distinct subtle reddish color for NaN cells
                return QColor(70, 20, 20) if self.is_dark_mode else QColor(255, 215, 215)
            return None

        elif role == Qt.ItemDataRole.ForegroundRole:
            if np.isnan(val):
                return QColor(255, 120, 120) if self.is_dark_mode else QColor(200, 30, 30)
            return None

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if np.isnan(val):
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.FontRole:
            if np.isnan(val):
                f = QFont()
                f.setItalic(True)
                return f
            return None

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        col = index.column()

        str_val = str(value).strip().lower()
        if str_val in ["", "nan", "null", "none"]:
            new_val = np.nan
        else:
            try:
                new_val = float(str_val)
            except ValueError:
                return False

        self._dem.set_cell_value(row, col, new_val)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            meta = self._dem.metadata
            if orientation == Qt.Orientation.Horizontal:
                if meta.dx != 1.0 or meta.x0 != 0.0:
                    x_coord = meta.x0 + section * meta.dx
                    return f"{section}\n({x_coord:.1f}m)"
                return str(section)
            else:
                if meta.dy != 1.0 or meta.y0 != 0.0:
                    y_coord = meta.y0 + section * meta.dy
                    return f"{section}\n({y_coord:.1f}m)"
                return str(section)
        return None


class DEMTableView(QTableView):
    """Excel-style table view with fast keyboard navigation and viewport tracking."""

    visibleViewportChanged = pyqtSignal(int, int, int, int)  # r_min, r_max, c_min, c_max
    activeCellChanged = pyqtSignal(int, int, float)  # r, c, val
    selectionStatsChanged = pyqtSignal(int, int, int, int)  # r_min, r_max, c_min, c_max

    def __init__(self, dem_model: DEMModel, parent=None):
        super().__init__(parent)
        self._dem = dem_model
        self.table_model = DEMTableModel(dem_model)
        self.setModel(self.table_model)

        self.setItemDelegate(FloatPrecisionDelegate(self))

        # View settings for fast rendering
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setAlternatingRowColors(True)

        self.horizontalHeader().setDefaultSectionSize(75)
        self.verticalHeader().setDefaultSectionSize(26)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Connect scrollbars to viewport tracking
        self.horizontalScrollBar().valueChanged.connect(self._emit_visible_viewport)
        self.verticalScrollBar().valueChanged.connect(self._emit_visible_viewport)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super().currentChanged(current, previous)
        if current.isValid():
            r, c = current.row(), current.column()
            val = self._dem.data[r, c]
            self.activeCellChanged.emit(r, c, val)

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        bbox = self.get_selected_bounding_box()
        if bbox:
            self.selectionStatsChanged.emit(*bbox)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._emit_visible_viewport()

    def _emit_visible_viewport(self):
        """Calculates visible row and column boundaries and notifies minimap."""
        if self._dem.data.size == 0:
            return

        viewport = self.viewport()
        top_left = self.indexAt(viewport.rect().topLeft())
        bottom_right = self.indexAt(viewport.rect().bottomRight())

        r_min = top_left.row() if top_left.isValid() else 0
        c_min = top_left.column() if top_left.isValid() else 0

        max_rows, max_cols = self._dem.shape
        r_max = bottom_right.row() if bottom_right.isValid() else max_rows - 1
        c_max = bottom_right.column() if bottom_right.isValid() else max_cols - 1

        if r_max < r_min:
            r_max = max_rows - 1
        if c_max < c_min:
            c_max = max_cols - 1

        self.visibleViewportChanged.emit(r_min, r_max, c_min, c_max)

    def get_selected_bounding_box(self) -> Optional[Tuple[int, int, int, int]]:
        """Returns (r_min, r_max, c_min, c_max) of current selection."""
        indexes = self.selectedIndexes()
        if not indexes:
            cur = self.currentIndex()
            if cur.isValid():
                return cur.row(), cur.row(), cur.column(), cur.column()
            return None

        rows = [idx.row() for idx in indexes]
        cols = [idx.column() for idx in indexes]
        return min(rows), max(rows), min(cols), max(cols)

    def copy_selection(self) -> bool:
        """Copia seleccion a portapapeles sistema (TSV). True si copio."""
        bbox = self.get_selected_bounding_box()
        if not bbox:
            return False
        r_min, r_max, c_min, c_max = bbox
        block = self._dem.get_block(r_min, r_max, c_min, c_max)
        QApplication.clipboard().setText(format_block_for_clipboard(block))
        self._dem.statusMessage.emit(
            f"Copiado {block.shape[0]}x{block.shape[1]} [{r_min}:{r_max}, {c_min}:{c_max}]."
        )
        return True

    def cut_selection(self) -> bool:
        """Corta: copia + pone NaN."""
        if not self.copy_selection():
            return False
        bbox = self.get_selected_bounding_box()
        if bbox:
            self._dem.delete_selection(*bbox)
        return True

    def paste_from_clipboard(self) -> bool:
        """Pega TSV en celda actual / seleccion estilo Excel."""
        text = QApplication.clipboard().text()
        vals, mask = parse_clipboard_text(text)
        if vals.size == 0 or not np.any(mask):
            self._dem.statusMessage.emit("Portapapeles vacío o sin números.")
            return False
        cur = self.currentIndex()
        sel = self.get_selected_bounding_box()
        if cur.isValid():
            anchor = (cur.row(), cur.column())
        elif sel:
            anchor = (sel[0], sel[2])
        else:
            return False
        sel_shape = None
        if sel:
            sel_shape = (sel[1] - sel[0] + 1, sel[3] - sel[2] + 1)
            if sel_shape != (1, 1):
                anchor = (sel[0], sel[2])
        r0, c0, nr, nc = resolve_paste_shape(vals.shape, anchor, sel_shape, self._dem.shape)
        if nr <= 0 or nc <= 0:
            self._dem.statusMessage.emit("Pegado fuera de malla: sin cambios.")
            return False
        tv, tm = tile_source(vals, mask, nr, nc)
        n, _ = self._dem.paste_block(r0, c0, tv, tm)
        if n > 0:
            from PyQt6.QtCore import QItemSelection
            qsel = QItemSelection(
                self.table_model.index(r0, c0),
                self.table_model.index(r0 + nr - 1, c0 + nc - 1),
            )
            self.selectionModel().select(qsel, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.setCurrentIndex(self.table_model.index(r0 + nr - 1, c0 + nc - 1))
            return True
        return False

    def keyPressEvent(self, event: QKeyEvent):
        # Ctrl+C / Ctrl+X / Ctrl+V estilo Excel (antes que edicion)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            k = event.key()
            if k in (Qt.Key.Key_C, Qt.Key.Key_Copy):
                self.copy_selection()
                event.accept()
                return
            if k in (Qt.Key.Key_X, Qt.Key.Key_Cut):
                self.cut_selection()
                event.accept()
                return
            if k in (Qt.Key.Key_V, Qt.Key.Key_Paste):
                self.paste_from_clipboard()
                event.accept()
                return
        key = event.key()

        # Delete or Backspace -> Set selected cells to NaN
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            bbox = self.get_selected_bounding_box()
            if bbox:
                self._dem.delete_selection(*bbox)
            event.accept()
            return

        # Fast direct numeric input: pressing digits, minus, period automatically opens editor
        text = event.text()
        if text and (text.isdigit() or text in ["-", "+", "."]):
            cur = self.currentIndex()
            if cur.isValid():
                self.edit(cur)
                # Pass key to the active editor
                editor = self.focusWidget()
                if isinstance(editor, QLineEdit):
                    editor.setText(text)
                    editor.setCursorPosition(len(text))
            event.accept()
            return

        super().keyPressEvent(event)
        self._emit_visible_viewport()

    def scroll_to_cell(self, row: int, col: int):
        """Centers viewport on specified row and column."""
        max_r, max_c = self._dem.shape
        if max_r == 0 or max_c == 0:
            return
        row = max(0, min(max_r - 1, row))
        col = max(0, min(max_c - 1, col))

        index = self.table_model.index(row, col)
        if index.isValid():
            self.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.setCurrentIndex(index)
            self._emit_visible_viewport()
