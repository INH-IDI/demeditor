"""Copy/paste bloques: parse, formato, modelo."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from dem_editor.core.dem_clipboard import (
    format_block_for_clipboard, parse_clipboard_text,
    resolve_paste_shape, tile_source,
)


def test_roundtrip_1x10():
    a = np.arange(10, dtype=float).reshape(1, 10)
    t = format_block_for_clipboard(a)
    v, m = parse_clipboard_text(t)
    assert v.shape == (1, 10) and m.all()
    assert np.allclose(v, a)


def test_nan_roundtrip():
    a = np.array([[1.5, np.nan, -3.0]])
    v, m = parse_clipboard_text(format_block_for_clipboard(a))
    assert m.all() and np.isnan(v[0, 1]) and v[0, 0] == 1.5


def test_comma_decimal():
    v, m = parse_clipboard_text("3,14\t2,5")
    assert m.all() and abs(v[0, 0] - 3.14) < 1e-9


def test_invalid_token_skipped():
    v, m = parse_clipboard_text("1.0\tabc")
    assert m[0, 0] and not m[0, 1]


def test_single_cell_fill_selection():
    r0, c0, nr, nc = resolve_paste_shape((1, 1), (5, 5), (3, 4), (10, 10))
    assert (nr, nc) == (3, 4)
    tv, tm = tile_source(np.array([[7.0]]), np.array([[True]]), nr, nc)
    assert np.all(tv == 7.0)


def test_paste_clipped_at_border():
    r0, c0, nr, nc = resolve_paste_shape((1, 10), (0, 5), None, (10, 10))
    assert (nr, nc) == (1, 5)


def test_model_paste_block_single_undo():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from dem_editor.core.dem_model import DEMModel
    m = DEMModel()
    m._data = np.zeros((5, 5))
    v, mask = parse_clipboard_text("1\t2\t3")
    from dem_editor.core.dem_clipboard import tile_source as ts
    tv, tm = ts(v, mask, 1, 3)
    n, _ = m.paste_block(0, 0, tv, tm)
    assert n == 1
    assert list(m._data[0, :3]) == [1, 2, 3]
    assert len(m._undo_stack) == 1  # un solo undo
    m.undo()
    assert list(m._data[0, :3]) == [0, 0, 0]
