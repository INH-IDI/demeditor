"""
dem_editor/core/dem_ops.py
Scientific numerical operations for DEMs:
- NaN interpolation (linear, nearest, cubic, harmonic/Laplace, fast/safe)
- Region smoothing (gaussian, box, median) with NaN-aware normalized filtering
- Array mathematics (offset, scale, sign inversion, clipping)

Fix history (2026-09):
- harmonic SOR omega=1.6 + Jacobi = divergence (±1e91 en huecos grandes).
  Corregido a Jacobi omega=1.0 estable + guarda divergencia + clamp max-principle.
- cubic/linear clamped a rango valido (Clough-Tocher overshoot [-31,19] en salto [-20,5]).
- all-NaN retorna NaN (antes zeros falsos). inf tratado como NaN.
- griddata Delaunay solo en arrays pequenos; en extensos usa via rapida local.
"""

from typing import Callable, Dict, Optional, Tuple

import numpy as np
from scipy import ndimage
from scipy.interpolate import griddata

try:
    from numba import njit  # noqa: F401  (aceleracion opcional futura)
    _HAS_NUMBA = True
except Exception:
    _HAS_NUMBA = False

# Umbral: griddata Delaunay solo bajo este tamano / puntos validos.
_GRIDDATA_MAX_CELLS = 500 * 500
_GRIDDATA_MAX_POINTS = 30_000

__all__ = [
    "fill_nans",
    "fill_nans_with_info",
    "fill_nans_fast",
    "fill_nans_safe",
    "smooth_region",
    "apply_arithmetic",
]


