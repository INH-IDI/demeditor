import numpy as np

from dem_editor.core.dem_io import load_dem_file, save_dem_file

R2S = """######
:FileType r2s  ASCII  EnSim 1.0
:Application  BlueKenue
:NoDataValue -999
:AttributeName 1 Value
:AttributeType 1 double
:xOrigin 100.0
:yOrigin 200.0
:xCount 3
:yCount 2
:xDelta 5
:yDelta 10
:Angle 0.0
:EndHeader
1 2 3
-999 5 6
"""


def _write(tmp_path, text=R2S):
    p = tmp_path / "a.r2s"
    p.write_bytes(text.replace("\n", "\r\r\n").encode())
    return str(p)


def test_load_r2s(tmp_path):
    data, meta = load_dem_file(_write(tmp_path))
    assert meta.format_type == "r2s"
    assert data.shape == (2, 3)
    assert (meta.x0, meta.y0, meta.dx, meta.dy) == (100.0, 200.0, 5.0, 10.0)
    # row 0 = south, kept as-is for origin_bottom=True
    assert list(data[0]) == [1, 2, 3]
    assert np.isnan(data[1, 0]) and data[1, 1] == 5


def test_load_r2s_top_origin(tmp_path):
    data, _ = load_dem_file(_write(tmp_path), origin_bottom=False)
    assert list(data[1]) == [1, 2, 3]


def test_r2s_roundtrip(tmp_path):
    data, meta = load_dem_file(_write(tmp_path))
    out = str(tmp_path / "b.r2s")
    save_dem_file(out, data, meta)
    d2, m2 = load_dem_file(out)
    np.testing.assert_array_equal(np.isnan(d2), np.isnan(data))
    np.testing.assert_allclose(d2[~np.isnan(d2)], data[~np.isnan(data)])
    assert (m2.x0, m2.y0, m2.dx, m2.dy) == (100.0, 200.0, 5.0, 10.0)


def test_r2s_bad_count(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        load_dem_file(_write(tmp_path, R2S.replace("5 6", "5")))
