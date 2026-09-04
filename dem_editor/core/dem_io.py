"""
dem_editor/core/dem_io.py
Scientific I/O module for Digital Elevation Models (DEM) and bathymetric grids.
Supports:
- Raw ASCII / FUNWAVE depth files (.dep, .txt, .dat)
- ESRI ASCII Raster (.asc)
- GeoTIFF (.tif, .tiff)
- NetCDF (.nc)
"""

import os
import numpy as np


class DEMMetadata:
    """Stores spatial and format metadata for a DEM."""

    def __init__(
        self,
        filename="",
        format_type="funwave",
        nrows=0,
        ncols=0,
        x0=0.0,
        y0=0.0,
        dx=1.0,
        dy=1.0,
        nodata=-9999.0,
        origin_bottom=True,
        extra_info=None,
    ):
        self.filename = filename
        self.format_type = format_type  # 'funwave', 'esri_asc', 'geotiff', 'netcdf'
        self.nrows = nrows
        self.ncols = ncols
        self.x0 = x0
        self.y0 = y0
        self.dx = dx
        self.dy = dy
        self.nodata = nodata
        self.origin_bottom = origin_bottom  # True: Row 0 is bottom (FUNWAVE); False: Row 0 is top (ESRI/Image)
        self.extra_info = extra_info or {}

    def copy(self):
        return DEMMetadata(
            filename=self.filename,
            format_type=self.format_type,
            nrows=self.nrows,
            ncols=self.ncols,
            x0=self.x0,
            y0=self.y0,
            dx=self.dx,
            dy=self.dy,
            nodata=self.nodata,
            origin_bottom=self.origin_bottom,
            extra_info=dict(self.extra_info),
        )


def is_esri_asc(filepath):
    """Check if file starts with ESRI ASCII header keywords."""
    try:
        with open(filepath, "r", errors="ignore") as f:
            for _ in range(6):
                line = f.readline()
                if not line:
                    break
                line_lower = line.strip().lower()
                if any(
                    line_lower.startswith(k)
                    for k in ["ncols", "nrows", "xllcorner", "yllcorner", "cellsize", "nodata_value"]
                ):
                    return True
    except Exception:
        pass
    return False


def load_ascii_funwave(filepath, origin_bottom=True):
    """Load plain ASCII / FUNWAVE depth grid (.dep, .txt)."""
    data = np.loadtxt(filepath, dtype=np.float64)
    if data.ndim == 1:
        data = data.reshape(1, -1)

    nrows, ncols = data.shape
    meta = DEMMetadata(
        filename=filepath,
        format_type="funwave",
        nrows=nrows,
        ncols=ncols,
        x0=0.0,
        y0=0.0,
        dx=1.0,
        dy=1.0,
        nodata=-9999.0,
        origin_bottom=origin_bottom,
    )
    return data, meta


def save_ascii_funwave(filepath, data, fmt="%.6g"):
    """Save plain ASCII / FUNWAVE depth grid."""
    np.savetxt(filepath, data, fmt=fmt, delimiter=" ")


def load_esri_asc(filepath, origin_bottom=True):
    """Load ESRI ASCII raster (.asc).
    ESRI ASC stores row 0 as the northernmost row (top).
    If origin_bottom=True, we vertically flip the array so row 0 is the southernmost (bottom/FUNWAVE).
    """
    header = {}
    header_lines_count = 0
    with open(filepath, "r") as f:
        while True:
            pos = f.tell()
            line = f.readline()
            if not line:
                break
            tokens = line.strip().split()
            if len(tokens) >= 2 and tokens[0].lower() in [
                "ncols",
                "nrows",
                "xllcorner",
                "yllcorner",
                "xllcenter",
                "yllcenter",
                "cellsize",
                "dx",
                "dy",
                "nodata_value",
            ]:
                header[tokens[0].lower()] = float(tokens[1])
                header_lines_count += 1
            else:
                f.seek(pos)
                break

    ncols = int(header.get("ncols", 0))
    nrows = int(header.get("nrows", 0))
    cellsize = float(header.get("cellsize", 1.0))
    dx = float(header.get("dx", cellsize))
    dy = float(header.get("dy", cellsize))
    x0 = float(header.get("xllcorner", header.get("xllcenter", 0.0)))
    y0 = float(header.get("yllcorner", header.get("yllcenter", 0.0)))
    nodata = float(header.get("nodata_value", -9999.0))

    data = np.loadtxt(filepath, skiprows=header_lines_count, dtype=np.float64)
    if data.shape != (nrows, ncols):
        data = data.reshape((nrows, ncols))

    if nodata is not None:
        mask = np.isclose(data, nodata, equal_nan=False)
        data[mask] = np.nan

    if origin_bottom:
        data = np.flipud(data).copy()

    meta = DEMMetadata(
        filename=filepath,
        format_type="esri_asc",
        nrows=nrows,
        ncols=ncols,
        x0=x0,
        y0=y0,
        dx=dx,
        dy=dy,
        nodata=nodata,
        origin_bottom=origin_bottom,
        extra_info=header,
    )
    return data, meta


