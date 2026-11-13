# TransMiTracker v0.2.0

Aplicación Python para analizar tiempos de viaje de TransMilenio/SITP.
Se entregaron las **Fases 0, 0.5, 1A, 1B, 2 y 2.1 (QA y recorridos habituales)**.
La **Fase 3A** añade un motor GPS exclusivamente offline, separado de la GUI.
La validación temporal de identidades Realtime reales sigue pendiente de evidencia.
No hay tracking continuo, predicción ni envío de Telegram. La Fase 3B requiere autorización.

El [plan completo](docs/IMPLEMENTATION_PLAN.md) conserva los requisitos recibidos,
con rutas adaptadas a `src/transmitracker/`.

## Reconstrucción GPS offline — Fase 3A

El [informe y matriz de Fase 3A](docs/PHASE3A_REPORT.md) separa resultados
sintéticos de parsing de capturas reales antiguas. El motor valida tiempos,
IDs y geometría, segmenta discontinuidades, estima pasos con intervalos y calcula
duraciones cuando ambos extremos tienen evidencia suficiente. No genera GPS
extrapolado, llegadas confirmadas ni ETA. Las mediciones reales permanecen sin
verificación operativa; las identidades sintéticas llevan una etiqueta específica.

Desde la raíz del proyecto, con `.venv` existente:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
# Catálogo y verdad sintéticos; comparación a 20, 40 y 90 segundos:
.\.venv\Scripts\python.exe -m transmitracker.reconstruction evaluate --directory data/phase3a/final
# Replay sintético individual:
.\.venv\Scripts\python.exe -m transmitracker.reconstruction replay --catalog data/phase3a/final/fixtures/synthetic_catalog_v1.sqlite3 --scenario normal --gap 40 --db data/phase3a/offline.sqlite3
# Captura real antigua guardada: no hace ninguna descarga nueva:
.\.venv\Scripts\python.exe -m transmitracker.reconstruction replay --catalog data/catalog/official_20261112.sqlite3 --capture data/phase1b/saved_original/capture.json --db data/phase3a/real_saved_reconstruction.sqlite3 --output docs/PHASE3A_REAL_SAVED_REPLAY.json
```

El almacén GPS es nuevo y separado de catálogo/perfiles. Guarda originales,
normalización, segmentos, eventos, mediciones, rechazos, versión/huella del algoritmo
y parámetros. Repetir la misma ejecución reutiliza resultados; cambiar parámetros,
versión o código conserva una ejecución nueva y la procedencia anterior.
Un `--parameters archivo.json` permite modificar umbrales; son candidatos sin
calibración operativa. La CLI solo admite rutas dentro del proyecto.

Para usar perfiles estructurales, añada `--profiles-db data/gui/profiles.sqlite3
--profile-id ID` o `--profile-json archivo.json` al replay. La lectura de perfiles
es explícita, en modo SQLite de solo lectura y sin migrarlos; debe coincidir el
hash de catálogo y las ocurrencias. Abrir la GUI o un perfil no ejecuta el motor.

La [especificación de Croma y créditos](docs/CROMA_INTEGRATION_DESIGN.md) es un
diseño e interfaces para una fase futura. No hay cliente Croma ni consumo de créditos.

## Abrir la GUI

Desde la raíz de TransMiTracker, en PowerShell:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.gui
```

Requiere el entorno instalado con `requirements-lock.txt`, incluido CustomTkinter
6.0.0, y Tkinter (comprobado con Python 3.13.14 / Tk 8.6 en Windows). La aplicación
usa tema oscuro inicial, permite tema claro y no hace consultas HTTP al iniciar.
El [informe de Fase 2.1](docs/PHASE2_1_REPORT.md) detalla las correcciones y pruebas.
El [informe histórico de Fase 2](docs/PHASE2_REPORT.md) se conserva.

Configure de uno a tres tramos **sin indicar una fecha ni una salida ficticia**.
En cada tramo puede elegir **Origen primero** (origen → ruta → patrón → destino)
o **Ruta primero** (número/nombre de ruta → patrón → origen → destino). Cambiar de
modalidad conserva las selecciones compatibles. Añadir o eliminar tramos conserva
las selecciones y textos de los restantes; los errores tampoco limpian el formulario.

