"""dem_editor/core/dem_clipboard.py — copy/paste bloques celdas estilo Excel."""

from typing import Optional, Tuple
import numpy as np

NAN_TOKENS = {"", "nan", "null", "none", "-", "na", "n/a", "nd"}


def _parse_token(tok: str):
    """Retorna (val, ok). ok=False = texto invalido (saltar celda)."""
    s = tok.strip()
    if s.lower() in NAN_TOKENS:
        return np.nan, True
    t = s.replace(" ", "")
    # Soporte decimal coma ES: "3,14" -> 3.14 ; "1.234,56" -> 1234.56
    if "," in t:
        if "." not in t:
            t = t.replace(",", ".")
        else:
            if t.rfind(",") > t.rfind("."):
                t = t.replace(".", "").replace(",", ".")
            else:
                t = t.replace(",", "")
    try:
        return float(t), True
    except ValueError:
        return np.nan, False


def parse_clipboard_text(text: str) -> Tuple[np.ndarray, np.ndarray]:
    """Parsea TSV portapapeles -> (vals float, mask_ok bool). Limpia \r, ignora filas vacias final."""
    if not text or not text.strip():
        return np.zeros((0, 0)), np.zeros((0, 0), dtype=bool)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Quita lineas vacias al final (Excel/Qt agregan \n)
    while lines and lines[-1].strip() == "":
        lines.pop()
    rows = []
    for ln in lines:
        if "\t" in ln:
            cells = ln.split("\t")
        elif ";" in ln:
            cells = ln.split(";")
        else:
            cells = [ln]
        rows.append(cells)
    if not rows:
        return np.zeros((0, 0)), np.zeros((0, 0), dtype=bool)
    ncols = max(len(r) for r in rows)
    vals = np.full((len(rows), ncols), np.nan)
    mask = np.zeros((len(rows), ncols), dtype=bool)
    for i, r in enumerate(rows):
        for j, tok in enumerate(r):
            v, ok = _parse_token(tok)
            if ok:
                vals[i, j] = v
                mask[i, j] = True
            # ok=False -> mask False, celda destino intacta
    return vals, mask


def format_block_for_clipboard(block: np.ndarray) -> str:
    """Bloque 2D -> TSV. NaN/inf -> 'NaN' (roundtrip explicito)."""
    a = np.asarray(block, dtype=np.float64)
    lines = []
    for i in range(a.shape[0]):
        cells = []
        for j in range(a.shape[1]):
            v = a[i, j]
            cells.append("NaN" if not np.isfinite(v) else f"{v:.6g}")
        lines.append("\t".join(cells))
    return "\n".join(lines)


def resolve_paste_shape(src_shape, anchor, sel_shape, data_shape) -> Tuple[int, int, int, int]:
    """Calcula (r0, c0, nrows, ncols) destino recortado a bordes.

    Reglas Excel:
    - src 1x1 + seleccion NxM -> rellena seleccion.
    - src 1xN + seleccion MxN (misma cols) -> repite filas.
    - src Mx1 + seleccion MxN? -> repite columnas.
    - resto -> pega en anchor (celda actual o esq. seleccion), recorta borde.
    Retorna (r0, c0, nr, nc) en coords destino.
    """
    sr, sc = src_shape
    dr, dc = data_shape
    ar, ac = anchor
    if sel_shape is not None:
        selr, selc = sel_shape
        if (sr, sc) == (1, 1) and (selr > 1 or selc > 1):
            return anchor[0], anchor[1], selr, selc
        if sr == 1 and selr > 1 and sc == selc:
            return anchor[0], anchor[1], selr, selc
        if sc == 1 and selc > 1 and sr == selr:
            return anchor[0], anchor[1], selr, selc
    nr = min(sr, dr - ar)
    nc = min(sc, dc - ac)
    return ar, ac, max(0, nr), max(0, nc)


def tile_source(vals: np.ndarray, mask: np.ndarray, nr: int, nc: int):
    """Repite fuente 1x1 / 1xN / Mx1 hasta (nr,nc). Resto: esquina."""
    sr, sc = vals.shape
    out_v = np.full((nr, nc), np.nan)
    out_m = np.zeros((nr, nc), dtype=bool)
    for i in range(nr):
        for j in range(nc):
            si = i if sr > 1 else 0
            sj = j if sc > 1 else 0
            if si < sr and sj < sc:
                # Si fuente es 1 fila -> repite; si multi pero destino mayor -> solo esquina
                if sr == 1 or si < sr:
                    if sc == 1 or sj < sc:
                        out_v[i, j] = vals[si, sj]
                        out_m[i, j] = mask[si, sj]
    return out_v, out_m
