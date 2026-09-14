"""
dem_editor/core/dem_model.py
Central data model for DEM Editor with full Undo/Redo history stack.
"""

from typing import Optional, Tuple, List, Dict, Any
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from dem_editor.core.dem_io import DEMMetadata, load_dem_file, save_dem_file
from dem_editor.core.dem_ops import fill_nans, fill_nans_with_info, smooth_region, apply_arithmetic


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

    def get_block(self, r_min: int, r_max: int, c_min: int, c_max: int) -> np.ndarray:
        """Retorna copia bloque [r_min:r_max, c_min:c_max] recortado a bordes."""
        r0, r1 = max(0, r_min), min(self._data.shape[0] - 1, r_max)
        c0, c1 = max(0, c_min), min(self._data.shape[1] - 1, c_max)
        return self._data[r0:r1 + 1, c0:c1 + 1].copy()

    def paste_block(self, r0: int, c0: int, vals: np.ndarray, mask: np.ndarray = None,
                    description: str = None) -> Tuple[int, int]:
        """Pega bloque en (r0,c0). Un solo undo. mask=False salta celda.
        Retorna (filas_pegadas, cols_pegadas). Recorta a borde."""
        vals = np.asarray(vals, dtype=np.float64)
        if vals.size == 0:
            return 0, 0
        nr = min(vals.shape[0], self._data.shape[0] - r0)
        nc = min(vals.shape[1], self._data.shape[1] - c0)
        if nr <= 0 or nc <= 0 or r0 < 0 or c0 < 0:
            self.statusMessage.emit("Pegado fuera de malla: sin cambios.")
            return 0, 0
        v = vals[:nr, :nc]
        m = np.ones_like(v, dtype=bool) if mask is None else np.asarray(mask[:nr, :nc], dtype=bool)
        if not np.any(m):
            self.statusMessage.emit("Portapapeles sin valores válidos.")
            return 0, 0
        # Evita undo si nada cambia
        cur = self._data[r0:r0 + nr, c0:c0 + nc]
        same = True
        for idx in np.argwhere(m):
            i, j = int(idx[0]), int(idx[1])
            a, b = cur[i, j], v[i, j]
            if (np.isnan(a) and np.isnan(b)) or a == b:
                continue
            same = False
            break
        if same:
            return 0, 0
        self._push_undo(description or f"Pegar bloque {nr}x{nc} en ({r0},{c0})")
        tgt = self._data[r0:r0 + nr, c0:c0 + nc]
        tgt[m] = v[m]
        self._data[r0:r0 + nr, c0:c0 + nc] = tgt
        self.dataChanged.emit()
        clipped_r = vals.shape[0] - nr
        clipped_c = vals.shape[1] - nc
        extra = f" (recortado -{clipped_r}f -{clipped_c}c)" if (clipped_r > 0 or clipped_c > 0) else ""
        self.statusMessage.emit(f"Pegado {nr}x{nc} en ({r0},{c0}){extra}.")
        return nr, nc

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
        """Fills all NaNs in entire DEM usando pipeline seguro (clip + Laplace estable)."""
        if not np.any(~np.isfinite(self._data)):
            self.statusMessage.emit("No hay celdas NaN en el DEM para interpolar.")
            return

        method_names = {
            "linear": "Bilineal",
            "nearest": "Vecino más cercano",
            "cubic": "Bicúbica",
            "harmonic": "Armónica (Laplace)",
            "fast": "Rápida (extenso)",
            "safe": "Segura",
        }
        name = method_names.get(method, method)
        n_bad = int(np.sum(~np.isfinite(self._data)))
        vmin = float(np.nanmin(self._data))
        vmax = float(np.nanmax(self._data))
        self._push_undo(f"Interpolar NaNs ({name})")
        self._data, info = fill_nans_with_info(self._data, method=method, clip=True)
        self.dataChanged.emit()
        omin = float(np.nanmin(self._data))
        omax = float(np.nanmax(self._data))
        warn = ""
        if omin < vmin - 1e-9 or omax > vmax + 1e-9:
            warn = " [AVISO fuera rango]"
        self.statusMessage.emit(
            f"Interpolación {name}: {n_bad} celdas, vía {info.get('method_used')}, "
            f"iter={info.get('n_iter', 0)} conv={info.get('converged')} "
            f"rango [{omin:.3g},{omax:.3g}]{warn}"
        )

    def apply_funwave_correction(
        self,
        r_min: int, r_max: int, c_min: int, c_max: int,
        slope_cap: float = 1.0,
        smooth_below_depth: float = -1.0e20,
        min_depth_frc: float = 0.1,
        dx: Optional[float] = None,
        dy: Optional[float] = None,
        max_iter: int = 1000,
        precomputed: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Correccion batimetria FUNWAVE-TVD (mod_bathy_correction.F) en ambito.
        Un solo undo. precomputed = bloque ya calculado (preview) evita recomputo."""
        from dem_editor.core.funwave_bathy import bathy_correction
        r0, r1 = max(0, r_min), min(self._data.shape[0] - 1, r_max)
        c0, c1 = max(0, c_min), min(self._data.shape[1] - 1, c_max)
        ddx = self._meta.dx if dx is None else dx
        ddy = self._meta.dy if dy is None else dy
        if precomputed is not None:
            new_block = np.asarray(precomputed, dtype=np.float64)
            info = {"from_preview": True}
        else:
            block = self._data[r0:r1 + 1, c0:c1 + 1].copy()
            new_block, info = bathy_correction(
                block, dx=ddx, dy=ddy, slope_cap=slope_cap,
                smooth_below_depth=smooth_below_depth,
                min_depth_frc=min_depth_frc, max_iter=max_iter)
        cur = self._data[r0:r1 + 1, c0:c1 + 1]
        diff = np.abs(new_block - cur)
        if not np.any(np.isfinite(diff) & (diff > 0)):
            self.statusMessage.emit("FUNWAVE: sin pendientes sobre cap, sin cambios.")
            return info
        self._push_undo(f"Corrección FUNWAVE SlopeCap={slope_cap:g} [{r0}:{r1}, {c0}:{c1}]")
        w = np.isfinite(new_block)
        self._data[r0:r1 + 1, c0:c1 + 1][w] = new_block[w]
        self.dataChanged.emit()
        self.statusMessage.emit(
            f"FUNWAVE: {info.get('n_exceed_before', '?')}→{info.get('n_exceed_after', '?')} "
            f"celdas sobre cap, iter={info.get('n_iter', '?')} "
            f"conv={info.get('converged', '?')} Δmáx={info.get('max_abs_change', 0):.3g}."
        )
        return info

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
