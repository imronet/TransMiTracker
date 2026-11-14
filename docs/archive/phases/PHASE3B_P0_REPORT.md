# Fase 3B-P0 — Preparación local de piloto GPS

Entrega **2026-11-13, America/Bogota**, referencia de producto **0.2.0**.
Alcance autorizado: herramienta y pruebas offline; **cero capturas GPS reales**.
No se entrega un colector de producción ni validación de tiempos de viaje.

## Resultado ejecutivo

Se implementó una CLI manual con plan offline predeterminado, generación de una
sesión explícitamente sintética, captura acotada preparada y analizador offline.
La captura real permanece deshabilitada incluso con confirmación: las condiciones
públicas no resuelven suficientemente el sondeo y almacenamiento local. Esto no
afirma una prohibición universal del feed ni exige certificación operacional
para un prototipo doméstico; conserva el bloqueo solicitado para una incertidumbre
material. No se contactaron proveedores ni se consumieron créditos.

## Archivos y reutilización

| Archivo | Cambio |
| --- | --- |
| src/transmitracker/research/local_pilot.py | CLI y sesión aislada, persistencia PB/JSON, análisis conservador |
| tests/test_local_pilot.py | 22 casos offline, incluidos parámetros, HTTP simulado y reproducción |
| docs/getting-started/LOCAL_GPS_PILOT.md | Instrucciones Windows, flags, semántica de datos y captura futura |
| Este informe y tres JSON de evidencia | Validación, revisión final y ejemplo sintético, sin renovar resultados anteriores |
| README, INDEX y adenda del plan | Capacidad de preparación offline y límite de autorización |

Se reutilizan `providers.http.download` con attempts=1 y límites de bytes,
`research.temporal.capture_record` para procedencia/observaciones y su lector
`gtfs.realtime.decode_realtime`, `distance_m` para distancias, y `project_path`
para mantener rutas CLI dentro del proyecto. No se modifica ninguno de ellos.
El wrapper local conserva current_status ausente como None, evitando presentar
el valor predeterminado Protobuf como estado publicado. No se duplicó el decoder.

La herramienta 1B anterior se inspeccionó, pero no cumple el nuevo alcance: admite
16 capturas, fija endpoint y depende del catálogo para analizar. No se altera esa
herramienta histórica ni se cambian sus contratos; P0 es un diagnóstico separado
que comparte las primitivas existentes. No se toca reconstruction/, GUI, perfiles,
catálogos ni SQLite. Sin dependencias nuevas; no se corta una versión de producto.

## Captura y controles

- El comando sin argumentos solo imprime un plan con network_requests=0.
- `capture` requiere --confirm-real-capture y el gate revisado NETWORK_ALLOWED.
  Este último está false y no se puede sobreescribir mediante argumentos CLI.
  Se comprueba antes de crear directorio o cliente HTTP.
- Hasta 12 posiciones, intervalo entero >=60 s, una sola sesión por proceso;
  una consulta adicional al manifiesto, sin concurrencia ni reintentos.
- El manifiesto determina el endpoint y debe anunciar una única positions.pb
  disponible, exactamente `https://gtfs.transmilenio.gov.co/positions.pb`.
  Si cambia, no se siguen URLs arbitrarias y se requiere revisión. La frecuencia
  publicada no implica permiso de sondeo.
- Capturas solo en un directorio nuevo bajo data/pilots; archivos exclusivos y
  outputs sin sobrescritura. Todo data/ está excluido de Git.
- Descarga secuencial HTTPS sin redirects, TLS no desactivado, máximo 64 KiB/8 MiB.
  Timeout y presupuesto se describen en la guía, sin prometer deadline absoluto.
- Cualquier fallo o PB rechazado detiene la sesión. También tres snapshots sin
  timestamps GPS nuevos de IDs candidatos/rutas seleccionadas. El primer snapshot
  no vacío cuenta como novedad; tres repeticiones después paran en la cuarta
  descarga. Con cero vehículos relevantes, tres vacíos paran en la tercera.
- Se guarda session.json incluso ante errores de red y cada PB descargado se
  conserva con su registro, aunque el decoder lo rechace. Una descarga fallida
  registra estado/error en session.json; no fabrica un PB exitoso ni una recepción.

La persistencia incluye payload y SHA-256, recepción UTC al terminar el cuerpo,
solicitud HTTP separada, feed.timestamp, timestamps de vehículos, ID de captura,
origen, source, parámetros/contadores de sesión y metadatos de descarga. El ID
individual es capture_NN dentro del namespace de la sesión. No hay secretos ni
placas reales en los archivos versionados de esta entrega.

## Diagnóstico y límites de interpretación

Se redecodifican los PB verificados por hash; el JSON derivado previo no se toma
como verdad. Se rechaza mezcla real/sintética y rutas de archivos fuera de sesión.
La salida es determinista para mismos archivos, filtros y umbrales; no usa reloj
actual ni hace red. Tiempos de fixtures son ficticios fijos de 2027.

Reporta snapshots decodificables/rechazados, observaciones, campos presentes y
ausentes, edades respecto a recepción, novedad GPS por snapshot, repeticiones,
IDs candidatos en tres instantes distintos, reapariciones y pares espaciales.
IDs nulos o duplicados en un snapshot no se enlazan. Distingue observación,
candidato plausible y no determinable. Ningún resultado acredita llegada,
embarque, espera ni duración de viaje. No se invoca el gate sintético del motor 3A.

