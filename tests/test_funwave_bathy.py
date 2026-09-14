"""Replica Fortran mod_bathy_correction."""
import numpy as np
from dem_editor.core.funwave_bathy import slope_fields, bathy_correction


def test_slope_def_is_fortran():
    # Gradx = |D(c+1)-D(c-1)|/DX (sin /2)
    D = np.array([[0., 0., 6., 0., 0.]])
    gx, _ = slope_fields(D, dx=2.0, dy=2.0)
    assert gx[0, 1] == 3.0  # |6-0|/2
    assert gx[0, 3] == 3.0


def test_flat_unchanged():
    D = np.full((10, 10), 5.0)
    o, i = bathy_correction(D, dx=1.0, dy=1.0)
    assert np.allclose(o, D) and i["n_exceed_before"] == 0 and i["converged"]


def test_single_jacobi_step():
    # Pico simetrico: centro grad 0 (nunca se toca, igual Fortran).
    # Anillo si excede: celda (2,1): |10-0|/0.5=20>cap ->
    # D1 = 0.4*0 + 0.15*(10+0+0+0) = 1.5
    D = np.zeros((5, 5))
    D[2, 2] = 10.0
    o, i = bathy_correction(D, dx=0.5, dy=0.5, slope_cap=1.0, max_iter=1)
    assert abs(o[2, 1] - 1.5) < 1e-12, o[2, 1]
    assert o[2, 2] == 10.0  # centro intacto (grad 0)
    assert o[0, 0] == 0.0


def test_step_reduced_bounded():
    # Escalon asimetrico 10->30: interfaz grad 20 > cap -> suaviza
    D = np.full((20, 20), 10.0)
    D[:, 10:] = 30.0
    o, i = bathy_correction(D, dx=1.0, dy=1.0, slope_cap=1.0)
    assert i["n_exceed_before"] > 0
    assert i["max_slope_after"] < i["max_slope_before"], i
    assert i["max_abs_change"] > 0
    assert o.min() >= 10.0 - 1e-9 and o.max() <= 30.0 + 1e-9


def test_nan_preserved():
    D = np.full((10, 10), 5.0)
    D[5, 5] = 50.0
    D[2, 2] = np.nan
    o, _ = bathy_correction(D, dx=1.0, dy=1.0)
    assert np.isnan(o[2, 2])


def test_smooth_below_excludes_land():
    # Escalon en agua se corrige; tierra (Depth<S) intacta
    D = np.full((12, 24), 10.0)
    D[:, 12:] = 30.0    # escalon mitad derecha (agua)
    D[9:11, 2:4] = -9.0  # bloque tierra con borde abrupto
    o, i = bathy_correction(D, dx=1.0, dy=1.0, smooth_below_depth=0.0, max_iter=200)
    assert o[5, 11] > 10.0 or o[5, 12] < 30.0  # interfaz agua suavizada
    assert np.all(o[9:11, 2:4] == -9.0)  # tierra intacta
