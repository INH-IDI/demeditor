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
)

from dem_editor.core.dem_model import DEMModel


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
    """Dialog to inspect and edit DEM metadata and coordinates."""

    def __init__(self, dem_model: DEMModel, parent=None):
        super().__init__(parent)
        self._dem = dem_model
        meta = dem_model.metadata
        self.setWindowTitle("Propiedades de la Malla y Coordenadas")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(0.0001, 1e6)
        self.spin_dx.setDecimals(4)
        self.spin_dx.setValue(meta.dx)
        form.addRow("Paso espacial ΔX (m):", self.spin_dx)

        self.spin_dy = QDoubleSpinBox()
        self.spin_dy.setRange(0.0001, 1e6)
        self.spin_dy.setDecimals(4)
        self.spin_dy.setValue(meta.dy)
        form.addRow("Paso espacial ΔY (m):", self.spin_dy)

        self.spin_x0 = QDoubleSpinBox()
        self.spin_x0.setRange(-1e9, 1e9)
        self.spin_x0.setDecimals(2)
        self.spin_x0.setValue(meta.x0)
        form.addRow("Origen X₀ (m):", self.spin_x0)

        self.spin_y0 = QDoubleSpinBox()
        self.spin_y0.setRange(-1e9, 1e9)
        self.spin_y0.setDecimals(2)
        self.spin_y0.setValue(meta.y0)
        form.addRow("Origen Y₀ (m):", self.spin_y0)

        self.spin_nodata = QDoubleSpinBox()
        self.spin_nodata.setRange(-1e9, 1e9)
        self.spin_nodata.setDecimals(2)
        self.spin_nodata.setValue(meta.nodata if meta.nodata is not None else -9999.0)
        form.addRow("Valor NoData (exportación):", self.spin_nodata)

        self.combo_orient = QComboBox()
        self.combo_orient.addItem("FUNWAVE: Fila 0 es la esquina inferior (Sur)", True)
        self.combo_orient.addItem("Estándar: Fila 0 es la esquina superior (Norte)", False)
        self.combo_orient.setCurrentIndex(0 if meta.origin_bottom else 1)
        form.addRow("Orientación Eje Y:", self.combo_orient)

        layout.addLayout(form)

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def apply_changes(self):
        meta = self._dem.metadata
        meta.dx = self.spin_dx.value()
        meta.dy = self.spin_dy.value()
        meta.x0 = self.spin_x0.value()
        meta.y0 = self.spin_y0.value()
        meta.nodata = self.spin_nodata.value()
        self._dem.set_origin_bottom(self.combo_orient.currentData())
        self._dem.metadataChanged.emit()
