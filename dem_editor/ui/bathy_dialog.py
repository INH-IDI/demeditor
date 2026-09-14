"""
dem_editor/ui/bathy_dialog.py
Ventana aparte: correccion batimetria FUNWAVE-TVD con preview.
No altera main window: QDialog independiente + plot propio (QPainter).
"""

from typing import Dict, Optional, Tuple

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dem_editor.core.funwave_bathy import (
    DEFAULT_MAX_ITER,
    DEFAULT_MIN_DEPTH_FRC,
    DEFAULT_SLOPE_CAP,
    DEFAULT_SMOOTH_BELOW,
    bathy_correction,
)


class TransectPreview(QWidget):
    """Dos transectos (fila/col central ambito): original gris vs corregido verde."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._orig = None
        self._corr = None
        self._scope = ""

    def set_data(self, orig: np.ndarray, corr: np.ndarray, scope: str):
        # Recorta a 2000 pts para pintar rapido
        def _ds(a, ax):
            n = a.shape[ax]
            if n > 2000:
                idx = np.linspace(0, n - 1, 2000).astype(int)
                return np.take(a, idx, axis=ax)
            return a
        self._orig = _ds(np.asarray(orig, dtype=float), 1)
        self._corr = _ds(np.asarray(corr, dtype=float), 1)
        self._scope = scope
        self.update()

    def _draw_transect(self, p: QPainter, rect, a: np.ndarray, b: np.ndarray, title: str):
        p.fillRect(rect, QColor(20, 20, 24))
        p.setPen(QPen(QColor(150, 170, 190)))
        p.drawText(rect.left() + 6, rect.top() + 14, title)
        vals = np.concatenate([a[np.isfinite(a)], b[np.isfinite(b)]]) if a.size else np.array([0])
        if vals.size == 0:
            return
        vmin, vmax = float(vals.min()), float(vals.max())
        if vmax - vmin < 1e-12:
            vmax = vmin + 1.0
        pad = 24
        W, H = rect.width() - 2 * pad, rect.height() - 30
        ox, oy = rect.left() + pad, rect.top() + 20
        n = len(a)
        def xy(i, v):
            x = ox + (i / max(1, n - 1)) * W
            y = oy + H - (v - vmin) / (vmax - vmin) * H
            return x, y
        # Ejes min/max labels
        p.setPen(QPen(QColor(90, 90, 100)))
        p.drawText(rect.left() + 2, oy + 8, f"{vmax:.2f}")
        p.drawText(rect.left() + 2, oy + H, f"{vmin:.2f}")
        for arr, col, w in ((a, QColor(140, 140, 150), 1), (b, QColor(80, 220, 130), 2)):
            pen = QPen(col)
            pen.setWidth(w)
            p.setPen(pen)
            prev = None
            for i, v in enumerate(arr):
                if not np.isfinite(v):
                    prev = None
                    continue
                x, y = xy(i, v)
                if prev is not None:
                    p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
                prev = (x, y)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._orig is None:
            p.fillRect(self.rect(), QColor(20, 20, 24))
            p.setPen(QPen(QColor(120, 120, 130)))
            p.drawText(20, 30, "Pulsa «Calcular preview» para ver antes/después.")
            return
        r = self.rect()
        h = r.height() // 2
        rm = self._orig.shape[0] // 2
        cm = self._orig.shape[1] // 2
        self._draw_transect(p, r.adjusted(0, 0, 0, -h),
                            self._orig[rm, :], self._corr[rm, :],
                            f"Fila central {self._scope} — gris orig / verde FUNWAVE")
        self._draw_transect(p, r.adjusted(0, h, 0, 0),
                            self._orig[:, cm], self._corr[:, cm],
                            "Columna central — gris orig / verde FUNWAVE")


class BathyDialog(QDialog):
    """Parametros + preview + aplicar. Todo vive aqui, main intacto."""

    def __init__(self, dem_model, scope_bbox=None, parent=None):
        super().__init__(parent)
        self._dem = dem_model
        self._bbox = scope_bbox  # (rmin,rmax,cmin,cmax) o None
        self._preview = None  # (corr_block, info, scope, params_key)
        self._cancel = False
        self.setWindowTitle("Corrección batimetría FUNWAVE-TVD")
        self.setMinimumSize(560, 640)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        info = QLabel(
            "Algoritmo BATHY_CORRECTION (Shi 2017, mod_bathy_correction.F): "
            "donde |ΔD|/DX > SlopeCap, D = 0.4·D + 0.15·Σvecinos, "
            "itera hasta cambio ≤5% (máx 1000). NaN intactos."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Ambito
        g_scope = QGroupBox("Ámbito")
        hs = QHBoxLayout(g_scope)
        self.rb_sel = QRadioButton("Selección actual")
        self.rb_all = QRadioButton("DEM completo")
        nrows, ncols = self._dem.shape
        if self._bbox:
            r0, r1, c0, c1 = self._bbox
            self.rb_sel.setText(f"Selección [{r0}:{r1}, {c0}:{c1}]")
            self.rb_sel.setChecked(True)
        else:
            self.rb_sel.setEnabled(False)
            self.rb_all.setChecked(True)
        self.rb_all.setText(f"DEM completo ({nrows}×{ncols})")
        hs.addWidget(self.rb_sel)
        hs.addWidget(self.rb_all)
        layout.addWidget(g_scope)

        # Parametros
        form = QFormLayout()
        self.sp_cap = QDoubleSpinBox()
        self.sp_cap.setRange(0.05, 10.0)
        self.sp_cap.setSingleStep(0.05)
        self.sp_cap.setValue(DEFAULT_SLOPE_CAP)
        form.addRow("SlopeCap:", self.sp_cap)

        hb = QHBoxLayout()
        self.cb_all = QCheckBox("Todo (default FUNWAVE)")
        self.cb_all.setChecked(True)
        self.sp_below = QDoubleSpinBox()
        self.sp_below.setRange(-1000.0, 1000.0)
        self.sp_below.setValue(0.0)
        self.sp_below.setEnabled(False)
        self.sp_below.setToolTip("Depth umbral: solo corrige Depth ≥ valor (agua). Tierra intacta.")
        self.cb_all.toggled.connect(lambda c: self.sp_below.setEnabled(not c))
        hb.addWidget(self.cb_all)
        hb.addWidget(QLabel("SmoothBelowDepth:"))
        hb.addWidget(self.sp_below)
        form.addRow(hb)

        self.sp_minfrc = QDoubleSpinBox()
        self.sp_minfrc.setRange(0.01, 2.0)
        self.sp_minfrc.setSingleStep(0.01)
        self.sp_minfrc.setValue(DEFAULT_MIN_DEPTH_FRC)
        form.addRow("MinDepthFrc:", self.sp_minfrc)

        meta = self._dem.metadata
        self.sp_dx = QDoubleSpinBox()
        self.sp_dx.setRange(1e-6, 1e6)
        self.sp_dx.setValue(meta.dx if meta.dx > 0 else 1.0)
        self.sp_dy = QDoubleSpinBox()
        self.sp_dy.setRange(1e-6, 1e6)
        self.sp_dy.setValue(meta.dy if meta.dy > 0 else 1.0)
        hd = QHBoxLayout()
        hd.addWidget(QLabel("DX:"))
        hd.addWidget(self.sp_dx)
        hd.addWidget(QLabel("DY:"))
        hd.addWidget(self.sp_dy)
        form.addRow(hd)

        self.sp_iter = QSpinBox()
        self.sp_iter.setRange(1, 2000)
        self.sp_iter.setValue(DEFAULT_MAX_ITER)
        form.addRow("Máx iter:", self.sp_iter)
        layout.addLayout(form)

        # Preview controls
        hp = QHBoxLayout()
        self.btn_prev = QPushButton("Calcular preview")
        self.btn_prev.clicked.connect(self.on_preview)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(lambda: setattr(self, "_cancel", True))
        hp.addWidget(self.btn_prev)
        hp.addWidget(self.btn_cancel)
        layout.addLayout(hp)
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)

        self.lbl_stats = QLabel("Sin preview.")
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.lbl_stats)

        self.plot = TransectPreview(self)
        layout.addWidget(self.plot, stretch=1)

        bbox = QDialogButtonBox()
        self.btn_apply = QPushButton("Aplicar al DEM")
        self.btn_apply.clicked.connect(self.on_apply)
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        bbox.addButton(self.btn_apply, QDialogButtonBox.ButtonRole.ApplyRole)
        bbox.addButton(btn_close, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(bbox)

    def _scope(self) -> Tuple[int, int, int, int]:
        if self.rb_sel.isChecked() and self._bbox:
            return self._bbox
        nrows, ncols = self._dem.shape
        return 0, nrows - 1, 0, ncols - 1

    def _params(self) -> Dict:
        below = DEFAULT_SMOOTH_BELOW if self.cb_all.isChecked() else float(self.sp_below.value())
        return {"slope_cap": float(self.sp_cap.value()), "smooth_below": below,
                "min_frc": float(self.sp_minfrc.value()),
                "dx": float(self.sp_dx.value()), "dy": float(self.sp_dy.value()),
                "max_iter": int(self.sp_iter.value())}

    def on_preview(self):
        r0, r1, c0, c1 = self._scope()
        p = self._params()
        block = self._dem.get_block(r0, r1, c0, c1)
        self._cancel = False
        self.btn_cancel.setEnabled(True)
        self.btn_prev.setEnabled(False)

        def prog(it, ch):
            self.pbar.setValue(int(100 * it / max(1, p["max_iter"])))
            self.lbl_stats.setText(f"Iter {it}/{p['max_iter']} — cambio {ch:.4f} (umbral 0.05)…")
            QApplication.processEvents()
            return self._cancel

        corr, info = bathy_correction(
            block, dx=p["dx"], dy=p["dy"], slope_cap=p["slope_cap"],
            smooth_below_depth=p["smooth_below"], min_depth_frc=p["min_frc"],
            max_iter=p["max_iter"], progress=prog)
        self.btn_cancel.setEnabled(False)
        self.btn_prev.setEnabled(True)
        self.pbar.setValue(100 if info.get("converged") else 0)
        key = (r0, r1, c0, c1, tuple(sorted(p.items())))
        self._preview = (corr, info, (r0, r1, c0, c1), key)
        status = "converge" if info.get("converged") else ("CANCELADO" if info.get("aborted") else "NO converge (límite iter)")
        self.lbl_stats.setText(
            f"<b>{status}</b> — iter={info['n_iter']} cambio={info['final_change']:.4f}<br>"
            f"• Celdas sobre cap: <b>{info['n_exceed_before']} → {info['n_exceed_after']}</b><br>"
            f"• Pendiente máx: {info['max_slope_before']:.3f} → {info['max_slope_after']:.3f}<br>"
            f"• |Δ| máx: <b>{info['max_abs_change']:.3g}</b> (ámbito [{r0}:{r1}, {c0}:{c1}])"
        )
        self.plot.set_data(block, corr, f"[{r0}:{r1},{c0}:{c1}]")

    def on_apply(self):
        r0, r1, c0, c1 = self._scope()
        p = self._params()
        key = (r0, r1, c0, c1, tuple(sorted(p.items())))
        pre = self._preview[0] if (self._preview and self._preview[3] == key) else None
        self._dem.apply_funwave_correction(
            r0, r1, c0, c1, slope_cap=p["slope_cap"],
            smooth_below_depth=p["smooth_below"], min_depth_frc=p["min_frc"],
            dx=p["dx"], dy=p["dy"], max_iter=p["max_iter"], precomputed=pre)
        self.accept()
