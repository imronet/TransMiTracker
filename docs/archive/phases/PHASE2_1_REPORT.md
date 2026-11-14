# Fase 2.1 — QA, correcciones y recorridos habituales

Entrega del **13 de noviembre de 2026, America/Bogota**, versión **0.1.0**.
Se aprobó el cierre de Fase 2; esta entrega corrige GUI, persistencia y selección.
**No se inició Fase 3A.** No hubo tracking, predicción, consultas de pago, mensajes
de Telegram ni recolección automática. No se añadieron dependencias.

## Resultado

Es posible configurar uno a tres tramos, guardar sin fecha ni salida ficticia,
recibir advertencias sin perder campos y recuperar el perfil al reabrir.
Los borradores incompletos se conservan separados del último perfil configurado.
La consulta horaria anterior sigue disponible como herramienta opcional.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.gui
```

## Causas raíz y correcciones P0

| Bug | Causa identificada | Corrección y evidencia |
| --- | --- | --- |
| BUG-01: añadir/eliminar pierde configuración | `build_legs` destruía los widgets y solo recibía `values()` con IDs/secuencias. No conservaba textos parciales, nombres, opciones ni modalidad. `remove_leg` además llamaba a `temporal_changed`, que limpiaba selecciones posteriores. Reconstruir un tramo vacío también podía pasar `None` a `Entry.insert`. | Snapshot completo por tramo, UID estable, restauración de etiquetas/opciones/textos y cancelación de tareas de widgets anteriores. Eliminar conserva los restantes; avisa revisar la nueva conexión. Regresión con tramo completo y otro parcialmente escrito, adición hasta tres, eliminación y respuesta antigua pendiente. |
| BUG-02: errores parecen borrar el recorrido | No se encontró una limpieza explícita en el callback final de validación. Sí había `reset()` anticipado en `fetch_routes`, cascadas desde `changed`/`temporal_changed` y reconstrucciones incompletas, ejecutadas antes de conocer el resultado de la consulta. | Consultar no limpia anticipadamente. Resultados/errores se presentan separados de los valores; las preferencias horarias no invalidan la estructura. Solo selecciones explícitamente incompatibles limpian dependencias locales. Regresiones de límite de llegada fallido y catálogo no disponible conservan snapshot íntegro. |
| BUG-03: guardado exige salida ficticia | `commit(True)` llamaba siempre a `departure()` y `ProfileStore.save`, cuyo contrato exigía validación temporal y disponibilidad en esa fecha/horizonte. La selección también dependía de esa ventana. | Nuevo `save_configuration` con validación estructural sin fecha. Selectores estructurales del catálogo. Consulta programada opcional y separada; el API temporal anterior se conserva. Regresión guarda sin fecha/salida y comprueba que una fecha sin servicio no modifica el perfil guardado. |

Escribir otro texto de origen conserva la selección anterior hasta confirmar un
resultado, pero impide guardarla como si el texto nuevo ya estuviera confirmado.
Ese estado parcial puede guardarse en borrador. Una consulta fallida conserva
las selecciones y textos. Cambiar explícitamente de ruta/patrón puede invalidar
un destino incompatible; esto se diferencia de borrar datos por un error.

## Perfiles y validación

Casa → Trabajo requiere límite de llegada y días activos, sin salida manual para
guardar. Trabajo → Casa no exige límite de llegada y añade `usual_departure`
opcional. El decodificador de perfiles acepta los documentos anteriores sin ese
campo. Los perfiles de regreso antiguos conservan su JSON original; al editarlos
se usa la nueva semántica sin límite obligatorio.

`CatalogService.validate_structure` aplica las reglas del modelo y comprueba
exactamente versión de catálogo, ruta, patrón, sentido publicado, ocurrencias,
permisos ordinarios de subida/bajada y destino posterior. No consulta un día ni
confunde estructura con disponibilidad del servicio. Los permisos condicionales
no se convierten en embarques ordinarios por suposición.

La ausencia de horarios para un instante no bloquea el guardado estructural.
**Consultar horario programado** requiere explícitamente fecha y salida, y reusa
calendario, excepciones, America/Bogota, medianoche y horas mayores a 24 de Fase 1B.
`ARRIVAL_DEADLINE_EXCEEDED` solo se aplica a esa consulta en Casa → Trabajo.
`TRANSFER_PATH_UNVERIFIED` es informativo y no bloquea el guardado.

El ajuste antes llamado «Ventana de embarque» ahora se presenta como **Horizonte
de búsqueda de buses programados**, dentro de opciones avanzadas, con tooltip y
explicación visible. Su nombre persistente `departure_window_minutes` se conserva
por compatibilidad. No es una espera media: `StructureCheck` declara
`expected_wait_minutes=null` y `wait_basis=unavailable_no_historical_estimate`.
No se implementó el cálculo histórico ni un predictor.

Si no hay salida habitual ni evidencia de duración, se informa esa ausencia.
No se fabrica una hora absoluta de llegada a casa. Una consulta programada
explícita sí puede mostrar sus horas, etiquetadas como programadas.

## Dos modalidades de búsqueda

- **Origen primero:** nombre/código/ID → ruta → patrón → destino posterior.
- **Ruta primero:** número/nombre corto/nombre largo → patrón → origen habilitado
  → destino posterior.

Ambas consultan servicios del catálogo, con SQL únicamente en `catalog/queries.py`.
Los orígenes se filtran por subida y existencia de destino posterior; los destinos
por bajada y secuencia. Los bucles mantienen las ocurrencias, no solo el ID.
Un patrón/sentido no se mezcla con otro. Cuando falta `direction_id`, permanece
desconocido. Los patrones se diferencian por destino habilitado y secuencias.

Alternar modalidad cambia la presentación y conserva selecciones compatibles.
El estado de modalidad y presentación se guarda vinculado a la revisión del perfil;
un borrador mantiene también sus textos incompletos y UIDs de tramos.

## Persistencia, migración y estados

El almacén local sigue siendo `data/gui/profiles.sqlite3`, separado del GTFS.
El esquema **1 → 2** es aditivo:

| Tabla | Cambio |
| --- | --- |
| `profiles`, `profile_revisions` | Conservadas; no se reescribe el JSON existente durante la migración |
| `catalog_registry`, `active_catalog`, `catalog_events` | Conservados, sin remapeo ni activación silenciosa |
| `profile_drafts` | Borrador por perfil/clase, revisión propia, revisión base, presentación y archivado |
| `profile_schedule_checks` | Resultado temporal opcional ligado a revisión e instante |

La prueba de migración recrea el esquema/JSON previos y verifica igualdad del
payload original en perfil e historial, hash de catálogo y revisión. Abrir una
base antigua añade tablas y cambia `user_version`; no borra perfiles existentes.
La compatibilidad es de lectura/migración hacia esta versión, no una promesa de
que el código antiguo entienda datos nuevos. No hay downgrade automático.

Guardar un borrador no sobrescribe el perfil configurado. Guardar configuración
archiva la edición correspondiente; los borradores archivados conservan su revisión
y pueden servir para restaurar la presentación de la configuración. Un borrador
de otra edición más reciente no se archiva por coincidencia de ID: se usa revisión
esperada. JSON de borradores tiene una whitelist y no admite campos de secretos.

Los estados expuestos son:

| Estado | Alcance |
| --- | --- |
| Borrador incompleto/sin validar | Edición reanudable; no acredita recorrido íntegro |
| `configured` | Estructura comprobada y preferencias guardadas |
| `schedule_validated` | Consulta programada satisfactoria para esa revisión |
| `pending_migration` | El perfil conserva un catálogo distinto del activo |

Una nueva revisión estructural no hereda evidencia temporal de la anterior.
La consulta de un formulario aún distinto del perfil guardado no marca esa
revisión como validada. Los conflictos de perfil y borrador no sobrescriben otra
edición. El catálogo antiguo sigue fijado y no se migran IDs automáticamente.

Se conservan revisiones y datos de Fase 2. El último perfil configurado puede
coexistir con un borrador; el dashboard distingue ambos. Si un borrador se basó
en una revisión antigua, guardar como configuración exige reconciliar el conflicto.

## Asincronía y QA de ventanas

Los resultados se entregan por generación y UID de tramo/vista. Destruir o
reconstruir widgets invalida sus consultas pendientes, sin alterar sus datos.
La cola del trabajador contiene resultados/futuros; los callbacks que referencian
widgets permanecen en un registro administrado por el hilo principal. Las tareas
capturan controladores y datos, sin referencias a los widgets del editor.

Durante ejecuciones intermedias aparecieron errores de lectura de scripts Tcl
de WindowsApps al crear intérpretes consecutivos. Una comprobación mínima de dos
raíces funcionó; no se concluyó que faltaran archivos de la instalación. Se
reforzó la vida de callbacks y la liberación de ciclos de ventanas destruidas en
el hilo principal antes de crear otra raíz. La ejecución final de todas las
pruebas y la reapertura quedaron correctas. No se modificó Python externo ni se
ocultó el problema con skips o mocks de Tk.

## Dashboard, ayuda y versión

El dashboard prioriza las tarjetas de ambos perfiles y sus estados, muestra
tramos y horarios configurados y explica los estados vacíos. Distingue datos
programados, históricos sin estimaciones y Realtime deshabilitado. No muestra
estadísticas o predicciones inexistentes.

Configuración añade explicaciones de GTFS, Croma, token/Chat ID, almacenamiento y
`.env` sin cifrado, tooltips y enlaces oficiales. Los controles de intervalos y
avisos futuros están deshabilitados. Guardar credenciales continúa siendo una
preparación local, sin consultas ni mensajes. Los enlaces externos solo se abren
por acción explícita del usuario.

Se inspeccionó la versión **0.0.1** de `pyproject.toml` antes de cambiarla a
**0.1.0**. `version.app_version()` lee esa fuente y usa metadatos de distribución
solo cuando no está el proyecto. Título, dashboard, pie lateral y README reflejan
la misma versión. Criterios MAJOR/MINOR/PATCH en `docs/VERSIONING.md`.
No se implementó empaquetado final.

## Evidencia real estática y capturas

`scripts/demo_phase2_1.py` usa exclusivamente el SQLite oficial ya importado,
en un espacio de ejemplos separado: `data/phase2_1/demo`.

Comprobaciones en `PHASE2_1_REAL_CATALOG_QA.json`:

- Búsqueda de Portal Norte encuentra estación `2000`.
- Ruta `13766` / 2-1, patrón publicado con sentido desconocido: tramos
  `74389` sec. 2 → `56059` sec. 3 → `56060` sec. 4 → `56128` sec. 5.
- Casa → Trabajo: tres tramos, límite 09:00 y dos transbordos de 7+2 y 4+1 minutos.
  Guardado estructural correcto con advertencias espaciales conservadas.
- Trabajo → Casa: un tramo técnico publicado, salida habitual opcional 17:30,
  sin límite de llegada. No se afirma que ese tramo sea el regreso personal.
- Sin fecha ni salida de consulta, sin ejecutar ejemplos temporales, sin HTTP.
- Un controlador nuevo recuperó exactamente ambos perfiles. El SHA-256 del SQLite
  real antes/después coincidió: datos GTFS originales **sin cambios**.

Los nombres publicados de nodos de regulación no acreditan una conexión peatonal
ni una recomendación de uso. Los ejemplos son técnicos, no trayectos personales,
posiciones en vivo ni respuestas inventadas del proveedor.

```powershell
.\.venv\Scripts\python.exe scripts/demo_phase2_1.py
.\.venv\Scripts\python.exe -m transmitracker.gui --qa-demo
```

Capturas de la aplicación real con esos ejemplos:

- [Dashboard](screenshots/phase2_1-dashboard.png).
- [Editor de recorrido habitual](screenshots/phase2_1-profile.png).
- [Modalidad ruta primero](screenshots/phase2_1-route-first.png).
- [Confirmación de guardado sin fecha ni salida de consulta](screenshots/phase2_1-saved.png).
- [Configuración y ayuda](screenshots/phase2_1-settings.png).

La revisión visual cambió el perfil técnico de regreso a Ruta primero y lo
guardó desde la ventana: confirmación de revisión 2, sin fecha ni salida de
consulta y sin límite de llegada. El JSON de QA conserva el resultado previo
del script (revisión 1); son verificaciones consecutivas del mismo espacio de
ejemplos, no una inconsistencia de versiones ni cambios en perfiles personales.

## Pruebas y archivos

**183 pruebas aprobadas: 160 anteriores + 23 nuevas**, en **167,82 s**.
Python 3.13.14 / Windows, Ruff correcto, **72 archivos formateados**, `pip check`
sin conflictos. Evidencia: `PHASE2_1_VALIDATION_RESULTS.json`.

Se conserva la suite anterior. Se actualiza únicamente la expectativa del test
GUI de cambios previos: ahora exige conservar selecciones estructurales de los
otros tramos, en vez de exigir borrarlas. Se renombra descriptivamente ese test;
no se elimina ni reduce su cobertura de uno a tres tramos.

Las 23 regresiones nuevas cubren los tres bugs, campos/nombres/texto parcial,
añadir/eliminar, errores sin limpieza, borradores/reapertura, los dos perfiles,
advertencias no bloqueantes, integridad, calendario sin servicio, migración del
esquema, revisiones/catálogos antiguos, ruta primero, cambios de modalidad,
presentación persistente, respuestas obsoletas y versión. Las ventanas son Tk
reales; la suite bloquea sockets y transporte HTTP. Los fixtures son sintéticos
y se mantienen separados del QA con catálogo real.

```powershell
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE2_1_VALIDATION_RESULTS.json
```

Archivos nuevos: `profiles/drafts.py`, `gui/help.py`, `version.py`,
`scripts/demo_phase2_1.py`, dos módulos de regresión, este informe, `USAGE.md`,
`VERSIONING.md`, evidencias JSON y capturas. Cambios en modelos/servicios/almacén
de perfiles, consultas del catálogo, controlador/editor/app/trabajador y entrada
GUI, metadatos, verificador, una expectativa de prueba GUI, README y plan.
Se conservan los informes y evidencias anteriores.

## Limitaciones y mejoras diferidas

- BUG-01, BUG-02 y BUG-03 corregidos; aceptación estructural y reapertura probadas.
- Los borradores requieren pulsar Guardar borrador; no hay autoguardado.
- Eliminar un tramo requiere revisar el tiempo de la nueva conexión espacial.
- Validación estructural no demuestra servicio en cualquier fecha ni accesibilidad.
- La consulta temporal sigue validando un itinerario programado de ejemplo,
  sin resolver frecuencias no exactas ni optimizar todas las combinaciones.
- Sin evidencia histórica útil no se calcula espera/duración ni llegada absoluta.
- Migración gráfica entre catálogos y resolución visual de conflictos siguen
  diferidas; existen avisos, protección de revisión y servicios explícitos.
- `.env` no está cifrado; configuración corrupta requiere reparación manual.
- Verificación visual y de ventanas en este equipo; no se certifican todos los
  monitores/DPI ni otras versiones de Python.
- Fase 3A, GPS, predictor, Croma, Telegram y scheduler **sin iniciar**.
