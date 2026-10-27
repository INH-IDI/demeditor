"""Pruebas para guardado y carga de GeoTIFF con proyección UTM y CRS."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import numpy as np
from osgeo import gdal, osr

from dem_editor.core.dem_io import (
    DEMMetadata,
    save_geotiff,
    load_geotiff,
    save_dem_file,
    load_dem_file,
    crs_to_wkt,
    utm_to_epsg,
    parse_crs_to_utm_info,
    get_crs_description,
)
from dem_editor.core.dem_model import DEMModel


def test_crs_helpers():
    assert utm_to_epsg(19, north=False) == 32719
    assert utm_to_epsg(18, north=True) == 32618

    # parse_crs_to_utm_info
    assert parse_crs_to_utm_info("32719") == (19, False)
    assert parse_crs_to_utm_info("EPSG:32618") == (18, True)
    assert parse_crs_to_utm_info("") is None
    assert parse_crs_to_utm_info("EPSG:4326") is None

    # crs_to_wkt
    wkt = crs_to_wkt("EPSG:32719")
    assert "32719" in wkt or "UTM zone 19S" in wkt

    # get_crs_description
    desc = get_crs_description("EPSG:32719")
    assert "19S" in desc and "32719" in desc
    assert get_crs_description("") == "Sin definir (Local)"


def test_geotiff_save_load_utm_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        tif_path = os.path.join(tmpdir, "test_utm19s.tif")
        data = np.array([
            [10.0, 11.5, 12.0],
            [13.0, 14.5, 15.0],
            [16.0, 17.5, 18.0],
            [19.0, 20.5, 21.0],
        ], dtype=np.float64)
        nrows, ncols = data.shape
        x0, y0, dx, dy = 255000.0, 6279500.0, 5.0, 5.0
        crs = "EPSG:32719"

        meta = DEMMetadata(
            filename=tif_path,
            format_type="geotiff",
            nrows=nrows,
            ncols=ncols,
            x0=x0,
            y0=y0,
            dx=dx,
            dy=dy,
            nodata=-999.0,
            origin_bottom=True,
            crs=crs,
        )

        save_geotiff(tif_path, data, meta)
        assert os.path.isfile(tif_path)

        # 1. Verificar directamente con GDAL como herramienta externa
        ds = gdal.Open(tif_path, gdal.GA_ReadOnly)
        assert ds is not None
        assert ds.RasterXSize == ncols
        assert ds.RasterYSize == nrows

        gt = ds.GetGeoTransform()
        assert abs(gt[0] - x0) < 1e-6
        assert abs(gt[1] - dx) < 1e-6
        assert abs(gt[5] - (-dy)) < 1e-6
        # Top-left Y = y0 + nrows * dy
        assert abs(gt[3] - (y0 + nrows * dy)) < 1e-6

        # Projection check
        proj = ds.GetProjectionRef()
        assert proj != ""
        srs = osr.SpatialReference()
        srs.ImportFromWkt(proj)
        assert srs.GetUTMZone() == -19  # 19 South
        ds = None

        # 2. Cargar con dem_io
        loaded_data, loaded_meta = load_geotiff(tif_path, origin_bottom=True)
        assert loaded_data.shape == data.shape
        assert np.allclose(loaded_data, data)
        assert abs(loaded_meta.x0 - x0) < 1e-6
        assert abs(loaded_meta.y0 - y0) < 1e-6
        assert abs(loaded_meta.dx - dx) < 1e-6
        assert abs(loaded_meta.dy - dy) < 1e-6
        assert parse_crs_to_utm_info(loaded_meta.crs) == (19, False)


def test_geotiff_nans_preserved():
    with tempfile.TemporaryDirectory() as tmpdir:
        tif_path = os.path.join(tmpdir, "test_nans.tif")
        data = np.array([
            [1.0, np.nan, 3.0],
            [np.nan, 5.0, np.nan],
        ], dtype=np.float64)

        meta = DEMMetadata(
            filename=tif_path,
            format_type="geotiff",
            nrows=2,
            ncols=3,
            x0=100.0,
            y0=200.0,
            dx=2.0,
            dy=2.0,
            nodata=-9999.0,
            origin_bottom=True,
            crs="EPSG:32718",
        )

        save_geotiff(tif_path, data, meta)
        loaded_data, loaded_meta = load_geotiff(tif_path, origin_bottom=True)

        assert np.isnan(loaded_data[0, 1])
        assert np.isnan(loaded_data[1, 0])
        assert np.isnan(loaded_data[1, 2])
        assert loaded_data[0, 0] == 1.0
        assert loaded_data[0, 2] == 3.0
        assert loaded_data[1, 1] == 5.0


def test_sidecar_prj_with_asc():
    with tempfile.TemporaryDirectory() as tmpdir:
        asc_path = os.path.join(tmpdir, "modelo.asc")
        prj_path = os.path.join(tmpdir, "modelo.prj")
        data = np.arange(12, dtype=np.float64).reshape((3, 4))

        meta = DEMMetadata(
            filename=asc_path,
            format_type="esri_asc",
            nrows=3,
            ncols=4,
            x0=500000.0,
            y0=6000000.0,
            dx=10.0,
            dy=10.0,
            nodata=-9999.0,
            origin_bottom=True,
            crs="EPSG:32719",
        )

        save_dem_file(asc_path, data, meta)
        assert os.path.isfile(asc_path)
        assert os.path.isfile(prj_path)

        # Cargar con universal loader y verificar que meta.crs se rescata del .prj
        loaded_data, loaded_meta = load_dem_file(asc_path, origin_bottom=True)
        assert parse_crs_to_utm_info(loaded_meta.crs) == (19, False)


def test_dialogs_utm_and_properties():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from dem_editor.ui.dialogs import AssignUTMDialog, GridPropertiesDialog

    # AssignUTMDialog
    dlg = AssignUTMDialog(default_zone=19, is_north=False)
    assert dlg.get_crs() == "EPSG:32719"

    dlg.spin_zone.setValue(18)
    dlg.combo_hemi.setCurrentIndex(1)  # North
    assert dlg.get_crs() == "EPSG:32618"

    dlg.chk_no_crs.setChecked(True)
    assert dlg.get_crs() == ""

    # GridPropertiesDialog
    model = DEMModel()
    model.metadata.crs = ""
    model.metadata.x0 = 255000.0
    model.metadata.y0 = 6279500.0
    prop_dlg = GridPropertiesDialog(model)
    prop_dlg.combo_crs_mode.setCurrentIndex(0)  # UTM
    prop_dlg.spin_utm_zone.setValue(19)
    prop_dlg.combo_utm_hemi.setCurrentIndex(0)  # South
    prop_dlg.apply_changes()

    assert model.metadata.crs == "EPSG:32719"
