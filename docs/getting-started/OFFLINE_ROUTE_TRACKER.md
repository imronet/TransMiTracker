# Rastreador experimental offline por ruta

Disponible desde 0.3.0. Procesa una sesión **ya guardada** por `route_id` exacto;
no descarga datos ni activa seguimiento. No exige viaje GTFS exacto ni estabilidad
de `start_time`. El motor conservador 3A mantiene sus reglas sin cambios.
Desde **0.4.0** también puede explorarse el reporte con el
[visor gráfico independiente](#visor-gráfico-independiente-040).
Desde **0.5.0** incluye [análisis experimental origen–destino](#análisis-experimental-origendestino-050)
sobre sus segmentos, sin convertir tiempos candidatos en mediciones operativas.

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

Para cambiar entre sesiones con diferentes versiones de catálogo, usar
**Abrir reporte y catálogo** (desde 0.4.1). Elegir primero el reporte y después
su catálogo: se valida el conjunto con las mismas comprobaciones de formato y
hash. Solo al aceptar ambos se sustituyen las rutas de archivos, geometrías y
candidatos; selección, deslizador y encuadre vuelven al inicio. Si se cancela
cualquiera de los diálogos o falla la validación, se conserva el par y la vista
anteriores. Los errores se muestran sin sustituir el catálogo automáticamente.
Las acciones individuales siguen usando el catálogo/reporte ya abierto; en una
ventana sin catálogo, **Abrir reporte privado** conserva el modo de solo GPS.

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

**Corrección 0.4.1:** 28 pruebas focalizadas aprobadas (17 de preparación de datos,
10 con ventanas Tk reales y una de versión); Ruff y formato correctos en los dos
archivos Python modificados. Los nuevos casos usan exclusivamente reportes y
SQLite sintéticos: cambio A → B con hashes diferentes, rechazo B/A, archivos
ausentes/JSON inválido, cancelación de ambos diálogos, conservación de la escena,
reinicio de controles/dibujo y sesiones vacías. Sin suite completa, red, GPS real,
dependencias nuevas ni cambios en `viewer.data.load()`, rastreador o motor 3A.
PATCH preparado para QA; sin commit ni push en esta corrección.

Validación original de **0.4.0**, conservada como contexto:

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

## Análisis experimental origen–destino (0.5.0)

CLI independiente `research.od_analyzer`: lee un reporte del rastreador ya guardado
y un catálogo local en modo lectura. Requiere coincidencia de ruta y del hash GTFS
fijado en el reporte; un catálogo ausente, diferente o no fijado se rechaza. La
compatibilidad por metadatos no certifica por sí sola la integridad física del DB.
No decodifica de nuevo los PB ni cambia las decisiones del rastreador o de 3A.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.research.od_analyzer `
  data/pilots/SESION/reporte-ruta.json --catalog data/catalog/CATALOGO.sqlite3 `
  --route 'ID_RUTA' --pattern 'ID_PATRON' `
  --origin 'ID_PARADA_ORIGEN' --origin-sequence 10 `
  --destination 'ID_PARADA_DESTINO' --destination-sequence 20 `
  --output data/pilots/RESULTADO_NUEVO/tramo.json
```

Los IDs permanecen como cadenas. Si una parada se repite, su secuencia es obligatoria;
si tiene una sola ocurrencia, puede omitirse. El destino debe ser posterior y
ambos extremos deben cumplir `Leg` y `Catalog.validate_leg_structure`, sin remapeo
de plataformas ni selección por proximidad. `--pattern` solo puede omitirse cuando
la ruta tiene exactamente un patrón. La selección es una **hipótesis explícita**,
sin prueba de que un candidato estuviera realizando ese servicio o calendario.

La geometría y anclas se obtienen con `GeometryCatalog`. El viaje GTFS registrado
como plantilla sirve exclusivamente para construir el patrón estático; no es una
correspondencia con el `trip_id` Realtime. Si las plantillas del mismo patrón tienen
distintas anotaciones `shape_distance`, el análisis queda indeterminado. Se conservan
los cambios de viaje, start_time, fecha, parada y secuencia como evidencia auxiliar;
no se utilizan esos campos para fabricar continuidad o resolver ramas GPS.

Se procesan solo los segmentos existentes. No se unen cortes, no se rehabilitan
segmentos ambiguos/descartados y no se eliminan puntos problemáticos para puentearlos.
La proyección reutiliza `select_projection`, con soporte de continuidad observada
y sin anclas tomadas de las referencias de parada Realtime. Un segmento con salto,
retroceso incompatible, mala frescura, hueco excesivo o rama sin resolver se rechaza.

Los cruces reutilizan `crossing_events`: requieren soporte anterior y posterior a
la banda de error GPS, con IDs/procedencia e intervalo temporal. Cercanía, una sola
observación o un timestamp repetido no prueban un cruce. Se conservan los parámetros
3A: hueco máximo 120 s (más estricto que los 300 s del rastreador), residual 60 m,
retroceso tolerado 10 m, velocidad 35 m/s, error GPS 8 m y timestamp ±1 s.
También se limita a 120 s el intervalo entre soportes extremos de cada cruce.
Solo se conserva una estimación puntual si 3A la justifica por velocidad estable
y separación de hasta 40 s; no se sustituye por un punto medio.

`measure` calcula límites usando ambos cruces del mismo segmento y las ocurrencias
seleccionadas. Esta CLI exige además intervalos de extremos temporalmente separados
(`origen.latest < destino.earliest`). Si se solapan, no propone duración. La
incertidumbre máxima admisible conserva el límite de 85 s de 3A: un rango más amplio
puede quedar registrado para diagnóstico con estado `indeterminate`, sin contar como
duración candidata. No se reducen los rangos para obtener una cifra más precisa.

Estados: `candidate_crossing` para cruce candidato con soporte; `no_evidence` o
`rejected` para los demás cruces; `candidate_interval`, `indeterminate` o `rejected`
para segmentos. Un intervalo candidato no implica aceptación conservadora/operativa:
**incluso en fixtures se usa `Confidence.CANDIDATE`, nunca una identidad sintética
que autorice tiempos reales**. Se conservan las razones de no aceptación de 3A.
No se generan llegadas, embarques, esperas, caminatas ni ETA.

El JSON completo contiene el tramo, plantilla estática, parámetros/huellas,
procedencia del reporte, segmentos, soporte original, proyecciones, eventos,
intervalos y razones. Solo admite archivos nuevos bajo `data/pilots`, sin
sobrescritura. La consola muestra agregados; los errores no imprimen IDs o GPS.

### Entrega OD — 2026-11-14

**115 pruebas pertinentes aprobadas en 26,26 s**, incluidas 18 nuevas sintéticas,
las 54 de reconstrucción/almacenamiento, 25 del rastreador, 17 de preparación del
visor y el contrato de versión. Ruff, formato y `pip check` correctos con Python
3.13. Sin suite completa ni ventanas GUI. Código nuevo en
`src/transmitracker/research/od_analyzer.py`; pruebas en `tests/test_od_analyzer.py`.
Producto 0.5.0 (capacidad compatible), algoritmo `od-candidate-offline-0.1.0`;
sin dependencias o esquemas SQLite nuevos.

Ejercicio real: se fijaron por separado **dos hipótesis de patrón** de la ruta
ya estudiada. Para cada una se tomó la primera pareja consecutiva de paradas
embarcable/desembarcable dentro del rango proyectado de un segmento móvil, sin
optimizar después para obtener duración. Cada hipótesis examinó los mismos
**3 candidatos y 10 segmentos**: dos cruces candidatos, cero intervalos admisibles.
Los dos cruces comparten soporte y sus ventanas de 122 s se solapan; no hay orden
temporal suficientemente acotado y se supera la incertidumbre permitida. Otros
segmentos: cinco ambiguos, uno descartado y tres sin ambos extremos. Son hipótesis
sobre los mismos datos, no cuatro cruces independientes ni un servicio identificado.
La repetición de la primera salida fue idéntica byte a byte. No se relajaron filtros.

Selecciones y resultados privados nuevos:
`data/pilots/first-real-20261113-223641-1613d2b6/od-analysis-20261114/`.
Incluye `selection-0.json`, `selection-1.json`, `result-0.json`, `result-1.json`,
`replay-0.json`, `input-integrity.json` y la receta local `prepare_example.py`.
Para repetir offline con un destino **nuevo**:

```powershell
$folder = 'data/pilots/first-real-20261113-223641-1613d2b6/od-analysis-20261114'
$s = Get-Content "$folder/selection-0.json" -Raw | ConvertFrom-Json
.\.venv\Scripts\python.exe -m transmitracker.research.od_analyzer `
  $s.report --catalog $s.catalog --route $s.route --pattern $s.pattern `
  --origin $s.origin --origin-sequence $s.origin_sequence `
  --destination $s.destination --destination-sequence $s.destination_sequence `
  --output "$folder/reproduccion-NUEVA.json"
```

[Evidencia QA y agregados no identificables](../archive/evidence/OD_ANALYZER_VALIDATION_20261114.json).
Los originales y análisis previos se conservan. Entrega lista para revisión del
propietario; no habilita otra captura, predicción, GUI o siguiente capacidad.
Sin red, Croma, modificaciones al motor 3A/rastreador, commit ni push.
