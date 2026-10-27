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

# DEM EDITOR — Agent Notes

PyQt6 scientific 2D DEM/bathymetry grid editor (FUNWAVE-TVD). No `requirements.txt` / `pyproject.toml` / lint / typecheck / CI workflows. Same caveman rules duplicated in `.github/copilot-instructions.md`, `.cursor/rules/caveman.mdc`, `.clinerules/caveman.md`, `.windsurf/rules/caveman.md` — edit here, not there.

## Commands (system `python3`, no venv)
- Run GUI: `python3 main.py [file.dep]` or `./run_editor.sh [file]` — needs display, never run headless in agent (blocks).
- All tests: `python3 -m pytest tests/ -q` (~0.8s, 24 tests).
- Single test: `python3 -m pytest tests/test_fill_nans.py::test_fast_large -q`.
- Deps preinstalled (py3.12): `PyQt6`, `numpy`, `scipy`, `GDAL (osgeo)`, `netCDF4`. Do not `pip install`; `tifffile` not used (GDAL handles `.tif`).

## Architecture
- Entrypoints: `main.py` → `dem_editor/ui/main_window.py` (`MainWindow`).
- `dem_editor/core/`: `dem_model.py` (reactive `QObject`, sole state owner), `dem_io.py`, `dem_ops.py`, `funwave_bathy.py`, `dem_clipboard.py`.
- `dem_editor/ui/`: `table_view.py`, `minimap_widget.py`, `profile_widget.py`, `dialogs.py`, `bathy_dialog.py`, `main_window.py`.
- `DEMModel` signals: `dataChanged / metadataChanged / historyChanged(can_undo,can_redo) / statusMessage`. Mutate via model methods only (`paste_block`, fill/smooth wrappers) so undo + views stay in sync. `max_history=30`, one `HistoryItem` per user op (paste = single undo).

## Data conventions (do not guess)
- Memory: missing = `np.nan`; `inf` sanitized to `NaN` (`dem_ops._sanitize`). Never store `-9999` in array.
- Disk: `NODATA_value -9999` for `.asc`/`.tif`/`.nc`.  `.r2s` (Blue Kenue 2D Rect Scalar, `:EndHeader` then rows; row 0 = South, no flip; `:NoDataValue` honored; single attribute, `:Angle 0` only). Lazy imports: `osgeo.gdal`, `netCDF4` inside `dem_io.py` functions.
- Orientation: `DEMMetadata.origin_bottom=True` = FUNWAVE (row 0 = South/Y=0). Preserve flag on load/save; do not flip.
- `.dep/.txt/.dat` = Depth: positive water, negative land. No sign flip anywhere.
- Table: keep virtualized `QAbstractTableModel` (`DEMTableModel`). No per-cell widgets; must handle >500×500. NaN = soft-red cells, magenta in minimap.

## Numerical gotchas (hard-earned, see `dem_ops.py` header + tests)
- `fill_nans`: `cubic`/`linear` clamped to `[vmin,vmax]` (Clough-Tocher overshoot); all-NaN input returns all-NaN (not zeros).
- `harmonic`: stable Jacobi `omega=1.0` only. SOR/Jacobi `omega=1.6` diverges (±1e91). Keep divergence guard + max-principle clamp.
- `griddata` Delaunay only if `cells <= 500*500` and `valid_points <= 30_000` (`_GRIDDATA_MAX_*`); else fast local fallback. `test_fast_large` (600×600) must hit fast path — check `info["method_used"]`.
- `funwave_bathy.py` replicates `mod_bathy_correction.F` exactly: `Grad=|D(c+1)-D(c-1)|/DX` (no `/2`); stencil `0.4*center + 0.15*(N+S+E+O)` Jacobi, mass-conserving; symmetric-peak center has grad 0, never touched; edges `pad edge` (Neumann, Fortran ghost-cell equiv); NaN never updated, stencil renormalizes; `SmoothBelowDepth` mask excludes cells + 4-neighbors (land stays intact).
- Clipboard (`dem_clipboard.py`): TSV with `\t` then `;` fallback; ES comma decimals (`3,14`, `1.234,56`); `NAN_TOKENS={"",nan,null,none,-,na,n/a,nd}`; invalid token → `mask=False`, destination cell untouched; strip Excel trailing `\n`; single-cell source tiles over selection; clip at grid border.

## Testing quirks
- Qt tests need headless: `os.environ.setdefault("QT_QPA_PLATFORM","offscreen")` before `QApplication` (see `tests/test_copy_paste.py`). New Qt-touching tests must copy this.
- Code uses `PyQt6` only; env also has `PyQt5` installed — do not import it.

## Git / files
- `.gitignore` blocks `*.dep *.nc *.tif* *.asc *.dat *.txt *.png *.log`, `__pycache__/`, `.pytest_cache/`. Sample `.dep` + `screenshot_preview.png` in root are local-only. Never `git add` data/screenshots.
