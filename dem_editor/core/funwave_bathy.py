"""
dem_editor/core/funwave_bathy.py
Replica fiel del algoritmo BATHY_CORRECTION de FUNWAVE-TVD
(src/mod_bathy_correction.F, Fengyan Shi 2017).

Corrige batimetria donde pendiente supera SlopeCap (default 1.0):
  Gradx = |D(c+1)-D(c-1)| / DX        (ojo: /DX, no /2DX, igual que Fortran)
  Grady = |D(r+1)-D(r-1)| / DY
  Si max(Gradx,Grady) > SlopeCap:
      D1 = 0.4*D0 + 0.15*(vecinos N+S+E+O)   (Jacobi, conserva masa: 0.4+4*0.15=1)
Itera hasta cambio relativo <= 0.05 o 1000 pasadas:
  cambio = max |D0-D1| / max(MinDepthFrc*10, D0)

Mascara: celdas con Depth < SmoothBelowDepth (+ sus 4 vecinos) se excluyen.
Default SmoothBelowDepth=-LARGE => corrige todo. MinDepthFrc default 0.1 (io.F).

Notas vs Fortran:
- Array editor YA es Depth (.dep: positivo agua, negativo tierra). Sin flip signo.
- NaN: Fortran no contempla. Aqui NaN nunca se actualiza; stencil con
  vecinos NaN renormaliza (0.4*D0 + 0.6*media(vecinos validos)).
- Bordes: Fortran usa ghost cells; aqui pad edge (Neumann).
"""

from typing import Callable, Dict, Optional, Tuple

import numpy as np
from scipy import ndimage

LARGE = 1.0e20
DEFAULT_SLOPE_CAP = 1.0
DEFAULT_SMOOTH_BELOW = -LARGE
DEFAULT_MIN_DEPTH_FRC = 0.1
DEFAULT_THRESHOLD = 0.05
DEFAULT_MAX_ITER = 1000

__all__ = [
    "LARGE",
    "slope_fields",
    "bathy_correction",
    "bathy_correction_info",
]


def slope_fields(depth: np.ndarray, dx: float = 1.0, dy: float = 1.0):
    """Gradientes definicion Fortran. NaN si stencil toca NaN/borde sin dato."""
    D = np.asarray(depth, dtype=np.float64)
    if dx <= 0 or dy <= 0:
        raise ValueError("dx/dy deben ser > 0")
    P = np.pad(D, 1, mode="edge")
    C, L, R = P[1:-1, 1:-1], P[1:-1, :-2], P[1:-1, 2:]
    U, Dn = P[:-2, 1:-1], P[2:, 1:-1]
    with np.errstate(invalid="ignore"):
        gx = np.abs(R - L) / dx
        gy = np.abs(Dn - U) / dy
    bad = ~np.isfinite(C) | ~np.isfinite(L) | ~np.isfinite(R)
    gx = np.where(bad, np.nan, gx)
    bad = ~np.isfinite(C) | ~np.isfinite(U) | ~np.isfinite(Dn)
    gy = np.where(bad, np.nan, gy)
    return gx, gy


def _build_mask(D: np.ndarray, smooth_below: float) -> np.ndarray:
    """True = celda corregible. Excluye NaN y Depth<S (+ vecinos, igual Fortran)."""
    valid = np.isfinite(D)
    if smooth_below <= -LARGE / 2:
        return valid
    excl = valid & (D < smooth_below)
    if np.any(excl):
        excl = ndimage.binary_dilation(excl, structure=np.ones((3, 3)))
    return valid & ~excl


