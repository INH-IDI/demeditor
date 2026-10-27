"""
dem_editor/ui/dialogs.py
Dialog windows for Interpolation, Smoothing, Mathematical operations, and Grid Metadata.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QDialogButtonBox,
    QRadioButton,
    QButtonGroup,
    QLineEdit,
    QFileDialog,
)

from dem_editor.core.dem_model import DEMModel
from dem_editor.core.dem_io import (
    utm_to_epsg,
    parse_crs_to_utm_info,
    get_crs_description,
    crs_to_wkt,
)


class InterpolateDialog(QDialog):
    """Dialog for choosing NaN filling interpolation method."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rellenar Celdas NaN (Interpolación)")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Selecciona el algoritmo científico para interpolar y rellenar "
            "todas las celdas vacías (NaN) del DEM:"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.combo_method = QComboBox()
        self.combo_method.addItem("Bilineal (Triangulación lineal / Delaunay)", "linear")
        self.combo_method.addItem("Vecino Más Cercano (Nearest Neighbor)", "nearest")
        self.combo_method.addItem("Bicúbica (Spline 2D)", "cubic")
        self.combo_method.addItem("Difusión Armónica (Laplace Inpainting EDP)", "harmonic")

        form.addRow("Método:", self.combo_method)
        layout.addLayout(form)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #9ab; font-size: 11px; padding: 6px;")
        layout.addWidget(self.desc_label)
        self.combo_method.currentIndexChanged.connect(self._update_desc)
        self._update_desc()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.button(QDialogButtonBox.StandardButton.Ok).setText("Interpolar Todo el DEM")
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _update_desc(self):
        method = self.combo_method.currentData()
        descs = {
            "linear": "Interpola usando superficies triangulares continuas entre los nodos válidos circundantes. Rellena bordes exteriores por vecino más cercano.",
            "nearest": "Asigna a cada celda NaN el valor del nodo válido más próximo en distancia euclidiana. Es ultra-rápido.",
            "cubic": "Genera superficies curvas de curvatura continua de orden superior. Ideal para pendientes suaves.",
            "harmonic": "Resuelve la ecuación diferencial de Laplace (∇²Z = 0) en la región NaN con condiciones de borde Dirichlet. Es la transición más suave para batimetría/topografía.",
        }
        self.desc_label.setText(descs.get(method, ""))

    def get_method(self) -> str:
        return self.combo_method.currentData()