def _sanitize(data: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """Copia float64. Mascara invalida = NaN | inf. Retorna (out, bad_mask, vmin, vmax)."""
    out = np.asarray(data, dtype=np.float64).copy()
    bad_mask = ~np.isfinite(out)  # NaN + inf
    if np.any(~bad_mask):
        v = out[~bad_mask]
        vmin, vmax = float(v.min()), float(v.max())
    else:
        vmin, vmax = np.nan, np.nan
    # Normaliza inf -> NaN para resto pipeline
    out[bad_mask & np.isinf(out)] = np.nan
    bad_mask = np.isnan(out)
    return out, bad_mask, vmin, vmax


def _nearest_fill(out: np.ndarray, bad_mask: np.ndarray) -> np.ndarray:
    """Relleno vecino mas cercano via EDT. Asume hay >=1 valido."""
    indices = ndimage.distance_transform_edt(
        bad_mask, return_distances=False, return_indices=True
    )
    filled = out[tuple(indices)]
    return filled


def _auto_max_iter(shape, bad_mask, requested=None, cap: int = 3000) -> int:
    """Iteraciones adaptativas segun tamano hueco. Hueco grande necesita miles."""
    if requested is not None:
        return int(requested)
    nrows, ncols = shape
    # Diametro aprox hueco = sqrt(area NaN); iteraciones difusion ~ d^2, cap.
    n_bad = int(bad_mask.sum())
    d = int(np.sqrt(n_bad)) if n_bad else 0
    est = max(300, min(cap, 2 * max(nrows, ncols), max(300, d * 2)))
    # Hueco pequeno converge rapido; hueco enorme pide cap.
    return int(est)


def _laplace_inpaint(
    u: np.ndarray,
    bad_mask: np.ndarray,
    max_iter: int,
    tol_rel: float = 1e-5,
    tol_abs: float = 1e-6,
    vmin: float = np.nan,
    vmax: float = np.nan,
    clip: bool = True,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Tuple[np.ndarray, Dict]:
    """Jacobi Laplace estable omega=1. Solo actualiza celdas bad_mask.

    Garantia: principio maximo -> resultado dentro [vmin,vmax] si clip=True.
    Retorna (u, info).
    """
    scale = 1.0
    if np.isfinite(vmin) and np.isfinite(vmax):
        scale = max(1.0, abs(vmax - vmin))
    tol = max(tol_abs, tol_rel * scale)
    n_iter = 0
    converged = False
    residual = np.nan
    # Margen divergencia: si excede rango valido x100 + escala, aborta.
    if np.isfinite(vmin) and np.isfinite(vmax):
        span = abs(vmax - vmin)
        bound = max(abs(vmin), abs(vmax), 1.0) + 100.0 * (span + 1.0)
    else:
        bound = np.inf

    for it in range(1, max_iter + 1):
        padded = np.pad(u, 1, mode="edge")
        avg = 0.25 * (
            padded[2:, 1:-1] + padded[:-2, 1:-1] + padded[1:-1, 2:] + padded[1:-1, :-2]
        )
        diff = avg[bad_mask] - u[bad_mask]
        u[bad_mask] += diff  # omega = 1.0 (Jacobi puro, estable)
        n_iter = it
        if progress is not None and (it % 100 == 0 or it == max_iter):
            progress(it, max_iter)
        # Chequeo cada 10 iters para ahorrar
        if it % 10 == 0 or it == max_iter:
            m = float(np.max(np.abs(diff))) if diff.size else 0.0
            residual = m
            if not np.all(np.isfinite(u[bad_mask])):
                # Divergencia numerica -> fallback conserva init
                break
            if bound != np.inf and float(np.max(np.abs(u[bad_mask]))) > bound:
                break
            if m < tol:
                converged = True
                break
    else:
        pass

    info = {"n_iter": n_iter, "converged": converged, "residual": float(residual) if np.isfinite(residual) else float("nan")}
    if clip and np.isfinite(vmin) and np.isfinite(vmax):
        lo, hi = (vmin, vmax) if vmin <= vmax else (vmax, vmin)
        before = u[bad_mask].copy()
        u[bad_mask] = np.clip(before, lo, hi)
        info["clipped"] = int(np.sum((before < lo) | (before > hi)))
    else:
        info["clipped"] = 0
    # Si no finito tras loop, recorta a nearest (seguridad)
    bad_finite = bad_mask & ~np.isfinite(u)
    if np.any(bad_finite):
        u[bad_finite] = np.nan  # llamador hara fallback nearest
        info["nonfinite"] = int(bad_finite.sum())
        info["converged"] = False
    else:
        info["nonfinite"] = 0
    return u, info


def fill_nans_with_info(
    data: np.ndarray,
    method: str = "linear",
    max_iter=None,
    clip: bool = True,
    tol_rel: float = 1e-5,
    tol_abs: float = 1e-6,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Tuple[np.ndarray, Dict]:
    """Version con diagnostico. Retorna (array, info).

    method: nearest | linear | cubic | harmonic | laplace | fast | safe
    - linear/cubic pequenos: griddata + fallback nearest + clamp.
    - linear/cubic extensos: via rapida (nearest init + Laplace), evita Qhull.
    - harmonic/laplace/fast/safe: Laplace Jacobi estable.
    - clip=True: recorta relleno a [vmin,vmax] validos (anti overshoot).
    """
    out, bad_mask, vmin, vmax = _sanitize(data)
    info: Dict = {"method_requested": method, "vmin": vmin, "vmax": vmax,
                  "n_bad": int(bad_mask.sum()), "clipped": 0}
    if not np.any(bad_mask):
        info.update({"method_used": "none", "n_iter": 0, "converged": True, "residual": 0.0})
        return out, info
    if not np.any(~bad_mask):
        # Todo invalido -> NaN, no zeros falsos
        out[:] = np.nan
        info.update({"method_used": "none-all-nan", "n_iter": 0, "converged": False,
                     "residual": float("nan")})
        return out, info

    m = method.lower().strip()

    if m == "nearest":
        out = _nearest_fill(out, bad_mask)
        info.update({"method_used": "nearest", "n_iter": 0, "converged": True, "residual": 0.0})
        return out, info

    if m in ("harmonic", "laplace", "fast", "safe"):
        iters = _auto_max_iter(out.shape, bad_mask, requested=max_iter)
        init = _nearest_fill(out, bad_mask)
        u = init.copy()
        u, lap = _laplace_inpaint(u, bad_mask, iters, tol_rel, tol_abs,
                                  vmin, vmax, clip, progress)
        if lap.get("nonfinite"):
            # Fallback total a nearest si Laplace fallo
            u = init
            lap["converged"] = False
        out = u
        info.update({"method_used": "laplace", "max_iter": iters, **lap})
        return out, info

    if m in ("linear", "cubic"):
        n_valid = int((~bad_mask).sum())
        ncells = out.size
        use_griddata = (ncells <= _GRIDDATA_MAX_CELLS and n_valid <= _GRIDDATA_MAX_POINTS)
        if use_griddata:
            try:
                valid_r, valid_c = np.nonzero(~bad_mask)
                valid_vals = out[~bad_mask]
                nan_r, nan_c = np.nonzero(bad_mask)
                points = np.column_stack((valid_r, valid_c))
                xi = np.column_stack((nan_r, nan_c))
                interp_vals = griddata(points, valid_vals, xi, method=m)
                rem = np.isnan(interp_vals)
                if np.any(rem):
                    fb = griddata(points, valid_vals, xi[rem], method="nearest")
                    interp_vals[rem] = fb
                if clip:
                    lo, hi = (vmin, vmax) if vmin <= vmax else (vmax, vmin)
                    n_clip = int(np.sum((interp_vals < lo) | (interp_vals > hi)))
                    interp_vals = np.clip(interp_vals, lo, hi)
                    info["clipped"] = n_clip
                # Seguridad: si aun NaN/inf, fallback nearest puntual
                still = ~np.isfinite(interp_vals)
                if np.any(still):
                    fb2 = griddata(points, valid_vals, xi[still], method="nearest")
                    interp_vals[still] = fb2
                    info["fallback_nearest"] = int(still.sum())
                out[bad_mask] = interp_vals
                # Ultima red: cualquier resto -> nearest global
                rest = ~np.isfinite(out)
                if np.any(rest):
                    out = _nearest_fill(np.where(rest, np.nan, out), rest)
                info.update({"method_used": m, "n_iter": 0, "converged": True, "residual": 0.0})
                return out, info
            except Exception as e:
                info["griddata_error"] = str(e)
                # Cae a via rapida
                pass
        # Via rapida para extensos o fallo Qhull: nearest + Laplace suave
        info["fast_fallback"] = True
        iters = _auto_max_iter(out.shape, bad_mask, requested=max_iter, cap=1500)
        init = _nearest_fill(out, bad_mask)
        u = init.copy()
        u, lap = _laplace_inpaint(u, bad_mask, iters, tol_rel, tol_abs,
                                  vmin, vmax, clip, progress)
        if lap.get("nonfinite"):
            u = init
        out = u
        info.update({"method_used": m + "+laplace-fast", "max_iter": iters, **lap})
        return out, info

    raise ValueError(f"Unknown interpolation method: {method}")


def fill_nans(data: np.ndarray, method: str = "linear", max_iter=None,
              clip: bool = True, **kwargs) -> np.ndarray:
    """API compatible. Rellena NaN/inf. Retorna array.

    Cambios: max_iter=None = auto adaptativo (antes 300 fijo insuficiente).
    clip=True recorta a rango valido (anti overshoot cubic / anti blow-up).
    all-NaN -> NaN (antes zeros).
    """
    out, _ = fill_nans_with_info(data, method=method, max_iter=max_iter,
                                 clip=clip, **kwargs)
    return out


def fill_nans_fast(data: np.ndarray, max_iter=None, clip: bool = True, **kwargs) -> np.ndarray:
    """Atajo rapido y acotado para modelos extensos: nearest + Laplace."""
    out, _ = fill_nans_with_info(data, method="fast", max_iter=max_iter,
                                 clip=clip, **kwargs)
    return out


def fill_nans_safe(data: np.ndarray, max_iter=None, clip: bool = True, **kwargs) -> np.ndarray:
    """Alias seguro (igual que fast). Garantiza salida dentro [vmin,vmax]."""
    return fill_nans_fast(data, max_iter=max_iter, clip=clip, **kwargs)


def _masked_smooth(sub: np.ndarray, nan_mask: np.ndarray, method: str,
                   sigma: float, filter_size: int) -> np.ndarray:
    """Suavizado normalizado por pesos: evita halo de fill-nearest."""
    if method == "median":
        # Mediana sin pesos: usa nearest temporal (acepta leve sesgo borde)
        filled = fill_nans(sub, method="nearest")
        return ndimage.median_filter(filled, size=filter_size, mode="nearest")
    filled = np.where(nan_mask, 0.0, sub)
    weight = (~nan_mask).astype(np.float64)
    if method == "gaussian":
        num = ndimage.gaussian_filter(filled, sigma=sigma, mode="nearest")
        den = ndimage.gaussian_filter(weight, sigma=sigma, mode="nearest")
    elif method == "box":
        num = ndimage.uniform_filter(filled, size=filter_size, mode="nearest")
        den = ndimage.uniform_filter(weight, size=filter_size, mode="nearest")
    else:
        raise ValueError(f"Unknown smoothing method: {method}")
    with np.errstate(invalid="ignore", divide="ignore"):
        smoothed = np.where(den > 1e-12, num / np.maximum(den, 1e-12), np.nan)
    # Celdas sin vecinos validos -> nearest fallback puntual
    empty = ~np.isfinite(smoothed) & ~nan_mask
    if np.any(empty):
        fb = fill_nans(sub, method="nearest")
        smoothed[empty] = fb[empty]
    return smoothed


def smooth_region(
    data: np.ndarray,
    r_slice: slice,
    c_slice: slice,
    method: str = "gaussian",
    sigma: float = 1.5,
    filter_size: int = 3,
    blend_border: bool = True,
) -> np.ndarray:
    """Suaviza rectangulo. NaN-aware: no filtra valores inventados."""
    out = np.asarray(data, dtype=np.float64).copy()
    sub = out[r_slice, c_slice].copy()

    nan_mask = ~np.isfinite(sub)
    if np.all(nan_mask):
        return out

    smoothed = _masked_smooth(sub, nan_mask, method, sigma, filter_size)
    smoothed[nan_mask] = np.nan  # restaura NaN original

    if blend_border and sub.shape[0] > 4 and sub.shape[1] > 4:
        h, w = sub.shape
        margin_y = min(3, h // 3)
        margin_x = min(3, w // 3)
        mask_y = np.ones(h, dtype=np.float64)
        for i in range(margin_y):
            wv = 0.5 * (1 - np.cos(np.pi * (i + 1) / (margin_y + 1)))
            mask_y[i] = wv
            mask_y[h - 1 - i] = wv
        mask_x = np.ones(w, dtype=np.float64)
        for j in range(margin_x):
            wv = 0.5 * (1 - np.cos(np.pi * (j + 1) / (margin_x + 1)))
            mask_x[j] = wv
            mask_x[w - 1 - j] = wv
        blend_weight = np.outer(mask_y, mask_x)
        valid = np.isfinite(sub) & np.isfinite(smoothed)
        final_sub = sub.copy()
        final_sub[valid] = (
            (1.0 - blend_weight[valid]) * sub[valid]
            + blend_weight[valid] * smoothed[valid]
        )
        out[r_slice, c_slice] = final_sub
    else:
        out[r_slice, c_slice] = smoothed

    return out


def apply_arithmetic(
    data: np.ndarray,
    r_slice: slice,
    c_slice: slice,
    op: str,
    param: float = 0.0,
) -> np.ndarray:
    """Operacion matematica en region o DEM total."""
    out = np.asarray(data, dtype=np.float64).copy()
    sub = out[r_slice, c_slice]

    if op == "add":
        sub += param
    elif op == "mult":
        sub *= param
    elif op == "invert":
        sub *= -1.0
    elif op == "set":
        sub[...] = param
    elif op == "set_nan":
        sub[...] = np.nan
    else:
        raise ValueError(f"Unknown op: {op}")

    out[r_slice, c_slice] = sub
    return out