def bathy_correction(
    depth: np.ndarray,
    dx: float = 1.0,
    dy: float = 1.0,
    slope_cap: float = DEFAULT_SLOPE_CAP,
    smooth_below_depth: float = DEFAULT_SMOOTH_BELOW,
    min_depth_frc: float = DEFAULT_MIN_DEPTH_FRC,
    threshold: float = DEFAULT_THRESHOLD,
    max_iter: int = DEFAULT_MAX_ITER,
    progress: Optional[Callable[[int, float], bool]] = None,
) -> Tuple[np.ndarray, Dict]:
    """Aplica correccion FUNWAVE. Retorna (corregido, info).

    progress(it, cambio) -> True aborta (boton Cancelar preview).
    """
    if dx <= 0 or dy <= 0:
        raise ValueError("dx/dy deben ser > 0")
    D0 = np.asarray(depth, dtype=np.float64).copy()
    mask = _build_mask(D0, smooth_below_depth)
    info: Dict = {"n_target": int(mask.sum())}
    gx0, gy0 = slope_fields(D0, dx, dy)
    with np.errstate(invalid="ignore"):
        smax0 = np.maximum(gx0, gy0)
    exc0 = (smax0 > slope_cap) & mask
    info["n_exceed_before"] = int(np.nansum(exc0))
    info["max_slope_before"] = float(np.nanmax(smax0)) if np.any(np.isfinite(smax0)) else float("nan")
    if not np.any(mask) or info["n_exceed_before"] == 0:
        info.update({"n_iter": 0, "converged": True, "final_change": 0.0,
                     "n_exceed_after": info["n_exceed_before"],
                     "max_slope_after": info["max_slope_before"],
                     "max_abs_change": 0.0})
        return D0, info

    D1 = D0.copy()
    denom_base = min_depth_frc * 10.0
    change = 1.0
    n_iter = 0
    aborted = False
    # Bbox recorte: solo interior con mascara + halo 1
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    r0, r1 = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))
    c0, c1 = int(np.argmax(cols)), int(len(cols) - 1 - np.argmax(cols[::-1]))
    R0, R1 = max(0, r0 - 1), min(D0.shape[0] - 1, r1 + 1)
    C0, C1 = max(0, c0 - 1), min(D0.shape[1] - 1, c1 + 1)

    while change > threshold and n_iter < max_iter:
        sub = D0[R0:R1 + 1, C0:C1 + 1]
        m = mask[R0:R1 + 1, C0:C1 + 1]
        P = np.pad(sub, 1, mode="edge")
        Cc, L, R = P[1:-1, 1:-1], P[1:-1, :-2], P[1:-1, 2:]
        U, Dn = P[:-2, 1:-1], P[2:, 1:-1]
        with np.errstate(invalid="ignore"):
            gx = np.abs(R - L) / dx
            gy = np.abs(Dn - U) / dy
            smax = np.maximum(gx, gy)
        active = m & np.isfinite(smax) & (smax > slope_cap)
        # Media vecinos validos (renormalizada si hay NaN)
        nbr = np.stack([L, R, U, Dn])
        vok = np.isfinite(nbr)
        cnt = vok.sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean_nbr = np.where(cnt > 0, np.nansum(nbr, axis=0) / np.maximum(cnt, 1), np.nan)
        upd = active & np.isfinite(mean_nbr) & np.isfinite(Cc)
        new = D1[R0:R1 + 1, C0:C1 + 1].copy()
        new[upd] = 0.4 * Cc[upd] + 0.6 * mean_nbr[upd]
        # Metrica Fortran sobre celdas actualizadas
        if np.any(upd):
            denom = np.maximum(denom_base, Cc[upd])
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = np.abs(Cc[upd] - new[upd]) / denom
                rel = rel[np.isfinite(rel)]
            change = float(rel.max()) if rel.size else 0.0
        else:
            change = 0.0
        D1[R0:R1 + 1, C0:C1 + 1] = new
        D0[R0:R1 + 1, C0:C1 + 1] = new
        n_iter += 1
        if progress is not None and (n_iter % 10 == 0 or change <= threshold):
            if progress(n_iter, change):
                aborted = True
                break

    out = D1
    out[~np.isfinite(np.asarray(depth, dtype=np.float64))] = np.nan  # NaN intactos
    gx1, gy1 = slope_fields(out, dx, dy)
    with np.errstate(invalid="ignore"):
        smax1 = np.maximum(gx1, gy1)
    exc1 = (smax1 > slope_cap) & mask
    change_map = np.abs(out - np.asarray(depth, dtype=np.float64))
    info.update({
        "n_iter": n_iter,
        "converged": bool(change <= threshold) and not aborted,
        "aborted": aborted,
        "final_change": float(change),
        "n_exceed_after": int(np.nansum(exc1)),
        "max_slope_after": float(np.nanmax(smax1)) if np.any(np.isfinite(smax1)) else float("nan"),
        "max_abs_change": float(np.nanmax(change_map)) if np.any(np.isfinite(change_map)) else 0.0,
        "gradx0": gx0, "grady0": gy0, "gradx": gx1, "grady": gy1,
        "depth_change": np.where(np.isfinite(change_map), change_map, np.nan),
    })
    return out, info


# Alias espanol
bathy_correction_info = bathy_correction