class SmoothDialog(QDialog):
    """Dialog for configuring region smoothing."""

    def __init__(self, bbox_info: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Suavizar Región Seleccionada")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        lbl = QLabel(f"Región seleccionada: <b>{bbox_info}</b>")
        layout.addWidget(lbl)

        form = QFormLayout()
        self.combo_method = QComboBox()
        self.combo_method.addItem("Filtro Gaussiano 2D", "gaussian")
        self.combo_method.addItem("Filtro de Media Móvil (Caja/Uniforme)", "box")
        self.combo_method.addItem("Filtro Mediana (Eliminar picos/outliers)", "median")
        form.addRow("Algoritmo:", self.combo_method)

        self.spin_sigma = QDoubleSpinBox()
        self.spin_sigma.setRange(0.1, 15.0)
        self.spin_sigma.setSingleStep(0.2)
        self.spin_sigma.setValue(1.5)
        form.addRow("Radio / Sigma (σ):", self.spin_sigma)

        self.spin_size = QSpinBox()
        self.spin_size.setRange(3, 31)
        self.spin_size.setSingleStep(2)
        self.spin_size.setValue(3)
        form.addRow("Tamaño de Ventana (px):", self.spin_size)

        self.chk_blend = QCheckBox("Transición gradual en bordes (evitar escalones)")
        self.chk_blend.setChecked(True)
        form.addRow("", self.chk_blend)

        layout.addLayout(form)

        self.combo_method.currentIndexChanged.connect(self._on_method_changed)
        self._on_method_changed()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.button(QDialogButtonBox.StandardButton.Ok).setText("Aplicar Suavizado")
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _on_method_changed(self):
        method = self.combo_method.currentData()
        self.spin_sigma.setEnabled(method == "gaussian")
        self.spin_size.setEnabled(method in ["box", "median"])

    def get_params(self):
        return {
            "method": self.combo_method.currentData(),
            "sigma": self.spin_sigma.value(),
            "filter_size": self.spin_size.value(),
            "blend": self.chk_blend.isChecked(),
        }


class MathDialog(QDialog):
    """Dialog for arithmetic operations on selection or full DEM."""

    def __init__(self, bbox_info: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Operación Matemática en Celdas")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.combo_op = QComboBox()
        self.combo_op.addItem("Sumar constante (Offset de marea/datum)", "add")
        self.combo_op.addItem("Multiplicar por factor (Escala)", "mult")
        self.combo_op.addItem("Invertir signo (Z = -Z)", "invert")
        self.combo_op.addItem("Asignar valor fijo constante", "set")
        form.addRow("Operación:", self.combo_op)

        self.spin_param = QDoubleSpinBox()
        self.spin_param.setRange(-1e9, 1e9)
        self.spin_param.setDecimals(4)
        self.spin_param.setValue(1.0)
        form.addRow("Valor / Parámetro:", self.spin_param)

        self.chk_all = QCheckBox("Aplicar a TODO el DEM (no solo selección)")
        form.addRow("", self.chk_all)

        layout.addLayout(form)

        self.combo_op.currentIndexChanged.connect(self._on_op_changed)
        self._on_op_changed()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.button(QDialogButtonBox.StandardButton.Ok).setText("Aplicar Operación")
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _on_op_changed(self):
        op = self.combo_op.currentData()
        self.spin_param.setEnabled(op != "invert")

    def get_params(self):
        return {
            "op": self.combo_op.currentData(),
            "param": self.spin_param.value(),
            "apply_all": self.chk_all.isChecked(),
        }


class GridPropertiesDialog(QDialog):
    """Dialog to inspect and edit DEM metadata, coordinates, and UTM/CRS."""

    def __init__(self, dem_model: DEMModel, parent=None):
        super().__init__(parent)
        self._dem = dem_model
        meta = dem_model.metadata
        self.setWindowTitle("Propiedades de la Malla y Coordenadas")
        self.setMinimumWidth(460)

        main_layout = QVBoxLayout(self)

        # 1. Geometria de la malla
        grp_geo = QGroupBox("Geometría y Orientación")
        form_geo = QFormLayout(grp_geo)

        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(0.0001, 1e6)
        self.spin_dx.setDecimals(4)
        self.spin_dx.setValue(meta.dx)
        form_geo.addRow("Paso espacial ΔX (m):", self.spin_dx)

        self.spin_dy = QDoubleSpinBox()
        self.spin_dy.setRange(0.0001, 1e6)
        self.spin_dy.setDecimals(4)
        self.spin_dy.setValue(meta.dy)
        form_geo.addRow("Paso espacial ΔY (m):", self.spin_dy)

        self.spin_x0 = QDoubleSpinBox()
        self.spin_x0.setRange(-1e9, 1e9)
        self.spin_x0.setDecimals(2)
        self.spin_x0.setValue(meta.x0)
        form_geo.addRow("Origen X₀ (Easting / m):", self.spin_x0)

        self.spin_y0 = QDoubleSpinBox()
        self.spin_y0.setRange(-1e9, 1e9)
        self.spin_y0.setDecimals(2)
        self.spin_y0.setValue(meta.y0)
        form_geo.addRow("Origen Y₀ (Northing / m):", self.spin_y0)

        self.spin_nodata = QDoubleSpinBox()
        self.spin_nodata.setRange(-1e9, 1e9)
        self.spin_nodata.setDecimals(2)
        self.spin_nodata.setValue(meta.nodata if meta.nodata is not None else -9999.0)
        form_geo.addRow("Valor NoData (exportación):", self.spin_nodata)

        self.combo_orient = QComboBox()
        self.combo_orient.addItem("FUNWAVE: Fila 0 es la esquina inferior (Sur)", True)
        self.combo_orient.addItem("Estándar: Fila 0 es la esquina superior (Norte)", False)
        self.combo_orient.setCurrentIndex(0 if meta.origin_bottom else 1)
        form_geo.addRow("Orientación Eje Y:", self.combo_orient)

        main_layout.addWidget(grp_geo)

        # 2. Sistema de Coordenadas (CRS / Proyeccion)
        grp_crs = QGroupBox("Sistema de Referencia de Coordenadas (CRS / UTM)")
        form_crs = QFormLayout(grp_crs)

        self.combo_crs_mode = QComboBox()
        self.combo_crs_mode.addItem("UTM (WGS 84)", "utm")
        self.combo_crs_mode.addItem("Código EPSG", "epsg")
        self.combo_crs_mode.addItem("Sin proyección (Local / Relativo)", "none")
        self.combo_crs_mode.addItem("Personalizado (WKT / Proj)", "custom")
        form_crs.addRow("Modo de Coordenadas:", self.combo_crs_mode)

        # UTM controls
        utm_info = parse_crs_to_utm_info(meta.crs)
        default_zone = utm_info[0] if utm_info else (19 if abs(meta.y0) > 1e5 else 19)
        default_north = utm_info[1] if utm_info else False

        self.spin_utm_zone = QSpinBox()
        self.spin_utm_zone.setRange(1, 60)
        self.spin_utm_zone.setValue(default_zone)
        form_crs.addRow("Zona UTM (1-60):", self.spin_utm_zone)

        self.combo_utm_hemi = QComboBox()
        self.combo_utm_hemi.addItem("Sur (S) [Chile / Sudamérica]", False)
        self.combo_utm_hemi.addItem("Norte (N)", True)
        self.combo_utm_hemi.setCurrentIndex(1 if default_north else 0)
        form_crs.addRow("Hemisferio UTM:", self.combo_utm_hemi)

        # EPSG controls
        self.spin_epsg = QSpinBox()
        self.spin_epsg.setRange(1000, 999999)
        init_epsg = 32719
        if utm_info:
            init_epsg = utm_to_epsg(utm_info[0], utm_info[1])
        elif meta.crs and meta.crs.isdigit():
            init_epsg = int(meta.crs)
        elif meta.crs and meta.crs.upper().startswith("EPSG:"):
            try:
                init_epsg = int(meta.crs.split(":")[1])
            except ValueError:
                pass
        self.spin_epsg.setValue(init_epsg)
        form_crs.addRow("Código EPSG:", self.spin_epsg)

        # Custom WKT
        self.txt_custom_crs = QLineEdit()
        self.txt_custom_crs.setText(meta.crs if meta.crs else "")
        self.txt_custom_crs.setPlaceholderText("WKT, PROJ, o ruta a .prj")
        form_crs.addRow("WKT / Definición:", self.txt_custom_crs)

        # Button to load .prj
        self.btn_load_prj = QPushButton("Cargar desde archivo .prj...")
        self.btn_load_prj.clicked.connect(self._on_load_prj_clicked)
        form_crs.addRow("", self.btn_load_prj)

        # Preview label
        self.lbl_crs_preview = QLabel()
        self.lbl_crs_preview.setWordWrap(True)
        form_crs.addRow("CRS Resuelto:", self.lbl_crs_preview)

        main_layout.addWidget(grp_crs)

        # Initial mode selection
        if utm_info is not None:
            self.combo_crs_mode.setCurrentIndex(0)
        elif meta.crs and (meta.crs.isdigit() or meta.crs.upper().startswith("EPSG:")):
            self.combo_crs_mode.setCurrentIndex(1)
        elif not meta.crs:
            if abs(meta.y0) > 1e5:
                self.combo_crs_mode.setCurrentIndex(0)  # Likely UTM coordinates
            else:
                self.combo_crs_mode.setCurrentIndex(2)  # Local
        else:
            self.combo_crs_mode.setCurrentIndex(3)

        self.combo_crs_mode.currentIndexChanged.connect(self._on_crs_mode_changed)
        self.spin_utm_zone.valueChanged.connect(self._update_crs_preview)
        self.combo_utm_hemi.currentIndexChanged.connect(self._update_crs_preview)
        self.spin_epsg.valueChanged.connect(self._update_crs_preview)
        self.txt_custom_crs.textChanged.connect(self._update_crs_preview)

        self._on_crs_mode_changed()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        main_layout.addWidget(bbox)

    def _on_load_prj_clicked(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo .prj", "", "Archivos de Proyección (*.prj);;Todos (*.*)"
        )
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    wkt = f.read().strip()
                if wkt:
                    utm = parse_crs_to_utm_info(wkt)
                    if utm:
                        self.combo_crs_mode.setCurrentIndex(0)
                        self.spin_utm_zone.setValue(utm[0])
                        self.combo_utm_hemi.setCurrentIndex(1 if utm[1] else 0)
                    else:
                        self.combo_crs_mode.setCurrentIndex(3)
                        self.txt_custom_crs.setText(wkt)
                    self._update_crs_preview()
            except Exception as e:
                self.lbl_crs_preview.setText(f"<font color='red'>Error al leer .prj: {e}</font>")

    def _on_crs_mode_changed(self):
        mode = self.combo_crs_mode.currentData()
        is_utm = (mode == "utm")
        is_epsg = (mode == "epsg")
        is_custom = (mode == "custom")

        self.spin_utm_zone.setVisible(is_utm)
        self.combo_utm_hemi.setVisible(is_utm)
        self.spin_epsg.setVisible(is_epsg)
        self.txt_custom_crs.setVisible(is_custom)
        self._update_crs_preview()

    def _update_crs_preview(self):
        mode = self.combo_crs_mode.currentData()
        if mode == "utm":
            z = self.spin_utm_zone.value()
            n = self.combo_utm_hemi.currentData()
            epsg = utm_to_epsg(z, n)
            h = "N" if n else "S"
            self.lbl_crs_preview.setText(f"<b>WGS 84 / UTM {z}{h}</b> (EPSG:{epsg})")
        elif mode == "epsg":
            code = self.spin_epsg.value()
            desc = get_crs_description(f"EPSG:{code}")
            self.lbl_crs_preview.setText(f"<b>{desc}</b>")
        elif mode == "none":
            self.lbl_crs_preview.setText("<i>Sin proyección (Coordenadas relativas / locales)</i>")
        else:
            wkt = self.txt_custom_crs.text().strip()
            desc = get_crs_description(wkt) if wkt else "Vacío"
            self.lbl_crs_preview.setText(f"<b>{desc}</b>")

    def get_resolved_crs(self) -> str:
        mode = self.combo_crs_mode.currentData()
        if mode == "utm":
            z = self.spin_utm_zone.value()
            n = self.combo_utm_hemi.currentData()
            return f"EPSG:{utm_to_epsg(z, n)}"
        elif mode == "epsg":
            return f"EPSG:{self.spin_epsg.value()}"
        elif mode == "none":
            return ""
        else:
            return self.txt_custom_crs.text().strip()

    def apply_changes(self):
        meta = self._dem.metadata
        meta.dx = self.spin_dx.value()
        meta.dy = self.spin_dy.value()
        meta.x0 = self.spin_x0.value()
        meta.y0 = self.spin_y0.value()
        meta.nodata = self.spin_nodata.value()
        meta.crs = self.get_resolved_crs()
        self._dem.set_origin_bottom(self.combo_orient.currentData())
        self._dem.metadataChanged.emit()


class AssignUTMDialog(QDialog):
    """Quick dialog to assign UTM coordinates when saving GeoTIFF without CRS."""

    def __init__(self, default_zone=19, is_north=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Asignar Coordenadas UTM a GeoTIFF")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        lbl = QLabel(
            "<b>El DEM no tiene un Sistema de Coordenadas (CRS) asignado.</b><br>"
            "Para que programas externos (QGIS, ArcGIS, Civil 3D) puedan georreferenciar "
            "el archivo GeoTIFF correctamente, asigne una Zona UTM:"
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        form = QFormLayout()

        self.spin_zone = QSpinBox()
        self.spin_zone.setRange(1, 60)
        self.spin_zone.setValue(default_zone)
        form.addRow("Zona UTM (1-60):", self.spin_zone)

        self.combo_hemi = QComboBox()
        self.combo_hemi.addItem("Sur (S) [Chile / Sudamérica]", False)
        self.combo_hemi.addItem("Norte (N)", True)
        self.combo_hemi.setCurrentIndex(1 if is_north else 0)
        form.addRow("Hemisferio:", self.combo_hemi)

        self.lbl_preview = QLabel()
        form.addRow("Proyección:", self.lbl_preview)

        layout.addLayout(form)

        self.chk_no_crs = QCheckBox("Guardar sin proyección (coordenadas relativas)")
        layout.addWidget(self.chk_no_crs)

        self.spin_zone.valueChanged.connect(self._update_preview)
        self.combo_hemi.currentIndexChanged.connect(self._update_preview)
        self.chk_no_crs.toggled.connect(self._on_no_crs_toggled)
        self._update_preview()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _on_no_crs_toggled(self, checked):
        self.spin_zone.setEnabled(not checked)
        self.combo_hemi.setEnabled(not checked)
        if checked:
            self.lbl_preview.setText("<i>Sin proyección</i>")
        else:
            self._update_preview()

    def _update_preview(self):
        if not self.chk_no_crs.isChecked():
            z = self.spin_zone.value()
            n = self.combo_hemi.currentData()
            epsg = utm_to_epsg(z, n)
            h = "N" if n else "S"
            self.lbl_preview.setText(f"<b>WGS 84 / UTM {z}{h}</b> (EPSG:{epsg})")

    def get_crs(self) -> str:
        if self.chk_no_crs.isChecked():
            return ""
        z = self.spin_zone.value()
        n = self.combo_hemi.currentData()
        return f"EPSG:{utm_to_epsg(z, n)}"