Casa → Trabajo requiere hora límite de llegada al trabajo y días activos.
Trabajo → Casa admite una salida habitual opcional y no exige hora de llegada.
Configure caminatas, transbordos, tolerancias y margen, y pulse **Guardar perfil**.
Se valida la integridad estructural del recorrido, sin exigir servicio en una fecha.
Si falta completar campos, use **Guardar borrador** y retómelo al volver a abrir.
Los borradores no reemplazan el último perfil configurado.

**Consultar horario programado** es una herramienta opcional: solo allí se indica
fecha y salida de consulta. Respeta America/Bogota y calendario GTFS. Un error o
ausencia de horarios no elimina ni impide guardar un recorrido estructuralmente
válido. El límite de llegada se comprueba temporalmente solo para Casa → Trabajo.
En opciones avanzadas, el **Horizonte de búsqueda de buses programados** limita
esa consulta; no es una estimación histórica del tiempo de espera.

Las horas consultadas son **programadas**, no predicciones. Las horas límite y
habituales son preferencias del usuario. No se fabrican duración o llegada a casa
cuando faltan datos. El aviso se configura pero no se
envía. Los transbordos conservan la caminata indicada y advierten que la conexión
espacial no está verificada. El `direction_id` ausente sigue siendo desconocido.

Los perfiles se guardan en `data/gui/profiles.sqlite3`, separados del catálogo;
las preferencias en `data/gui/settings.json`. Los secretos opcionales se guardan
solo en `.env`, con campos enmascarados: **el archivo no está cifrado**. Todo queda
dentro del proyecto y excluido de Git. Las preferencias de intervalos y avisos no
activan recolección, Telegram ni Croma; los controles futuros están deshabilitados.
El almacén migra de esquema 1 a 2 añadiendo tablas de borradores y consultas, sin
reescribir los perfiles ni su historial. Un cambio explícito de catálogo conserva
los perfiles asociados a la versión anterior y muestra el aviso de migración.

Ejemplo técnico con el catálogo real, separado de sus perfiles personales:

```powershell
.\.venv\Scripts\python.exe scripts/demo_phase2_1.py
.\.venv\Scripts\python.exe -m transmitracker.gui --qa-demo
```

Usa `data/phase2_1/demo` y selecciones publicadas de Portal Norte, sin fecha ni
salida de ejemplo. No representa su recorrido personal ni un estado real en vivo.
La demo verifica perfiles de tres y un tramos, guardado/recuperación y catálogo
sin cambios. La demo anterior permanece disponible mediante `--demo`.

Consulte la [guía de uso](docs/USAGE.md) para catálogo, credenciales y estados,
y la [política de versiones](docs/VERSIONING.md). La única fuente de versión
es `pyproject.toml`; README refleja la versión de esta entrega.

```powershell
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE3A_VALIDATION_RESULTS.json
# Solo ventanas Tk reales:
.\.venv\Scripts\python.exe -m pytest -m gui -q
# Servicios y controladores sin ventanas:
.\.venv\Scripts\python.exe -m pytest -m 'not gui' -q
```

## Fase 1B: perfiles y diagnóstico temporal

El [informe de Fase 1B](docs/PHASE1B_REPORT.md) documenta los contratos tipados
independientes de GUI, los perfiles Casa → Trabajo y Trabajo → Casa de uno a tres
tramos, validación de calendario/horarios y persistencia en SQLite separado.
Cada perfil conserva el hash de su catálogo. Activar otra versión no cambia
referencias guardadas; migrarlas exige una propuesta, revalidación y revisión
esperada. Los tiempos de caminata del usuario se conservan y todo transbordo
advierte que su conexión espacial no está verificada.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/demo_phase1b.py
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE1B_VALIDATION_RESULTS.json
```

La demo es offline y crea perfiles técnicos con el catálogo real, una base de
ejemplos nueva y análisis real/sintético separados. No representa los trayectos
personales del usuario. La suite conserva las 99 pruebas anteriores: **138
aprobadas**, Ruff/formato correctos y `pip check` sin conflictos en Python 3.13.14.

El diagnóstico acotado `transmitracker.research.snapshot_diagnostic` está preparado.
La [revisión del proveedor](docs/PHASE1B_PROVIDER_REVIEW.json) no estableció una
cadencia aplicable; la [política actual](docs/PHASE1B_EXPERIMENT_POLICY.json)
bloquea las capturas antes de consultar la red. **No se ejecutó una serie real**.
Una captura antigua permite revisar referencias de catálogo, pero no estabilidad
de IDs. Los cambios de `start_time` en snapshots sucesivos se probaron solo con
fixtures sintéticos; no constituyen hallazgos reales sobre el productor.

## Fase 1A: catálogo estático

El [informe de Fase 1A](docs/PHASE1A_REPORT.md) contiene el esquema, los índices,
la demo y las limitaciones. El ZIP real ya está importado en
`data/catalog/official_20261112.sqlite3`: **1.054 rutas, 8.325 nodos y 1.564
patrones**, con 9.464.235 horarios. Importación: **169,32 s**; SQLite: **673,14 MB**.
Las consultas son de programación estática, no posiciones ni llegadas reales.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.catalog demo 'Portal Norte' --when '2026-11-12T08:00:00-05:00' --auto
.\.venv\Scripts\python.exe -m transmitracker.catalog search 'Portal Norte'
.\.venv\Scripts\python.exe -m transmitracker.catalog options 2000 --when '2026-11-12T08:00:00-05:00'
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE1A_VALIDATION_RESULTS.json
```