El filtro de una/dos rutas es igualdad literal del route_id publicado. No hay
crosswalk GTFS y se informa esa limitación. Una ausencia no confirma llegada o
desaparición. Un mismo timestamp con posición diferente es conflicto, no novedad.
Un ID con tres tiempos puede ser reciclado: sigue siendo candidato. Las coordenadas
inválidas causan rechazo del snapshot completo por la validación reutilizada,
no recuperación parcial. No se aseguran completitud de flota ni identidad operativa.

Umbrales: reciente <120 s, retrasado 120–300 inclusive, antiguo >300 s;
futuro/ausente aparte, configurables por --recent/--delayed. Velocidad media
candidata <=35 m/s y hueco <=300 s son diagnósticos exploratorios, no calibración.

## Condiciones y endpoint: verificado y pendiente

Lectura de repositorio: README, política documental, plan/adendas, informe de
viabilidad GPS y contratos 3A. El [manifiesto público conservado](../../research/evidence/GPS_FEASIBILITY_20261113_PUBLIC_HTTP.json)
se obtuvo durante la investigación del mismo día, no mediante una captura nueva
en P0. Anuncia el endpoint revisado. El navegador de esta tarea no pudo consultar
directamente [manifest.json](https://gtfs.transmilenio.gov.co/manifest.json);
por ello no se afirma una revalidación HTTP actual del PB. Antes de una sesión
futura habilitada se comprobará con el GET al manifiesto que implementa la herramienta.

Se volvió a consultar documentalmente el 2026-11-13 la página pública de
[términos web de TMSA](https://www.transmilenio.gov.co/comunicaciones/publicaciones/2025/terminos-y-condiciones-en-el-sitio-web-de-transmilenio).
Sus restricciones generales sobre reutilización de contenidos no aclaran una
licencia específica de sondeo/retención del host GTFS. No se encontró una regla
pública inspeccionada que resuelva ese punto para estas 12 consultas y archivo
doméstico. Es incertidumbre de aplicabilidad, no prueba de denegación concreta.
La noticia de apertura y el manifiesto no se interpretan como autorización ilimitada.

Se documenta el bloqueo sin imponer a P0 los requisitos de producción del informe
previo: no exigimos SLA, muestra estadística, identidad verificada o ground truth
antes de explorar novedades. Solo queda pendiente resolver condiciones aplicables
y autorización posterior de ejecución; no se envían consultas a terceros automáticamente.

## Pruebas y evidencia

Se ejecutaron **139 pruebas offline**, 22 nuevas y 117 regresiones pertinentes,
en **25,51 s**. Incluyen HTTP/Protobuf, temporal, snapshots, motor 3A y su almacén.
Ruff check y formato global correctos (110 archivos); pip check sin conflictos.
No se ejecutó suite completa ni ventanas GUI: sus componentes no se modificaron.
Los 237 casos anteriores se conservan; no se afirma haberlos reejecutado todos.

[Validación](../evidence/PHASE3B_P0_VALIDATION_20261113.json).
Tras añadir el rechazo de recepción no verificada se repitieron los 22 tests
del piloto: **22 aprobados en 0,46 s**, Ruff y formato correctos (112 archivos).
La [revisión final](../evidence/PHASE3B_P0_FINAL_20261113.json) conserva ese
resultado, 43 enlaces locales comprobados y 45 evidencias históricas con hashes
idénticos. No se sobrescribió el primer registro de validación. Un registro antiguo
sin recepción verificada no se utiliza para deducir antigüedad GPS.
HTTP en pruebas usa httpx.MockTransport con reloj/sleep simulados y el bloqueo
de red autouse existente; no hubo esperas de diez minutos ni solicitudes reales.
Se cubren confirmación/gate, máximo de peticiones, separación de inicios,
sesión única, límite de tamaño, timeout, estados 401/403/429/5xx/redirect,
decode error, hash adulterado, paths inválidos, replay determinista, duplicados,
campos ausentes, estado Protobuf no publicado, filtros y fronteras de recencia.

El [ejemplo sintético](../evidence/PHASE3B_P0_SYNTHETIC_20261113.json) se generó
con `fixture` y `analyze`, sin descarga. Resultado: cuatro snapshots decodificables,
cuatro observaciones, un timestamp repetido, tres instantes distintos del ID DEMO,
dos desplazamientos candidatos (~66 m en 60 s cada uno), cero validación operativa.
Las antigüedades simuladas son 5, 5, 65 y 65 s. Son observaciones fabricadas para
pruebas, no una muestra de buses reales. El PB original del ejemplo permanece
local en data/pilots/p0-synthetic-20261113, no versionado; el comando fixture permite
reproducirlo. No se modificaron las capturas de investigaciones previas.

Comandos de comprobación (PowerShell, PYTHONPATH=src):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_local_pilot.py tests/test_http.py tests/test_realtime.py tests/test_temporal_diagnostic.py tests/test_reconstruction.py tests/test_reconstruction_store.py tests/test_snapshots.py -q --basetemp=.cache/pilot-p0-NUEVO
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
```

## Ejecución posterior y cierre

La [guía Windows](../../getting-started/LOCAL_GPS_PILOT.md) contiene el comando
de una sesión real futura, hoy bloqueado aun con confirmación. Resolver la revisión
de condiciones con evidencia y aprobar la ejecución son pasos separados de esta
preparación. No hay flag de bypass, cliente Croma ni mantenimiento eludido.

Preparación offline entregada; resultado real todavía desconocido. No se ha
descargado ninguna posición real en esta tarea, no se modificaron reglas de
confianza/duración, bases existentes, dependencias, GUI o perfiles, ni se hicieron
commits/push. La autorización de captura real y cualquier ampliación de 3B queda
pendiente del propietario.
