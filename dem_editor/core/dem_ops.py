"""
dem_editor/core/dem_ops.py
Scientific numerical operations for DEMs:
- NaN interpolation (Bilinear, Nearest Neighbor, Bicubic, Harmonic/Laplace Inpainting)
- Region smoothing (Gaussian, Box filter, Median filter)
- Array mathematics (offset, scale, sign inversion, clipping)
"""

import numpy as np
from scipy import ndimage
from scipy.interpolate import griddata


def fill_nans(data: np.ndarray, method: str = "linear", max_iter: int = 300) -> np.ndarray:
    """
    Fills all NaN values in a 2D array using scientific interpolation.
    
    Methods:
    - 'linear': Delaunay triangulation / bilinear interpolation. Outer NaNs filled by nearest.
    - 'nearest': Nearest-neighbor Euclidean distance fill (very fast).
    - 'cubic': Bicubic spline interpolation. Outer NaNs filled by nearest.
    - 'harmonic': Solves Laplace equation Laplace(Z) = 0 on NaN mask (smooth Dirichlet inpainting).
    """
    out = data.copy()
    nan_mask = np.isnan(out)
    if not np.any(nan_mask):
        return out  # Nothing to fill

    valid_mask = ~nan_mask
    if not np.any(valid_mask):
        # All are NaN, cannot interpolate
        return np.zeros_like(out)

    nrows, ncols = out.shape

    if method == "nearest":
        # Blazing fast exact Euclidean nearest-neighbor using distance_transform_edt
        indices = ndimage.distance_transform_edt(
            nan_mask, return_distances=False, return_indices=True
        )
        return out[tuple(indices)]

    elif method in ["linear", "cubic"]:
        # Get coordinates of valid points
        valid_r, valid_c = np.nonzero(valid_mask)
        valid_vals = out[valid_mask]

        # Target coordinates where NaNs exist
        nan_r, nan_c = np.nonzero(nan_mask)

        # Interpolate NaN positions
        points = np.column_stack((valid_r, valid_c))
        xi = np.column_stack((nan_r, nan_c))

        interp_vals = griddata(points, valid_vals, xi, method=method)

        # griddata with linear/cubic gives NaN for points outside the convex hull of valid points
        remaining_nans = np.isnan(interp_vals)
        if np.any(remaining_nans):
            fallback_vals = griddata(points, valid_vals, xi[remaining_nans], method="nearest")
            interp_vals[remaining_nans] = fallback_vals

        out[nan_mask] = interp_vals
        return out

    elif method == "harmonic":
        # Iterative Laplace PDE solver (Dirichlet boundary condition)
        # Initialize NaN regions with nearest neighbor first for fast convergence
        indices = ndimage.distance_transform_edt(
            nan_mask, return_distances=False, return_indices=True
        )
        u = out[tuple(indices)].copy()

        # 4-neighbor Laplace stencil: u[i,j] = 0.25 * (u[i+1,j] + u[i-1,j] + u[i,j+1] + u[i,j-1])
        # Successive Over-Relaxation (SOR) with omega = 1.6
        omega = 1.6
        for _ in range(max_iter):
            # Compute Laplacian neighbor average
            # Padded view
            padded = np.pad(u, 1, mode="edge")
            laplace_avg = 0.25 * (
                padded[2:, 1:-1] + padded[:-2, 1:-1] + padded[1:-1, 2:] + padded[1:-1, :-2]
            )
            # Update only NaN cells
            diff = omega * (laplace_avg[nan_mask] - u[nan_mask])
            u[nan_mask] += diff
            if np.max(np.abs(diff)) < 1e-4:
                break
        return u

    else:
        raise ValueError(f"Unknown interpolation method: {method}")


def smooth_region(
    data: np.ndarray,
    r_slice: slice,
    c_slice: slice,
    method: str = "gaussian",
    sigma: float = 1.5,
    filter_size: int = 3,
    blend_border: bool = True,
) -> np.ndarray:
    """
    Smooths a selected rectangular region of the DEM.
    
    Methods:
    - 'gaussian': Gaussian filter with standard deviation sigma
    - 'box': Uniform mean box filter of size (filter_size, filter_size)
    - 'median': Median filter (despikes extreme noise/outliers)
    
    If blend_border is True, creates a smooth transition along the perimeter
    of the selection to avoid step artifacts at the edges.
    """
    out = data.copy()
    sub = out[r_slice, c_slice].copy()

    # Handle NaNs in subregion if any
    nan_mask = np.isnan(sub)
    if np.all(nan_mask):
        return out  # Nothing valid to smooth

    has_nans = np.any(nan_mask)
    if has_nans:
        # Temporarily fill NaNs for filtering
        sub_filled = fill_nans(sub, method="nearest")
    else:
        sub_filled = sub

    # Apply selected filter
    if method == "gaussian":
        smoothed = ndimage.gaussian_filter(sub_filled, sigma=sigma, mode="nearest")
    elif method == "box":
        smoothed = ndimage.uniform_filter(sub_filled, size=filter_size, mode="nearest")
    elif method == "median":
        smoothed = ndimage.median_filter(sub_filled, size=filter_size, mode="nearest")
    else:
        raise ValueError(f"Unknown smoothing method: {method}")

    # If subregion originally had NaNs, reapply NaNs
    if has_nans:
        smoothed[nan_mask] = np.nan

    if blend_border and sub.shape[0] > 4 and sub.shape[1] > 4:
        # Generate 2D smooth feathering mask from 0 at border to 1 in center
        h, w = sub.shape
        margin_y = min(3, h // 3)
        margin_x = min(3, w // 3)

        mask_y = np.ones(h, dtype=np.float64)
        for i in range(margin_y):
            w_val = 0.5 * (1 - np.cos(np.pi * (i + 1) / (margin_y + 1)))
            mask_y[i] = w_val
            mask_y[h - 1 - i] = w_val

        mask_x = np.ones(w, dtype=np.float64)
        for j in range(margin_x):
            w_val = 0.5 * (1 - np.cos(np.pi * (j + 1) / (margin_x + 1)))
            mask_x[j] = w_val
            mask_x[w - 1 - j] = w_val

        blend_weight = np.outer(mask_y, mask_x)
        # Apply blended result where valid
        valid_blend = ~np.isnan(sub)
        final_sub = sub.copy()
        final_sub[valid_blend] = (
            (1.0 - blend_weight[valid_blend]) * sub[valid_blend]
            + blend_weight[valid_blend] * smoothed[valid_blend]
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
    """
    Applies mathematical operation to region or entire DEM.
    - 'add': Z = Z + param
    - 'mult': Z = Z * param
    - 'invert': Z = -Z
    - 'set': Z = param
    """
    out = data.copy()
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

    out[r_slice, c_slice] = sub
    return out
