"""
dem_editor/ui/main_window.py
Main Application Window for DEM Editor.
"""

import os
import sys
import numpy as np
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence, QIcon
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QLabel,
    QComboBox,
    QStatusBar,
    QToolBar,
    QGroupBox,
    QFrame,
)

from dem_editor.core.dem_model import DEMModel
from dem_editor.core.dem_io import get_crs_description, parse_crs_to_utm_info
from dem_editor.ui.table_view import DEMTableView
from dem_editor.ui.minimap_widget import DEMMinimapWidget
from dem_editor.ui.profile_widget import DEMProfileWidget
from dem_editor.ui.bathy_dialog import BathyDialog
from dem_editor.ui.dialogs import (
    InterpolateDialog,
    SmoothDialog,
    MathDialog,
    GridPropertiesDialog,
    AssignUTMDialog,
)
from dem_editor.ui.styles import DARK_THEME, LIGHT_THEME


class MainWindow(QMainWindow):
    """Scientific DEM Editor Main Window."""

    def __init__(self, initial_filepath: str = None):
        super().__init__()
        self.setWindowTitle("DEM Editor - FUNWAVE & Scientific Grids")
        self.resize(1280, 800)

        # Core Data Model
        self.dem_model = DEMModel()
        self.current_theme = "dark"

        # Setup UI Components
        self._init_ui()
        self._apply_theme("dark")

        # Connect model signals
        self.dem_model.historyChanged.connect(self._update_undo_redo_actions)
        self.dem_model.statusMessage.connect(self.statusBar().showMessage)
        self.dem_model.dataChanged.connect(self._update_stats_display)
        self.dem_model.metadataChanged.connect(self._on_metadata_changed)

        # Load file if provided
        if initial_filepath and os.path.isfile(initial_filepath):
            self.load_file(initial_filepath)
        elif os.path.isfile("5x5_malla_moloBatiMod2.dep"):
            self.load_file("5x5_malla_moloBatiMod2.dep")

    def _init_ui(self):
        # 1. Main Central Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Table View (Excel-style)
        self.table_view = DEMTableView(self.dem_model, self)
        self.splitter.addWidget(self.table_view)

        # Right Side Panel (Minimap, Cross-Section Profile, Statistics)
        self.side_panel = QWidget(self)
        self.side_panel.setMinimumWidth(340)
        self.side_panel.setMaximumWidth(480)
        side_layout = QVBoxLayout(self.side_panel)
        side_layout.setContentsMargins(6, 6, 6, 6)
        side_layout.setSpacing(8)

        # Minimap Box
        map_box = QGroupBox("Vista Global (Minimapa DEM)")
        map_layout = QVBoxLayout(map_box)
        map_layout.setContentsMargins(4, 4, 4, 4)
        map_layout.setSpacing(4)

        # Colormap & orientation selector bar
        map_ctrls = QHBoxLayout()
        map_ctrls.addWidget(QLabel("Color:"))
        self.combo_cmap = QComboBox()
        for cmap in ["terrain", "viridis", "plasma", "ocean", "coolwarm", "cividis", "jet", "gray"]:
            self.combo_cmap.addItem(cmap.capitalize(), cmap)
        self.combo_cmap.currentIndexChanged.connect(self._on_cmap_changed)
        map_ctrls.addWidget(self.combo_cmap)

        self.combo_orient = QComboBox()
        self.combo_orient.addItem("Fila 0: Abajo (FUNWAVE)", True)
        self.combo_orient.addItem("Fila 0: Arriba (Estándar)", False)
        self.combo_orient.currentIndexChanged.connect(self._on_orient_changed)
        map_ctrls.addWidget(self.combo_orient)

        map_layout.addLayout(map_ctrls)

        self.minimap = DEMMinimapWidget(self.dem_model, self)
        map_layout.addWidget(self.minimap, stretch=1)
        side_layout.addWidget(map_box, stretch=3)

        # Profile Box (1D Cross Section)
        prof_box = QGroupBox("Perfil Transecto 1D")
        prof_layout = QVBoxLayout(prof_box)
        prof_layout.setContentsMargins(4, 4, 4, 4)
        self.profile_widget = DEMProfileWidget(self.dem_model, self)
        prof_layout.addWidget(self.profile_widget)
        side_layout.addWidget(prof_box, stretch=2)

        # Statistics Card
        stats_box = QGroupBox("Estadísticas de Selección / DEM")
        self.stats_layout = QVBoxLayout(stats_box)
        self.stats_layout.setContentsMargins(8, 6, 8, 6)
        self.lbl_stats = QLabel("Sin datos")
        self.lbl_stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stats_layout.addWidget(self.lbl_stats)
        side_layout.addWidget(stats_box, stretch=1)

        self.splitter.addWidget(self.side_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self.splitter)

        # Connect Table View with Minimap and Profile
        self.table_view.visibleViewportChanged.connect(self.minimap.set_visible_viewport)
        self.minimap.cellSelected.connect(self.table_view.scroll_to_cell)
        self.table_view.activeCellChanged.connect(self._on_active_cell_changed)
        self.table_view.selectionStatsChanged.connect(self._on_selection_changed)

        # 2. Setup Menus and Toolbars
        self._create_actions()
        self._create_toolbars()
        self._create_statusbar()

    def _create_actions(self):
        # File Actions
        self.act_open = QAction("Abrir DEM...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.on_open_file)

        self.act_save = QAction("Guardar", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.on_save_file)

        self.act_save_as = QAction("Guardar Como...", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self.on_save_as_file)

        # Edit Actions
        self.act_undo = QAction("Deshacer", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.setEnabled(False)
        self.act_undo.triggered.connect(self.dem_model.undo)

        self.act_redo = QAction("Rehacer", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.setEnabled(False)
        self.act_redo.triggered.connect(self.dem_model.redo)

        self.act_delete_nan = QAction("Borrar a NaN (Del)", self)
        self.act_delete_nan.setShortcut(Qt.Key.Key_Delete)
        self.act_delete_nan.triggered.connect(self.on_delete_selected_to_nan)

        self.act_copy = QAction("Copiar celdas", self)
        self.act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.act_copy.triggered.connect(self.on_copy_cells)

        self.act_cut = QAction("Cortar celdas", self)
        self.act_cut.setShortcut(QKeySequence.StandardKey.Cut)
        self.act_cut.triggered.connect(self.on_cut_cells)

        self.act_paste = QAction("Pegar celdas", self)
        self.act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.act_paste.triggered.connect(self.on_paste_cells)

        self.act_fill_nans = QAction("Interpolar NaNs...", self)
        self.act_fill_nans.setShortcut("Ctrl+I")
        self.act_fill_nans.triggered.connect(self.on_interpolate_nans)

        self.act_smooth = QAction("Suavizar Selección...", self)
        self.act_smooth.setShortcut("Ctrl+R")
        self.act_smooth.triggered.connect(self.on_smooth_selection)

        self.act_bathy = QAction("Corrección FUNWAVE...", self)
        self.act_bathy.setShortcut("Ctrl+B")
        self.act_bathy.triggered.connect(self.on_bathy_correction)

        self.act_math = QAction("Operación Matemática...", self)
        self.act_math.setShortcut("Ctrl+M")
        self.act_math.triggered.connect(self.on_math_operation)

        self.act_grid_props = QAction("Propiedades de Malla...", self)
        self.act_grid_props.triggered.connect(self.on_grid_properties)

        self.act_toggle_theme = QAction("Tema Claro/Oscuro", self)
        self.act_toggle_theme.triggered.connect(self.on_toggle_theme)

    def _create_toolbars(self):
        toolbar = QToolBar("Barra de Herramientas Principal", self)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        toolbar.addAction(self.act_open)
        toolbar.addAction(self.act_save)
        toolbar.addAction(self.act_save_as)
        toolbar.addSeparator()

        toolbar.addAction(self.act_undo)
        toolbar.addAction(self.act_redo)
        toolbar.addSeparator()

        toolbar.addAction(self.act_delete_nan)
        toolbar.addAction(self.act_copy)
        toolbar.addAction(self.act_paste)
        toolbar.addAction(self.act_fill_nans)
        toolbar.addAction(self.act_smooth)
        toolbar.addAction(self.act_bathy)
        toolbar.addAction(self.act_math)
        toolbar.addSeparator()

        toolbar.addAction(self.act_grid_props)
        toolbar.addAction(self.act_toggle_theme)

    def _create_statusbar(self):
        status = QStatusBar(self)
        self.setStatusBar(status)

        self.lbl_cursor_info = QLabel("Fila: - | Col: - | Z: -")
        self.lbl_dim_info = QLabel("0 × 0")
        self.lbl_crs_info = QLabel("CRS: Sin definir")

        status.addPermanentWidget(self.lbl_cursor_info)
        status.addPermanentWidget(self.lbl_dim_info)
        status.addPermanentWidget(self.lbl_crs_info)

    def _apply_theme(self, theme_name: str):
        self.current_theme = theme_name
        if theme_name == "dark":
            self.setStyleSheet(DARK_THEME)
            self.table_view.table_model.is_dark_mode = True
        else:
            self.setStyleSheet(LIGHT_THEME)
            self.table_view.table_model.is_dark_mode = False
        self.table_view.table_model.on_data_updated()

    def on_toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._apply_theme(new_theme)

    def _on_cmap_changed(self):
        cmap = self.combo_cmap.currentData()
        self.minimap.set_colormap(cmap)

    def _on_orient_changed(self):
        val = self.combo_orient.currentData()
        self.dem_model.set_origin_bottom(val)

    def _on_metadata_changed(self):
        self._update_crs_display()

    def _update_crs_display(self):
        crs_desc = get_crs_description(self.dem_model.metadata.crs)
        self.lbl_crs_info.setText(f"CRS: {crs_desc}")

    def _update_undo_redo_actions(self, can_undo: bool, can_redo: bool):
        self.act_undo.setEnabled(can_undo)
        self.act_redo.setEnabled(can_redo)

    def _on_active_cell_changed(self, row: int, col: int, val: float):
        self.profile_widget.update_cell(row, col)
        meta = self.dem_model.metadata
        x_m = meta.x0 + col * meta.dx
        y_m = meta.y0 + row * meta.dy
        val_str = "NaN" if np.isnan(val) else f"{val:.4f}"
        self.lbl_cursor_info.setText(
            f"Fila (Y): {row} ({y_m:.1f}m) | Col (X): {col} ({x_m:.1f}m) | Z = {val_str}"
        )

    def _on_selection_changed(self, r_min: int, r_max: int, c_min: int, c_max: int):
        self._update_stats_display(r_min, r_max, c_min, c_max)

    def _update_stats_display(self, r_min=None, r_max=None, c_min=None, c_max=None):
        if r_min is None:
            bbox = self.table_view.get_selected_bounding_box()
            if bbox:
                r_min, r_max, c_min, c_max = bbox

        stats = self.dem_model.get_stats(r_min, r_max, c_min, c_max)
        nrows, ncols = self.dem_model.shape
        self.lbl_dim_info.setText(f"Malla: {nrows} filas × {ncols} cols")

        if r_min is not None and r_max is not None:
            scope_str = f"Selección [{r_min}:{r_max}, {c_min}:{c_max}]"
        else:
            scope_str = "DEM Completo"

        text = (
            f"<b>{scope_str}</b> ({stats['total']} celdas)<br>"
            f"• Mínimo: <b>{stats['min']:.3f}</b><br>"
            f"• Máximo: <b>{stats['max']:.3f}</b><br>"
            f"• Media: <b>{stats['mean']:.3f}</b> (±{stats['std']:.3f})<br>"
            f"• Válidas: <b>{stats['valid']}</b> | NaNs: <b style='color:#ff5577;'>{stats['nans']}</b>"
        )
        self.lbl_stats.setText(text)

    def load_file(self, filepath: str):
        try:
            self.dem_model.load_file(filepath)
            self.combo_orient.setCurrentIndex(0 if self.dem_model.metadata.origin_bottom else 1)
            self.table_view.scroll_to_cell(0, 0)
            self._update_stats_display()
            self._update_crs_display()
            self.setWindowTitle(f"DEM Editor - {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar", f"No se pudo cargar el archivo:\n{str(e)}")

    def on_open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir Archivo DEM",
            "",
            "Archivos DEM (*.dep *.asc *.txt *.dat *.tif *.tiff *.nc *.r2s);;FUNWAVE ASCII (*.dep *.txt *.dat);;ESRI ASC (*.asc);;Blue Kenue r2s (*.r2s);;GeoTIFF (*.tif *.tiff);;NetCDF (*.nc);;Todos (*.*)",
        )
        if filepath:
            self.load_file(filepath)

    def on_save_file(self):
        if not self.dem_model.metadata.filename:
            self.on_save_as_file()
            return
        target = self.dem_model.metadata.filename
        ext = os.path.splitext(target)[1].lower()
        if ext in [".tif", ".tiff"] and not self.dem_model.metadata.crs:
            utm_info = parse_crs_to_utm_info(self.dem_model.metadata.crs)
            default_zone = utm_info[0] if utm_info else 19
            default_north = utm_info[1] if utm_info else False
            dlg = AssignUTMDialog(default_zone=default_zone, is_north=default_north, parent=self)
            if dlg.exec():
                self.dem_model.set_crs(dlg.get_crs())
            else:
                return
        try:
            self.dem_model.save_file()
            QMessageBox.information(self, "Guardado", f"Archivo guardado exitosamente:\n{target}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el archivo:\n{str(e)}")

    def on_save_as_file(self):
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Guardar DEM Como",
            self.dem_model.metadata.filename or "dem_editado.dep",
            "GeoTIFF (*.tif);;ESRI ASCII Raster (*.asc);;FUNWAVE ASCII (*.dep);;Blue Kenue r2s (*.r2s);;NetCDF (*.nc);;Texto (*.txt)",
        )
        if filepath:
            ext = os.path.splitext(filepath)[1].lower()
            fmt = None
            if "GeoTIFF" in selected_filter:
                fmt = "geotiff"
                if not ext:
                    filepath += ".tif"
                    ext = ".tif"
            elif "ESRI" in selected_filter:
                fmt = "esri_asc"
                if not ext:
                    filepath += ".asc"
                    ext = ".asc"
            elif "NetCDF" in selected_filter:
                fmt = "netcdf"
                if not ext:
                    filepath += ".nc"
                    ext = ".nc"
            elif "Blue Kenue" in selected_filter:
                fmt = "r2s"
                if not ext:
                    filepath += ".r2s"
                    ext = ".r2s"
            elif "FUNWAVE" in selected_filter:
                fmt = "funwave"
                if not ext:
                    filepath += ".dep"
                    ext = ".dep"

            if (fmt == "geotiff" or ext in [".tif", ".tiff"]) and not self.dem_model.metadata.crs:
                utm_info = parse_crs_to_utm_info(self.dem_model.metadata.crs)
                default_zone = utm_info[0] if utm_info else 19
                default_north = utm_info[1] if utm_info else False
                dlg = AssignUTMDialog(default_zone=default_zone, is_north=default_north, parent=self)
                if dlg.exec():
                    self.dem_model.set_crs(dlg.get_crs())
                else:
                    return

            try:
                self.dem_model.save_file(filepath, fmt=fmt)
                self.setWindowTitle(f"DEM Editor - {os.path.basename(filepath)}")
                QMessageBox.information(self, "Guardado", f"Archivo guardado exitosamente:\n{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el archivo:\n{str(e)}")

    def on_copy_cells(self):
        self.table_view.copy_selection()

    def on_cut_cells(self):
        self.table_view.cut_selection()

    def on_paste_cells(self):
        self.table_view.paste_from_clipboard()

    def on_delete_selected_to_nan(self):
        bbox = self.table_view.get_selected_bounding_box()
        if bbox:
            self.dem_model.delete_selection(*bbox)

    def on_interpolate_nans(self):
        dlg = InterpolateDialog(self)
        if dlg.exec():
            method = dlg.get_method()
            self.dem_model.fill_all_nans(method=method)

    def on_smooth_selection(self):
        bbox = self.table_view.get_selected_bounding_box()
        if not bbox:
            QMessageBox.warning(self, "Aviso", "Selecciona primero un rango de celdas en la grilla.")
            return

        r_min, r_max, c_min, c_max = bbox
        bbox_str = f"Filas {r_min} a {r_max}, Cols {c_min} a {c_max}"
        dlg = SmoothDialog(bbox_str, self)
        if dlg.exec():
            params = dlg.get_params()
            self.dem_model.smooth_selection(
                r_min,
                r_max,
                c_min,
                c_max,
                method=params["method"],
                sigma=params["sigma"],
                filter_size=params["filter_size"],
                blend=params["blend"],
            )

    def on_bathy_correction(self):
        bbox = self.table_view.get_selected_bounding_box()
        dlg = BathyDialog(self.dem_model, scope_bbox=bbox, parent=self)
        dlg.exec()

    def on_math_operation(self):
        bbox = self.table_view.get_selected_bounding_box()
        bbox_str = f"Filas {bbox[0]} a {bbox[1]}, Cols {bbox[2]} a {bbox[3]}" if bbox else "Todo"
        dlg = MathDialog(bbox_str, self)
        if dlg.exec():
            p = dlg.get_params()
            if p["apply_all"] or not bbox:
                r_min, r_max = 0, self.dem_model.shape[0] - 1
                c_min, c_max = 0, self.dem_model.shape[1] - 1
            else:
                r_min, r_max, c_min, c_max = bbox

            self.dem_model.apply_math(r_min, r_max, c_min, c_max, p["op"], p["param"])

    def on_grid_properties(self):
        dlg = GridPropertiesDialog(self.dem_model, self)
        if dlg.exec():
            dlg.apply_changes()
