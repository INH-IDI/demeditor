"""Regresion: rango preservado, convergencia Laplace, all-NaN/inf."""
import numpy as np
from dem_editor.core.dem_ops import fill_nans, fill_nans_with_info


def _cliff():
    d = np.zeros((50, 50))
    d[:, :25] = -20
    d[:, 25:] = 5
    d[20:30, 20:30] = np.nan
    return d


def test_cubic_clipped():
    o = fill_nans(_cliff(), method="cubic")
    assert np.all(np.isfinite(o))
    assert o.min() >= -20 - 1e-9 and o.max() <= 5 + 1e-9, (o.min(), o.max())


def test_linear_clipped():
    o = fill_nans(_cliff(), method="linear")
    assert o.min() >= -20 - 1e-9 and o.max() <= 5 + 1e-9


def test_harmonic_converges_bounded():
    d = _cliff()
    o, info = fill_nans_with_info(d, method="harmonic")
    assert np.all(np.isfinite(o)), "harmonic diverge"
    assert o.min() >= -20 - 1e-9 and o.max() <= 5 + 1e-9, (o.min(), o.max(), info)
    assert abs(o[20:30, 20:30]).max() < 1e6, info


def test_harmonic_smooth_gradient():
    x = np.linspace(-10, 10, 60)
    xx, yy = np.meshgrid(x, x)
    d = xx + yy
    d[25:35, 25:35] = np.nan
    o, info = fill_nans_with_info(d, method="harmonic")
    assert np.all(np.isfinite(o))
    # Error vs plano real < 5% span
    err = np.abs(o[25:35, 25:35] - (xx + yy)[25:35, 25:35]).max()
    assert err < 0.05 * 40, err


def test_all_nan_returns_nan():
    o = fill_nans(np.full((5, 5), np.nan), method="harmonic")
    assert np.all(np.isnan(o))


def test_inf_treated_as_nan():
    d = np.ones((10, 10))
    d[4, 4] = np.inf
    o = fill_nans(d, method="nearest")
    assert np.all(np.isfinite(o)) and o[4, 4] == 1.0


def test_fast_large():
    rng = np.random.default_rng(0)
    big = rng.normal(-5, 1, size=(600, 600))
    big[250:350, 250:350] = np.nan
    o, info = fill_nans_with_info(big, method="linear")  # debe usar fast_fallback
    assert np.all(np.isfinite(o))
    assert info.get("method_used", "").endswith("fast") or info["method_used"] == "laplace"