def save_esri_asc(filepath, data, meta: DEMMetadata, fmt="%.6g"):
    """Save ESRI ASCII raster (.asc)."""
    nrows, ncols = data.shape
    nodata = meta.nodata if meta.nodata is not None else -9999.0
    x0 = meta.x0
    y0 = meta.y0
    cellsize = meta.dx

    out_data = data.copy()
    if meta.origin_bottom:
        out_data = np.flipud(out_data)

    nan_mask = np.isnan(out_data)
    out_data[nan_mask] = nodata

    header = (
        f"ncols         {ncols}\n"
        f"nrows         {nrows}\n"
        f"xllcorner     {x0:.6f}\n"
        f"yllcorner     {y0:.6f}\n"
        f"cellsize      {cellsize:.6f}\n"
        f"NODATA_value  {nodata:.6f}\n"
    )

    with open(filepath, "w") as f:
        f.write(header)
        np.savetxt(f, out_data, fmt=fmt, delimiter=" ")


def load_geotiff(filepath, origin_bottom=True):
    """Load GeoTIFF file using GDAL without requiring _gdal_array."""
    try:
        from osgeo import gdal
        ds = gdal.Open(filepath, gdal.GA_ReadOnly)
        if ds is not None:
            ncols = ds.RasterXSize
            nrows = ds.RasterYSize
            band = ds.GetRasterBand(1)
            nodata = band.GetNoDataValue()
            if nodata is None:
                nodata = -9999.0

            buf = band.ReadRaster(0, 0, ncols, nrows)
            # detect dtype or default to float32
            data = np.frombuffer(buf, dtype=np.float32).reshape((nrows, ncols)).astype(np.float64)

            gt = ds.GetGeoTransform()
            x0 = gt[0]
            dx = gt[1]
            dy = abs(gt[5]) if abs(gt[5]) > 0 else 1.0
            y0 = gt[3] - nrows * dy

            mask = np.isclose(data, nodata, equal_nan=False)
            data[mask] = np.nan

            if origin_bottom:
                data = np.flipud(data).copy()

            meta = DEMMetadata(
                filename=filepath,
                format_type="geotiff",
                nrows=nrows,
                ncols=ncols,
                x0=x0,
                y0=y0,
                dx=dx,
                dy=dy,
                nodata=nodata,
                origin_bottom=origin_bottom,
            )
            ds = None
            return data, meta
    except Exception:
        pass

    # Fallback to tifffile
    import tifffile
    data = tifffile.imread(filepath).astype(np.float64)
    if data.ndim == 3:
        data = data[0]
    nrows, ncols = data.shape
    if origin_bottom:
        data = np.flipud(data).copy()
    meta = DEMMetadata(
        filename=filepath,
        format_type="geotiff",
        nrows=nrows,
        ncols=ncols,
        x0=0.0,
        y0=0.0,
        dx=1.0,
        dy=1.0,
        nodata=-9999.0,
        origin_bottom=origin_bottom,
    )
    return data, meta


def save_geotiff(filepath, data, meta: DEMMetadata):
    """Save GeoTIFF file using GDAL WriteRaster."""
    nrows, ncols = data.shape
    nodata = meta.nodata if meta.nodata is not None else -9999.0

    out_data = data.copy()
    if meta.origin_bottom:
        out_data = np.flipud(out_data)

    nan_mask = np.isnan(out_data)
    out_data[nan_mask] = nodata
    out_arr = out_data.astype(np.float32)

    try:
        from osgeo import gdal
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(filepath, ncols, nrows, 1, gdal.GDT_Float32)
        y_top_left = meta.y0 + nrows * meta.dy
        ds.SetGeoTransform([meta.x0, meta.dx, 0.0, y_top_left, 0.0, -meta.dy])

        band = ds.GetRasterBand(1)
        band.SetNoDataValue(nodata)
        band.WriteRaster(0, 0, ncols, nrows, out_arr.tobytes())
        band.FlushCache()
        ds = None
    except Exception:
        import tifffile
        tifffile.imwrite(filepath, out_arr)


