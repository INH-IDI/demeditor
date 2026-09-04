# DEM Editor - Software Científico para Edición de Modelos de Elevación y Batimetría

Software interactivo, minimalista y de alto rendimiento para visualización, inspección y edición de mallas batimétricas y modelos de elevación digital (DEM), especialmente optimizado para **FUNWAVE-TVD**, hidrodinámica y geociencias.

---

## 🚀 Características Principales

1. **Grilla Virtualizada Tipo Excel**:
   - Renderizado ultra-rápido de mallas con cientos de miles o millones de celdas a 60 FPS.
   - Navegación fluida por teclado con las **flechas de dirección**.
   - Edición manual in-situ (doble clic o escribiendo directamente números).
   - Selección continua de bloques de celdas con el ratón o con **Shift + Flechas**.
   - Tecla **Delete / Backspace**: borra la celda o rango seleccionado fijando el valor en blanco (`NaN`). Las celdas `NaN` se resaltan visualmente con un tono sutil rojizo.

2. **Minimapa Global Interactivo (Visor 2D)**:
   - Vista global del DEM completo renderizado como imagen continua.
   - **Marco interactivo (Bounding Box)** en color cian que muestra en tiempo real la región exacta que se está viendo en la grilla.
   - **Navegación bidireccional**: Al moverte o hacer scroll en la tabla, el marco se desplaza; al hacer clic o arrastrar en el minimapa, la grilla salta instantáneamente a esa coordenada.
   - Detección de NaNs: Las celdas vacías (`NaN`) se iluminan en color fucsia brillante para ubicarlas rápidamente en la malla global.
   - Soporte de múltiples mapas de color científicos: *Terrain, Viridis, Plasma, Ocean, Coolwarm, Cividis, Jet, Gray*.

3. **Orientación de Coordenadas**:
   - **Modo FUNWAVE (Fila 0 = Abajo / Sur)**: Respeta la convención donde la fila 0 del archivo corresponde a la esquina inferior ($Y=0$).
   - **Modo Estándar (Fila 0 = Arriba / Norte)**: Convención cartográfica e imagen raster estándar.

4. **Algoritmos de Relleno e Interpolación de NaNs (`Ctrl+I`)**:
   - **Bilineal (Delaunay)**: Relleno continuo basado en triangulación lineal de los nodos válidos adyacentes.
   - **Vecino Más Cercano (Nearest Neighbor)**: Relleno euclidiano ultra-rápido.
   - **Bicúbica (Spline 2D)**: Superficies suaves de orden superior.
   - **Difusión Armónica / Laplace (Inpainting EDP)**: Resuelve la ecuación de Laplace $\nabla^2 Z = 0$ con condiciones de borde Dirichlet. Garantiza la máxima suavidad física sin gradientes artificiales.

5. **Suavizado Espacial de Regiones Seleccionadas (`Ctrl+R`)**:
   - Aplica filtros únicamente sobre la selección: **Gaussiano 2D**, **Media Móvil (Box)** o **Mediana (despiking / remoción de ruido)**.
   - Opcionalmente realiza una transición suave (*blending*) en los bordes de la selección para evitar discontinuidades o escalones respecto al resto del DEM.

6. **Perfil de Corte 1D en Tiempo Real (Cross-Section)**:
   - Gráfico de transecto dinámico bajo el minimapa.
   - Muestra el perfil de elevación/profundidad a lo largo de la fila activa (Transecto X) o columna activa (Transecto Y).
   - Marca la celda activa con un punto amarillo y una línea guía.

7. **Historial Deshacer / Rehacer (`Ctrl+Z` / `Ctrl+Y`)**:
   - Pila completa de deshacer y rehacer para todas las ediciones manuales, borrados, suavizados e interpolaciones.

8. **Formatos de Entrada y Salida (I/O)**:
   - **FUNWAVE ASCII / Matriz Simple** (`.dep`, `.txt`, `.dat`): Detección automática de filas y columnas.
   - **ESRI ASCII Raster** (`.asc`): Lectura y escritura del encabezado estándar (`ncols`, `nrows`, `xllcorner`, `yllcorner`, `cellsize`, `NODATA_value`).
   - **GeoTIFF** (`.tif`, `.tiff`): Soporte geoespacial raster.
   - **NetCDF** (`.nc`): Soporte para mallas NetCDF4.

---

## 💻 Instrucciones de Ejecución

Desde la terminal, puedes iniciar el editor directamente ejecutando:

```bash
python3 main.py
```
o indicando un archivo específico:
```bash
python3 main.py 5x5_malla_moloBatiMod2.dep
```
o simplemente usando el script ejecutable:
```bash
./run_editor.sh 5x5_malla_moloBatiMod2.dep
```

---

## ⌨️ Atajos de Teclado Útiles

| Acción | Atajo |
| :--- | :--- |
| **Navegar celdas** | `Flechas` (Arriba, Abajo, Izquierda, Derecha) |
| **Seleccionar rango** | `Shift + Flechas` o arrastre con ratón |
| **Borrar a NaN** | `Delete` o `Backspace` |
| **Editar celda** | Escribir número directamente o Doble Clic |
| **Deshacer** | `Ctrl + Z` |
| **Rehacer** | `Ctrl + Y` |
| **Interpolar NaNs** | `Ctrl + I` |
| **Suavizar selección** | `Ctrl + R` |
| **Operación matemática** | `Ctrl + M` |
| **Abrir archivo** | `Ctrl + O` |
| **Guardar archivo** | `Ctrl + S` |
| **Guardar como...** | `Ctrl + Shift + S` |
