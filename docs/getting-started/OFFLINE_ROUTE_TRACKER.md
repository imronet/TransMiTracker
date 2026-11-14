# Rastreador experimental offline por ruta

Disponible desde 0.3.0. Procesa una sesión **ya guardada** por `route_id` exacto;
no descarga datos ni activa seguimiento. No exige viaje GTFS exacto ni estabilidad
de `start_time`. El motor conservador 3A mantiene sus reglas sin cambios.
Desde **0.4.0** también puede explorarse el reporte con el
[visor gráfico independiente](#visor-gráfico-independiente-040).

## Ejecución manual en PowerShell

Desde la raíz del proyecto, sustituir los valores de ejemplo por rutas locales
y un ID publicado. Conservar el ID como cadena, incluyendo ceros iniciales.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.research.route_tracker `
  data/pilots/SESION/session --route 'ID_EXACTO' `
  --catalog data/catalog/official_20261112.sqlite3 `
  --output data/pilots/RESULTADO_NUEVO/reporte.json
```

La sesión debe contener `session.json`, sus registros y los Protobuf originales.
Se verifica cada hash mediante el lector existente. Un archivo alterado, una ruta
de captura escapada, mezcla sintética/real o entrada incompatible aborta el análisis.
No se reparan originales ni se adquieren sustitutos. El catálogo se abre en lectura.
Sin `--catalog`, se analiza continuidad de coordenadas sin progreso geométrico.
Un catálogo inexistente/inválido produce error; una ruta ausente o sin shape se
declara en `geometry_status`, sin inventar asociaciones ni descargar otro catálogo.

El archivo de salida debe ser nuevo y su ruta resuelta estar dentro de `data/pilots`.
Se rechazan destinos publicables, escapes y sobrescrituras. La consola muestra solo
conteos; el JSON contiene coordenadas e identificadores y debe permanecer privado.
Un checkout público no incluye los datos de la sesión real.

Los errores controlados terminan con código 2 y una categoría estable, sin imprimir
la excepción original, rutas de entrada, IDs ni coordenadas: `OUTPUT_PATH`
(destino privado inválido), `OUTPUT_EXISTS`, `OUTPUT_WRITE`, `CATALOG` (archivo,
consulta o esquema), `INPUT_MISSING`, `INPUT_READ`, `INPUT_JSON`, `INPUT_ENCODING`,
`INPUT_INTEGRITY` (hash PB) e `INPUT_INVALID` (estructura/contenido incompatible).
No se adquieren datos ni se reintenta para resolver esos errores.

## Ejemplo real conservado

La selección privada corresponde a la ruta de la mediana S01 del diagnóstico
geométrico previo. Para repetir **solo el análisis offline**, elegir una salida
nueva; no ejecutar comandos históricos de captura:

```powershell
$exampleRoot = 'data/pilots/first-real-20261113-223641-1613d2b6/route-tracker-20261114'
$selection = Get-Content "$exampleRoot/selection.json" -Raw | ConvertFrom-Json
.\.venv\Scripts\python.exe -m transmitracker.research.route_tracker `
  $selection.session --route $selection.route_id --catalog $selection.catalog `
  --output "$exampleRoot/reproduccion-NUEVA.json"
```

`report.json` y `replay.json` ya existen y no se deben sobrescribir. La receta
privada `summarize_example.py` explica la exportación por lista permitida y el
contraste con S01; su destino público también es exclusivo. Véanse los
[resultados y evidencia](../archive/phases/PHASE3B_ROUTE_TRACKER_REPORT.md).

## Interpretación del reporte

- Agrupa por `(source, vehicle_id)` dentro de la ruta exacta. El ID es candidato,
  sin prueba de identidad física permanente. Conserva todos los originales,
  timestamps de recepción/feed/GPS, hashes y observaciones de otras rutas del
  mismo candidato para detectar cambios de ruta.
- Mantiene el orden de capturas. Cada segmento tiene timestamps GPS estrictamente
  crecientes; un retroceso corta la época antes de continuar. No ordena globalmente
  observaciones antiguas para ocultar el retroceso.
- Deduplica `(route_id, timestamp GPS, latitud, longitud)` por candidato. Un timestamp
  repetido no crea movimiento nuevo. Coordenadas distintas con el mismo timestamp
  se rechazan, sin escoger una. Una repetición tras una ausencia no reinicia movimiento.
- `distinct_published_gps_times` cuenta timestamps distintos por candidato y se
  suma entre candidatos; no son timestamps únicos globales ni posiciones aceptadas.
  `temporal_exact_duplicate_sightings` mide todas las repeticiones; el contador
  `duplicates_removed_from_movement` corresponde a las retiradas en esa etapa,
  después de validar campos/frescura. No tienen que coincidir en entradas obsoletas.
- `auxiliary_changes` registra cambios de viaje, `start_time`, fecha de inicio,
  parada y secuencia; permanecen en el original. No son condiciones de continuidad.
- Los candidatos geométricos se consultan por ruta exacta, agrupados por shape.
  Cada proyección conserva todos los patrones del shape. Varias geometrías viables
  o ramas sin resolver producen ambigüedad; no se escoge la más conveniente.
  No se utilizan paradas auxiliares como anclas ni se valida servicio/calendario.

Cada segmento contiene soporte, timestamps extremos, cambios de coordenadas,
distancia entre muestras, progreso neto sobre shape cuando puede determinarse y
motivos de inicio/final. Distancia muestreada y progreso geométrico son magnitudes
distintas; no son una medida de precisión ni duración.

| Estado | Significado experimental |
| --- | --- |
| `movimiento_candidato` | Dos o más muestras con progreso neto >10 m; sin geometría, distancia muestreada >8 m |
| `estacionario` | Dos o más muestras sin superar ese criterio; no demuestra detención ni permanencia en parada |
| `interrumpido` | Segmento con al menos dos muestras cerrado por discontinuidad; `activity_candidate` conserva la actividad previa |
| `ambiguo` | Observación con proyección no resoluble; no se enlaza |
| `descartado` | Observación rechazada o segmento de una sola muestra, insuficiente para movimiento |

`pattern_ambiguous` es independiente del estado: puede existir movimiento sobre un
shape compartido por varios patrones, sin resolver cuál corresponde al servicio.
Los conflictos de múltiples estados del mismo candidato en un snapshot se guardan
como incidentes y originales, sin seleccionar un representante para enlazar.

## Límites utilizados

Reutiliza distancias/proyección y parámetros existentes: frescura máxima 300 s,
adelanto tolerado 5 s, hueco máximo **300 s** (del diagnóstico real previo),
velocidad máxima 35 m/s, residual máximo 60 m, empate de proyección 5 m,
separación de ramas 30 m, retroceso tolerado 10 m y error GPS 8 m.
El reporte guarda el conjunto `Parameters`; solo estos campos intervienen aquí.
Los parámetros de cruces, permanencia y duración de 3A no se aplican.

Cambio de ruta, ausencia en un snapshot completo, regresión, hueco, salto,
cambio de shape y ambigüedad cortan enlaces. Un salto espacial incompatible
descarta la observación y rompe continuidad; no se puentea hasta la anterior.
Son controles exploratorios, sin garantías operativas. El reporte declara
`operationally_verified=false` y ninguna llegada, embarque o duración inferida.

No hay scheduler, captura, Croma, predictor ni integración nueva en la GUI.

## Visor gráfico independiente (0.4.0)

Ventana CustomTkinter con Canvas local, separada de la GUI principal. No requiere
mapas web, claves ni dependencias adicionales. Ejemplo completamente sintético:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.viewer --demo
```

Para abrir el reporte real privado **existente** con el catálogo local:

```powershell
$exampleRoot = 'data/pilots/first-real-20261113-223641-1613d2b6/route-tracker-20261114'
.\.venv\Scripts\python.exe -m transmitracker.viewer `
  "$exampleRoot/report.json" --catalog data/catalog/official_20261112.sqlite3
```

Sin argumentos se abre una ventana vacía: **Abrir reporte privado** permite elegir
el JSON y **Catálogo local…**, un SQLite. Sin catálogo se muestran solo los GPS;
no se inventa un trazado. Si el reporte fija un catálogo, se compara el hash GTFS
registrado en sus metadatos; otra versión se rechaza. Esto no verifica por sí solo
la integridad física del SQLite. El catálogo siempre se abre en modo lectura.

Seleccionar un candidato por ID/fuente y un segmento en el panel izquierdo.
**Anterior**, **Siguiente** y el deslizador recorren observaciones originales por
orden de captura, incluyendo repeticiones y regresiones GPS; no son reproducción
animada ni una escala de tiempo interpolada. Seleccionar un segmento lleva a su
primera observación. El aro blanco marca la observación actual. Los timestamps
del panel (GPS, recepción y feed) se presentan en America/Bogota.

Los puntos de color son GPS observados. Las uniones punteadas son ayudas de lectura
entre muestras del **mismo segmento**; no son posiciones intermedias ni cruzan
interrupciones. Gris identifica observaciones sin segmento. Las posiciones
ausentes, inválidas o declaradas extrapoladas no se dibujan como GPS observado.
Los colores distinguen movimiento candidato, bajo movimiento, interrupción,
ambigüedad y descarte. Las métricas del panel corresponden al **segmento completo**,
no solo al prefijo visible del control temporal.

Los trazados grises son todos los shapes utilizables de la ruta, sin selección
arbitraria. El panel conserva patrones compartidos y alternativas/motivos de
proyección del reporte; no recalcula correspondencias ni resuelve ramas. Usar
**Encuadrar GPS**, **Ruta completa**, zoom o arrastre para explorar el dibujo.
La proyección local sirve para dibujar; no estima precisión ni nuevas distancias.

El visor valida formato y consistencia de los segmentos, pero confía en los datos
y métricas del reporte local; no vuelve a verificar los PB ni ejecuta el rastreador.
No escribe reportes, preferencias o exportaciones. Los IDs y posiciones son
visibles únicamente en la ventana privada: no compartir capturas reales.
Un reporte inválido produce un mensaje seguro; al abrir desde la ventana se
conserva la vista anterior. Si Tk no puede iniciarse, la CLI termina con error.

### Validación de entrega — 2026-11-14

**44 pruebas focalizadas aprobadas**, incluida una prueba con ventana Tk real,
las 25 pruebas del rastreador y el contrato de versión. Ruff y formato correctos
en los siete archivos Python nuevos; `pip check` correcto en Python 3.13.
Sin suite completa ni cambios de reglas del rastreador, motor 3A, GUI principal,
perfiles o catálogo. La versión de producto aumenta a 0.4.0 por esta capacidad
compatible; el algoritmo del rastreador conserva su versión.

Se abrió la demostración sintética y se comprobó selección, slider, cortes y
ambigüedad en widgets reales. Luego se abrió el reporte privado: **3 candidatos,
36 observaciones recorridas, 10 segmentos y un shape**; reporte y SQLite sin
cambios de hash, cero errores de callbacks y red bloqueada. Esto prueba lectura
y visualización, sin identidad operativa, llegadas, duraciones o ETA verificadas.

[Captura exclusivamente sintética](../archive/phases/screenshots/offline-viewer-synthetic-20261114.png)
y [evidencia de pruebas y comprobaciones](../archive/evidence/OFFLINE_VIEWER_VALIDATION_20261114.json).
Las fuentes están en `src/transmitracker/viewer/`; preparación de datos en `data.py`,
widgets en `app.py`, demo en `demo.py` y entrada independiente en `__main__.py`.
Los tests nuevos son `tests/test_viewer.py` y `tests/test_viewer_widgets.py`.
Quedan fuera de alcance mapas geográficos de fondo, grandes lotes de producción,
identidad permanente, nuevos análisis y adquisición. Entrega preparada para QA;
ningún commit/push ni autorización de la siguiente capacidad.
