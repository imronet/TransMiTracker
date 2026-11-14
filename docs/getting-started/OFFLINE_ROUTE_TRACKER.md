# Rastreador experimental offline por ruta

Disponible desde 0.3.0. Procesa una sesión **ya guardada** por `route_id` exacto;
no descarga datos ni activa seguimiento. No exige viaje GTFS exacto ni estabilidad
de `start_time`. El motor conservador 3A mantiene sus reglas sin cambios.

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