Quita `--auto` para elegir origen y ruta/patrón interactivamente. Para crear o
reutilizar el catálogo desde el ZIP local:

```powershell
.\.venv\Scripts\python.exe -m transmitracker.catalog import data/probes/official_static.zip --source-url https://gtfs.transmilenio.gov.co/GTFS.zip
```

La misma versión se reutiliza sin modificar SQLite; otra versión requiere otra
ruta mediante `--db` **antes del subcomando**. Se conservan IDs como texto,
procedencia/hash y esquema versionado. Estaciones expanden plataformas propias;
los destinos se filtran por patrón, orden, permisos y servicio activo en la
ventana de embarque. Se admiten horas mayores a 24 y excepciones de calendario.
Las frecuencias sin horario exacto no se presentan como salidas puntuales.

El ZIP real omite `direction_id` en todos sus viajes: se muestra **desconocido**
y se elige el patrón, sin inventar sentido 0/1. La suite cubre sentidos conocidos
con fixtures sintéticos. **99 pruebas aprobadas: 69 anteriores + 30 nuevas**.
Este es el resultado histórico de Fase 1A; la entrega 1B se describe arriba.
El tracking operativo sigue pendiente de autorización.

## Fase 0.5: históricos y snapshots

El [informe de Fase 0.5](docs/PHASE0_5_REPORT.md) documenta la búsqueda de
históricos operativos, análisis temporal, comparación de dos versiones estáticas,
arquitectura propuesta y almacenamiento medido. No se encontró un histórico
operativo público verificable en las fuentes consultadas. La comparación de
versiones no resuelve las asociaciones; `start_time` coincide con la hora GPS en
las 2.565 posiciones guardadas y requiere investigación adicional.

Los experimentos de `src/transmitracker/research/` reciben archivos locales y
escriben bases SQLite de prueba. No ejecutan recolección continua. Una captura
real repetida valida deduplicación; la secuencia sucesiva es explícitamente
sintética. Se conservan las 54 pruebas originales y se añaden 15: **69 aprobadas**.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE0_5_VALIDATION_RESULTS.json
.\.venv\Scripts\python.exe scripts/replay_phase0_5.py
.\.venv\Scripts\python.exe scripts/analyze_phase0_5.py
```

Estos comandos no usan internet; el análisis requiere las capturas reales
originales y el ZIP histórico local para incluir la comparación de versiones.
Los requisitos originales siguen íntegros en el plan, con una adenda propuesta
de migración. La arquitectura del colector compartido quedó aprobada como
dirección futura; su implementación operativa sigue sin autorización.

## Resultados reales

Consulta del **12 de noviembre de 2026, 21:56–21:57, America/Bogota**:

- GTFS estático: HTTP 200; 1.054 rutas, 8.325 paradas y 181.070 viajes.
- Posiciones: HTTP 200 y Protobuf interpretable; 2.565 vehículos, 30 obsoletos.
- Viajes: HTTP 200; 84.292 actualizaciones, sin eventos por parada en la muestra.
- Alertas: HTTP 200 y Protobuf legible, rechazado por IDs duplicados.
- Los tres endpoints Realtime antiguos devolvieron HTTP 500.
- Croma: documentación revisada; ninguna operación de datos ni claves solicitadas.

Los IDs Realtime no siempre coinciden con el estático. Consulta el
[informe de Fase 0](docs/PHASE0_REPORT.md) antes de usar los datos: HTTP 200
no garantiza integridad, actualidad ni utilidad para calcular llegadas.

## Preparación en Windows / PowerShell

Entorno comprobado: Windows x64 y **Python 3.13.14**. El plan conserva Python
3.12+ como objetivo; esta entrega no verifica otras versiones.

Si necesitas recrear el entorno, desde la raíz del proyecto:

```powershell
py -3.13 -m venv .venv
$env:PIP_CACHE_DIR = Join-Path (Get-Location).Path '.cache\pip'
$env:TEMP = Join-Path (Get-Location).Path '.cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

