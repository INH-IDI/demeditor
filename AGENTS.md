Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.

---

# DEM EDITOR — Project Context for Agents

## Project Overview
Scientific 2D Digital Elevation Model (DEM) and Bathymetry Grid Editor. Designed for coastal/ocean hydrodynamic modeling (FUNWAVE-TVD) and geospatial raster manipulation.

## Tech Stack
- **Language**: Python 3.12+
- **GUI Framework**: PyQt6
- **Numerical Engines**: NumPy, SciPy (scipy.ndimage, scipy.interpolate)
- **Spatial I/O**: GDAL, NetCDF4, tifffile, Matplotlib colormaps

## Core Conventions
1. **Coordinate Orientation**:
   - FUNWAVE mode: Row 0 is at bottom (South, Y=0).
   - Standard mode: Row 0 is at top (North).
2. **Missing / Empty Data**:
   - Represented as `np.nan` in array memory.
   - Saved with standard sentinel (e.g. `NODATA_value -9999`) in ESRI ASC, GeoTIFF, and NetCDF.
   - Displayed with soft red highlight in table grid and magenta in global minimap.
3. **Table Performance**:
   - Must use virtualized `QAbstractTableModel` (`DEMTableModel`) to support grids > 500x500 without UI freeze.

## Key Files
- `main.py` / `run_editor.sh`: Application entrypoints.
- `dem_editor/core/dem_model.py`: Reactive state model, Undo/Redo history stack.
- `dem_editor/core/dem_io.py`: File loaders/savers for ASCII (.dep), ESRI (.asc), GeoTIFF (.tif), NetCDF (.nc).
- `dem_editor/core/dem_ops.py`: Numerical operations (fill NaNs: linear/nearest/cubic/harmonic; smoothing: gaussian/box/median).
- `dem_editor/ui/main_window.py`: Main window, toolbar, docking, status bar.
- `dem_editor/ui/table_view.py`: Virtualized Excel-style table view.
- `dem_editor/ui/minimap_widget.py`: 2D minimap with synchronized viewport bounding box.
- `dem_editor/ui/profile_widget.py`: Real-time 1D cross-section transects (X/Y).

## How to Test & Run
```bash
# Run application
python3 main.py [optional_path_to_dem]
# Or via launcher
./run_editor.sh
```
