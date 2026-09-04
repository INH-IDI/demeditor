"""
dem_editor/core/dem_model.py
Central data model for DEM Editor with full Undo/Redo history stack.
"""

from typing import Optional, Tuple, List, Dict, Any
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from dem_editor.core.dem_io import DEMMetadata, load_dem_file, save_dem_file
from dem_editor.core.dem_ops import fill_nans, smooth_region, apply_arithmetic


class HistoryItem:
    def __init__(self, data: np.ndarray, description: str):
        self.data = data.copy()
        self.description = description


class DEMModel(QObject):
    """
    Holds the DEM array, spatial metadata, and manages undo/redo stack.
    Emits PyQt signals when data updates so UI components refresh smoothly.
    """

    dataChanged = pyqtSignal()
    metadataChanged = pyqtSignal()
    historyChanged = pyqtSignal(bool, bool)  # can_undo, can_redo
    statusMessage = pyqtSignal(str)

    def __init__(self, max_history: int = 30):
        super().__init__()
        self.max_history = max_history
        self._data: np.ndarray = np.zeros((10, 10), dtype=np.float64)
        self._meta: DEMMetadata = DEMMetadata()
        self._undo_stack: List[HistoryItem] = []
        self._redo_stack: List[HistoryItem] = []
        self._is_modified = False

    @property
    def data(self) -> np.ndarray:
        return self._data

    @property
    def metadata(self) -> DEMMetadata:
        return self._meta

    @property
    def shape(self) -> Tuple[int, int]:
        return self._data.shape

    @property
    def is_modified(self) -> bool:
        return self._is_modified

    def load_file(self, filepath: str, origin_bottom: Optional[bool] = None) -> bool:
        """Loads DEM file into model and resets history."""
        try:
            use_origin = self._meta.origin_bottom if origin_bottom is None else origin_bottom
            data, meta = load_dem_file(filepath, origin_bottom=use_origin)
            self._data = data
            self._meta = meta
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._is_modified = False
            self.historyChanged.emit(False, False)
            self.metadataChanged.emit()
            self.dataChanged.emit()
            self.statusMessage.emit(
                f"Cargado: {filepath} ({data.shape[0]} filas × {data.shape[1]} cols)"
            )
            return True
        except Exception as e:
            self.statusMessage.emit(f"Error al cargar archivo: {str(e)}")
            raise

    def save_file(self, filepath: Optional[str] = None, fmt: Optional[str] = None) -> bool:
        """Saves DEM to current or new filepath."""
        target = filepath or self._meta.filename
        if not target:
            raise ValueError("No se ha especificado un nombre de archivo para guardar.")
        try:
            save_dem_file(target, self._data, self._meta, fmt=fmt)
            self._meta.filename = target
            self._is_modified = False
            self.statusMessage.emit(f"Guardado exitosamente: {target}")
            return True
        except Exception as e:
            self.statusMessage.emit(f"Error al guardar archivo: {str(e)}")
            raise

    def set_origin_bottom(self, origin_bottom: bool):
        """Toggles between FUNWAVE orientation (row 0 = bottom) and Standard (row 0 = top)."""
        if self._meta.origin_bottom != origin_bottom:
            self._meta.origin_bottom = origin_bottom
            self.metadataChanged.emit()
            self.dataChanged.emit()

    def _push_undo(self, description: str):
        """Saves current state to undo stack."""
        self._undo_stack.append(HistoryItem(self._data, description))
        if len(self._undo_stack) > self.max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._is_modified = True
        self.historyChanged.emit(True, False)

    def undo(self) -> Optional[str]:
        """Reverts last change."""
        if not self._undo_stack:
            return None
        item = self._undo_stack.pop()
        self._redo_stack.append(HistoryItem(self._data, item.description))
        self._data = item.data.copy()
        self.historyChanged.emit(len(self._undo_stack) > 0, True)
        self.dataChanged.emit()
        self.statusMessage.emit(f"Deshecho: {item.description}")
        return item.description

    def redo(self) -> Optional[str]:
        """Reapplies last undone change."""
        if not self._redo_stack:
            return None
        item = self._redo_stack.pop()
        self._undo_stack.append(HistoryItem(self._data, item.description))
        self._data = item.data.copy()
        self.historyChanged.emit(True, len(self._redo_stack) > 0)
        self.dataChanged.emit()
        self.statusMessage.emit(f"Rehecho: {item.description}")
        return item.description

    def set_cell_value(self, r: int, c: int, val: float):
        """Edits a single cell."""
        if 0 <= r < self._data.shape[0] and 0 <= c < self._data.shape[1]:
            old_val = self._data[r, c]
            if np.isnan(old_val) and np.isnan(val):
                return
            if old_val == val:
                return
            self._push_undo(f"Editar celda ({r}, {c})")
            self._data[r, c] = val
            self.dataChanged.emit()

    def delete_selection(self, r_min: int, r_max: int, c_min: int, c_max: int):
        """Sets selected block to NaN."""
        r_slice = slice(max(0, r_min), min(self._data.shape[0], r_max + 1))
        c_slice = slice(max(0, c_min), min(self._data.shape[1], c_max + 1))

        sub = self._data[r_slice, c_slice]
        if np.all(np.isnan(sub)):
            return

        self._push_undo(f"Borrar celdas a NaN [{r_min}:{r_max}, {c_min}:{c_max}]")
        self._data[r_slice, c_slice] = np.nan
        self.dataChanged.emit()
        self.statusMessage.emit(f"Celdas borradas a NaN en [{r_min}:{r_max}, {c_min}:{c_max}]")

    def fill_all_nans(self, method: str = "linear"):
        """Fills all NaNs in entire DEM using chosen interpolation method."""
        if not np.any(np.isnan(self._data)):
            self.statusMessage.emit("No hay celdas NaN en el DEM para interpolar.")
            return

        method_names = {
            "linear": "Bilineal",
            "nearest": "Vecino más cercano",
            "cubic": "Bicúbica",
            "harmonic": "Armónica (Laplace)",
        }
        name = method_names.get(method, method)
        self._push_undo(f"Interpolar NaNs ({name})")
        self._data = fill_nans(self._data, method=method)
        self.dataChanged.emit()
        self.statusMessage.emit(f"Interpolación completada con método: {name}")

    def smooth_selection(
        self,
        r_min: int,
        r_max: int,
        c_min: int,
        c_max: int,
        method: str = "gaussian",
        sigma: float = 1.5,
        filter_size: int = 3,
        blend: bool = True,
    ):
        """Smooths selected region."""
        r_slice = slice(max(0, r_min), min(self._data.shape[0], r_max + 1))
        c_slice = slice(max(0, c_min), min(self._data.shape[1], c_max + 1))

        self._push_undo(f"Suavizar [{r_min}:{r_max}, {c_min}:{c_max}]")
        self._data = smooth_region(
            self._data,
            r_slice,
            c_slice,
            method=method,
            sigma=sigma,
            filter_size=filter_size,
            blend_border=blend,
        )
        self.dataChanged.emit()
        self.statusMessage.emit(f"Región suavizada [{r_min}:{r_max}, {c_min}:{c_max}]")

    def apply_math(
        self,
        r_min: int,
        r_max: int,
        c_min: int,
        c_max: int,
        op: str,
        param: float = 0.0,
    ):
        """Applies arithmetic operation to selection."""
        r_slice = slice(max(0, r_min), min(self._data.shape[0], r_max + 1))
        c_slice = slice(max(0, c_min), min(self._data.shape[1], c_max + 1))

        op_names = {
            "add": f"Sumar {param}",
            "mult": f"Multiplicar × {param}",
            "invert": "Invertir signo",
            "set": f"Asignar {param}",
        }
        self._push_undo(f"Operación: {op_names.get(op, op)}")
        self._data = apply_arithmetic(self._data, r_slice, c_slice, op, param)
        self.dataChanged.emit()
        self.statusMessage.emit(f"Operación aplicada en [{r_min}:{r_max}, {c_min}:{c_max}]")

    def get_stats(
        self,
        r_min: Optional[int] = None,
        r_max: Optional[int] = None,
        c_min: Optional[int] = None,
        c_max: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Calculates min, max, mean, std, count, nans for full DEM or selection."""
        if r_min is None or r_max is None or c_min is None or c_max is None:
            sub = self._data
        else:
            r_slice = slice(max(0, r_min), min(self._data.shape[0], r_max + 1))
            c_slice = slice(max(0, c_min), min(self._data.shape[1], c_max + 1))
            sub = self._data[r_slice, c_slice]

        total = sub.size
        nan_count = int(np.isnan(sub).sum())
        valid_count = total - nan_count

        if valid_count > 0:
            z_min = float(np.nanmin(sub))
            z_max = float(np.nanmax(sub))
            z_mean = float(np.nanmean(sub))
            z_std = float(np.nanstd(sub))
        else:
            z_min = z_max = z_mean = z_std = np.nan

        return {
            "total": total,
            "valid": valid_count,
            "nans": nan_count,
            "min": z_min,
            "max": z_max,
            "mean": z_mean,
            "std": z_std,
        }