`requirements.txt` contiene las dependencias de ejecución; `requirements-dev.txt`
añade pytest y Ruff; `requirements-lock.txt` fija el entorno completo comprobado.
No hace falta activar `.venv` ni cambiar la política de ejecución de PowerShell.

## Demo sin internet

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker --offline --output data/offline-diagnostic.json
```

Sin argumentos también se usa el modo offline. Los fixtures son **sintéticos**,
con IDs `DEMO_*` y reloj fijo. La salida declara `mode: offline_synthetic_fixture`,
`network_requests: 0` y `live_connection_validated: false`. No demuestra conexión real.

## Diagnóstico real puntual

Hace descargas reales de los cuatro endpoints actuales; el ZIP ronda **180 MB**.
No ejecuta seguimiento periódico ni Croma.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker --live --only official_static official_positions official_tripupdates official_alerts --output data/latest-diagnostic.json
```

Para una prueba menor, usa `--only official_positions`. Con `--reuse-static` se
reutiliza explícitamente un ZIP previo, si existe, etiquetado como archivo local.
Sin `--only` se prueban también los endpoints antiguos. El comando devuelve 1
si algún feed falla o es rechazado y 2 ante argumentos/archivos inválidos.
Una respuesta legible pero obsoleta puede devolver 0: revisa la frescura del JSON.

Cada ejecución nueva conserva descargas y checkpoint en una subcarpeta fechada
de `data/probes/`. Las descargas originales están en `data/probes/official_*`.
No hay fallback automático a fixtures. Las URLs y su procedencia están en
[endpoints.json](docs/endpoints.json).

## Verificación sin internet

```powershell
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE2_1_VALIDATION_RESULTS.json
```

Ejecuta pytest, Ruff, formato y `pip check`; guarda
[PHASE3A_VALIDATION_RESULTS.json](docs/PHASE3A_VALIDATION_RESULTS.json). La suite bloquea la red
y usa temporales exclusivos en `.cache/verification`. Resultado original de Fase 0: **54 pruebas**;
con Fase 0.5: **69**; con Fase 1A: **99**; con Fase 1B: **138**; con Fase 2:
**160**; con Fase 2.1: **183**; con Fase 3A: **237 casos (183 anteriores + 54 nuevos)**.
En Windows, los casos con ventanas Tk se ejecutan en procesos separados sin
omitir ni reintentar sus aserciones; conservan el bloqueo de red.

Para regenerar fixtures sintéticos:

```powershell
.\.venv\Scripts\python.exe scripts/build_fixtures.py
```

Para analizar las descargas reales originales sin red, verificando SHA-256:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
.\.venv\Scripts\python.exe scripts/analyze_saved_feeds.py
```

Este análisis local no valida disponibilidad actual.
`scripts/research_sources.py` es una herramienta documental separada que sí hace
GET a fuentes públicas; no forma parte de las pruebas offline.

## Estructura

```text
src/transmitracker/
    __main__.py             # CLI de Fase 0
    diagnostics.py          # Modos real y fixture explícitos
    providers/http.py       # Descarga, límites y errores
    gtfs/static.py          # ZIP/CSV y referencias seleccionadas
    gtfs/realtime.py        # Protobuf y frescura
    gtfs/links.py           # Cruces exactos de identificadores
    catalog/                # Importación y consultas SQLite inmutable
    profiles/               # Modelos, contratos, validación y almacén separado
    gui/                    # CustomTkinter, controladores y trabajador local
    research/               # Experimentos offline y diagnóstico acotado
    reconstruction/         # Motor GPS, SQLite y replay exclusivamente offline
scripts/                    # Investigación y verificación
tests/                      # Pruebas y fixtures sintéticos
docs/                       # Plan, informe y evidencia JSON
data/                       # Descargas locales, excluidas de Git
```

`.venv/`, `.cache/`, `.env` y bases de datos locales están excluidos de Git.
`.env.example` no contiene secretos ni activa integraciones. No se crearon
commits ni se configuró un remoto.