def load_netcdf(filepath, origin_bottom=True):
    """Load NetCDF file (.nc) using netCDF4."""
    import netCDF4

    ds = netCDF4.Dataset(filepath, "r")

    target_var = None
    priority_names = ["z", "elevation", "depth", "bathy", "topo", "dem", "h"]
    for name in priority_names:
        if name in ds.variables and len(ds.variables[name].shape) == 2:
            target_var = ds.variables[name]
            break

    if target_var is None:
        for name, var in ds.variables.items():
            if len(var.shape) == 2:
                target_var = var
                break

    if target_var is None:
        ds.close()
        raise ValueError("No 2D elevation/depth variable found in NetCDF file.")

    raw_data = target_var[:]
    if hasattr(raw_data, "filled"):
        data = raw_data.filled(np.nan).astype(np.float64)
    else:
        data = np.array(raw_data, dtype=np.float64)

    x_coords = None
    y_coords = None
    for name in ["x", "lon", "longitude", "X"]:
        if name in ds.variables and len(ds.variables[name].shape) == 1:
            x_coords = ds.variables[name][:]
            break
    for name in ["y", "lat", "latitude", "Y"]:
        if name in ds.variables and len(ds.variables[name].shape) == 1:
            y_coords = ds.variables[name][:]
            break

    nrows, ncols = data.shape
    x0 = float(x_coords[0]) if x_coords is not None and len(x_coords) > 0 else 0.0
    y0 = float(y_coords[0]) if y_coords is not None and len(y_coords) > 0 else 0.0
    dx = float(np.diff(x_coords).mean()) if x_coords is not None and len(x_coords) > 1 else 1.0
    dy = float(np.diff(y_coords).mean()) if y_coords is not None and len(y_coords) > 1 else 1.0

    nodata = getattr(target_var, "_FillValue", getattr(target_var, "missing_value", -9999.0))
    if nodata is not None:
        mask = np.isclose(data, nodata, equal_nan=False)
        data[mask] = np.nan

    ds.close()

    meta = DEMMetadata(
        filename=filepath,
        format_type="netcdf",
        nrows=nrows,
        ncols=ncols,
        x0=x0,
        y0=y0,
        dx=dx,
        dy=abs(dy),
        nodata=nodata,
        origin_bottom=origin_bottom,
    )
    return data, meta


def save_netcdf(filepath, data, meta: DEMMetadata):
    """Save NetCDF file (.nc) using netCDF4."""
    import netCDF4

    nrows, ncols = data.shape
    ds = netCDF4.Dataset(filepath, "w", format="NETCDF4")

    ds.createDimension("x", ncols)
    ds.createDimension("y", nrows)

    x_vals = meta.x0 + np.arange(ncols) * meta.dx
    y_vals = meta.y0 + np.arange(nrows) * meta.dy

    var_x = ds.createVariable("x", "f8", ("x",))
    var_y = ds.createVariable("y", "f8", ("y",))
    var_z = ds.createVariable("z", "f4", ("y", "x"), fill_value=meta.nodata)

    var_x[:] = x_vals
    var_y[:] = y_vals
    var_z[:] = data.astype(np.float32)

    var_x.units = "meters"
    var_y.units = "meters"
    var_z.units = "meters"
    var_z.description = "DEM elevation / depth"
    ds.close()


def load_dem_file(filepath, origin_bottom=True):
    """Universal loader that detects format by extension and content."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in [".tif", ".tiff"]:
        return load_geotiff(filepath, origin_bottom=origin_bottom)
    elif ext == ".nc":
        return load_netcdf(filepath, origin_bottom=origin_bottom)
    elif ext == ".asc" or is_esri_asc(filepath):
        return load_esri_asc(filepath, origin_bottom=origin_bottom)
    else:
        return load_ascii_funwave(filepath, origin_bottom=origin_bottom)


def save_dem_file(filepath, data, meta: DEMMetadata, fmt=None):
    """Universal saver by extension or specified format."""
    ext = os.path.splitext(filepath)[1].lower()
    if fmt is None:
        if ext in [".tif", ".tiff"]:
            fmt = "geotiff"
        elif ext == ".nc":
            fmt = "netcdf"
        elif ext == ".asc":
            fmt = "esri_asc"
        else:
            fmt = "funwave"

    if fmt == "geotiff" or ext in [".tif", ".tiff"]:
        save_geotiff(filepath, data, meta)
    elif fmt == "netcdf" or ext == ".nc":
        save_netcdf(filepath, data, meta)
    elif fmt == "esri_asc" or ext == ".asc":
        save_esri_asc(filepath, data, meta)
    else:
        save_ascii_funwave(filepath, data)
