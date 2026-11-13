# Informe de Fase 0 — TransMiTracker

## Estado

Fase 0 completada: descargas reales, lectores mínimos y pruebas offline.
**La Fase 1 requiere aprobación expresa.** No se implementaron GUI, tracking
continuo, Telegram, tareas programadas ni importación a SQLite.

El plan recibido se conserva completo en `IMPLEMENTATION_PLAN.md`. Solo se
adaptaron `main.py` a `src/transmitracker/__main__.py` y las rutas `app/` a
`src/transmitracker/`. No se eliminaron fases ni requisitos.

Las consultas son del **12 de noviembre de 2026, America/Bogota (UTC−05:00)**.
Las conclusiones describen esas capturas; no garantizan disponibilidad futura.

## Evidencia

| Archivo | Contenido |
| --- | --- |
| `SOURCE_RESEARCH.json` | GET reales de documentación/metadatos, fechas, estados y hashes |
| `endpoints.json` | URLs y procedencia de su publicación |
| `LIVE_DIAGNOSTIC.json` | Diagnóstico real original, iniciado a las 21:56:47 |
| `SAVED_FEED_ANALYSIS.json` | Análisis posterior sin red, con verificación de hashes originales |
| `OFFLINE_DIAGNOSTIC.json` | Demo explícitamente sintética; no valida conectividad |
| `VALIDATION_RESULTS.json` | Pruebas, lint, formato, versiones y entorno ejecutados |

Los cuerpos descargados están en `data/research/` y `data/probes/`, excluidos
de Git. Los JSON pequeños de `docs/` permiten revisar los resultados. Los
fixtures se escribieron por separado; no son respuestas de las APIs.

## Descubrimiento de fuentes

La [noticia oficial](https://www.transmilenio.gov.co/comunicaciones/noticias-de-transmilenio/especiales-transmilenio/datos-abiertos-tiempo-real-transmilenio-conecta-operacion-sistema-tecnologia-ciudad)
enlaza al [portal GTFS](https://gtfs.transmilenio.gov.co/). Su JavaScript carga
[`manifest.json`](https://gtfs.transmilenio.gov.co/manifest.json), donde se
obtuvieron los cuatro endpoints actuales, sin adivinar rutas.

El HTML incluye un aviso de mantenimiento oculto. El texto de un buscador no
basta para determinar disponibilidad: el estado efectivo depende del JavaScript
y del manifiesto. El manifiesto consultado a las 21:52:53 declaraba disponibilidad
pero contenía fechas de la madrugada; las descargas posteriores sí tenían
cabeceras Realtime recientes. Se inspeccionaron los mensajes, sin confiar en
la fecha o el tamaño del manifiesto como garantía de frescura.

El [catálogo de Datos Abiertos Bogotá](https://datosabiertos.bogota.gov.co/dataset/especificacion-gtfs-general-transport-feed-specification-sitp)
se consultó también mediante CKAN. Remite a ArcGIS de TransMilenio; la búsqueda
de su organización `9unqgkQ8KCOfnzoB` mostró archivos históricos, incluido
`GTFS_20261027.zip`. **Esos ZIP históricos no se descargaron ni validaron**.
El estático usado fue el del portal actual.

## Endpoints probados con conexiones reales

| GET | Hora | HTTP | Resultado |
| --- | --- | --- | --- |
| `https://gtfs.transmilenio.gov.co/GTFS.zip` | 21:56:47 | 200 | 180.271.992 bytes; ZIP/CSV interpretable |
| `https://gtfs.transmilenio.gov.co/positions.pb` | 21:57:39 | 200 | 298.066 bytes; 2.565 posiciones |
| `https://gtfs.transmilenio.gov.co/tripupdates.pb` | 21:57:40 | 200 | 8.211.671 bytes; 84.292 actualizaciones |
| `https://gtfs.transmilenio.gov.co/alerts.pb` | 21:57:41 | 200 | 101.391 bytes; Protobuf legible, rechazado por IDs duplicados |
| `https://gis.transmilenio.gov.co/gtfs/vehiclepos.pb` | 21:57:41 | 500 | Falló tras dos intentos |
| `https://gis.transmilenio.gov.co/gtfs/tripupdate.pb` | 21:57:42 | 500 | Falló tras dos intentos |
| `https://gis.transmilenio.gov.co/gtfs/serviceAlerts.pb` | 21:57:43 | 500 | Falló tras dos intentos |

Los antiguos proceden de la página oficial `gis.../gtfs/` indexada por búsqueda;
la propia página devolvió HTTP 500. No constituyen un respaldo funcional.
Los cuatro endpoints actuales respondieron al primer intento y sin enviar
claves. Esto no establece SLA, cuota ni permiso para sondeo ilimitado.
El catálogo CKAN indica CC BY-SA 4.0; revisar atribución y alcance antes de
redistribuir datos derivados.

## GTFS estático y cobertura

Se recorrieron todos los registros de horarios y geometrías, sin extraer el ZIP
ni cargar `stop_times.txt` y `shapes.txt` completos en memoria.

| Tabla | Registros |
| --- | ---: |
| `routes.txt` | 1.054 |
| `stops.txt` | 8.325 |
| `trips.txt` | 181.070 |
| `stop_times.txt` | 9.464.235 |
| `shapes.txt` | 952.585 |
| `agency.txt` | 7 |
| `calendar.txt` | 7 |
| `calendar_dates.txt` | 133 |
| `frequencies.txt` | 14 |

`feed_info.txt` declara vigencia del 01-01-2026 al 31-12-2026 y versión `1`.
Hay 1.053 rutas de tipo 3 y una de tipo 6. Las agencias permiten distinguir:

| Agencia publicada | Rutas | Paradas distintas con horarios |
| --- | ---: | ---: |
| Transmilenio-Troncal | 113 | 656 |
| Transmilenio-Alimentadores | 152 | 682 |
| Transmilenio-Dual | 31 | 183 |
| Zonal-Urbano | 746 | 7.219 |
| Zonal-Complementario | 7 | 192 |
| Zonal-Especial | 4 | 63 |
| TransMiCable | 1 | 4 |

Las paradas pueden compartirse entre agencias: no deben sumarse para obtener
cobertura total. En `stop_times.txt` aparecen 1.052 rutas y 8.155 paradas
distintas. Algunas estaciones padre pueden no figurar como parada del viaje
porque este atiende sus plataformas. Los conteos no demuestran actividad de
todas las rutas a la hora consultada.

Las referencias comprobadas no presentaron errores: viaje→ruta/servicio,
horario→viaje/parada y parada→estación padre. **No se ejecutó un validador GTFS
integral**: no se certifican todas las reglas condicionales, horarios,
geometrías o calendarios de la norma.

## Realtime y calidad

Las tres cabeceras descargadas tenían timestamp **21:56:56**. La frescura se
evalúa por entidad: 300 segundos es el umbral diagnóstico inicial, no una
tolerancia oficialmente calibrada. Más de 60 segundos en el futuro se marca
`future`; un timestamp ausente se marca `unknown`.

- **Posiciones:** 2.535 recientes y 30 obsoletas en la lectura original. Aportan
  coordenadas, vehículo, viaje, ruta, inicio del viaje, parada, secuencia y estado.
  No todas incluyen sentido (`direction_id`).
- **TripUpdates:** 426 recientes y 83.866 obsoletos respecto a la consulta.
  Las 84.292 entidades contienen **cero `stop_time_update`**. Sirven para estudiar
  descriptores y timestamps; no aportan eventos de llegada/salida por parada en
  esta captura. No se calcularon ETAs.
- **Alertas:** 421 entidades y ocho IDs repetidos dos veces: `193183`, `206186`,
  `213714`, `212516`, `213854`, `213882`, `213904`, `213884`. La inspección
  forense muestra textos y selectores de ruta/parada, pero el lector estricto
  rechaza el feed completo. No se deduplica silenciosamente.

El lector comprueba campos requeridos por Protobuf, versión, IDs de entidad y
coordenadas. No certifica toda la semántica GTFS-RT. Identifica mensajes
diferenciales pero no reconstruye su estado previo.
`live_connection_validated` significa conexión real con algún contenido reciente
bajo esas comprobaciones; no implica que todas las entidades sean actuales ni
que permitan calcular llegadas. Un archivo guardado o fixture nunca prueba
disponibilidad actual.

## Relación entre IDs

Las referencias [GTFS Schedule](https://gtfs.org/documentation/schedule/reference/)
y [GTFS Realtime](https://gtfs.org/documentation/realtime/reference/) establecen:

1. `vehicle.id` identifica el vehículo; `FeedEntity.id` identifica una entidad.
   Aunque coincidan en esta muestra, no son intercambiables.
2. `VehiclePosition.trip.trip_id` referencia `trips.trip_id`.
3. `trips.route_id` lleva a la ruta y `shape_id` a su geometría.
4. `stop_times.trip_id` aporta las paradas ordenadas; `stops.parent_station`
   relaciona plataformas con estaciones.
5. Las actualizaciones de parada pueden usar `stop_id` o secuencia cuando el
   viaje sea identificable. No se infieren esos datos si faltan.
6. Resolver la instancia operativa exige considerar fecha de servicio, hora,
   calendario y frecuencias; no basta siempre un `trip_id` coincidente.

Cruces exactos sobre las 2.565 posiciones capturadas:

| Comprobación | Resultado |
| --- | ---: |
| `route_id` encontrado | 2.565 |
| `trip_id` encontrado | 189 |
| De esos 189, ruta Realtime distinta de la ruta del viaje estático | **159** |
| Viaje y ruta coincidentes sin ese conflicto | **30** |
| `trip_id` sin coincidencia | 2.376 |
| `stop_id` encontrado | 2.451 |
| `stop_id` sin coincidencia | 114 |

Ejemplo real consistente: vehículo `924093` → viaje `TB4710008.7.11836` → ruta
`11836` (`K721 / Terminal Salitre`), geometría `11836`, parada `53244`.
La unión al catálogo está probada; la instancia completa no se declara resuelta.

Ejemplo conflictivo: vehículo `504203`, viaje `CE12D0027.6.12327`, ruta Realtime
`13378`; ese viaje estático pertenece a `12327`. Se etiqueta `conflict` sin
atribuirle una geometría fiable.

En TripUpdates coinciden 39.822 viajes y existen 83.356 rutas de las 84.292
entidades; no hay conflictos de ruta entre los viajes coincidentes. No hay
eventos de parada que unir. **La causa de las discrepancias no está confirmada**.
No se recortan sufijos, convierten IDs a números ni mezclan proveedores para
forzar coincidencias. No está probada la cobertura Realtime de todo el SITP.

## Croma: investigación sin integración de pago

La [guía oficial](https://docs.usecroma.com/es/guides/colombia/transmilenio)
y [OpenAPI](https://usecroma.com/openapi.json) devolvieron HTTP 200 a las 21:51.
Documentan base `https://api.croma.run` y operaciones POST bajo `/co/transmilenio/`:

| Ruta | Función documentada |
| --- | --- |
| `stops-search/v1` | Buscar paraderos |
| `stop/v1` | Detalle de parada |
| `stop-departures/v1` | Horarios programados |
| `routes-search/v1` | Buscar rutas |
| `route/v1` | Patrones, paradas y geometría opcional |
| `vehicles/v1` | Posiciones de vehículos |
| `stop-arrivals/v1` | Llegadas y base de estimación |
| `alerts/v1` | Novedades |

La guía distingue catálogos con `as_of` y operaciones en vivo. Campos como
`live`, `notice`, `reported_at` y `basis` permiten evaluar vigencia y procedencia.
Puede devolver posiciones anteriores o llegadas de horario si falla la fuente:
no se supone independencia del proveedor oficial.

La [autenticación](https://docs.usecroma.com/authentication) exige
`Authorization: Bearer <clave de organización>`. No se solicitaron claves ni
se ejecutaron operaciones POST; solo se consultó documentación pública.

Los [créditos](https://docs.usecroma.com/credits) documentados son uno por dataset
y diez por consulta en vivo. Un acierto de caché no consume, pero exige saldo
para aceptar la consulta; no se presupone ese acierto ni gratuidad de un sondeo.
No se ejecutó ninguna operación de datos de Croma en esta investigación.

Los [límites](https://docs.usecroma.com/rate-limits) se comparten por organización.
No se encontró una cuota específica por segundo para TransMilenio; no se inventa.
Una futura integración debe atender `Retry-After` ante 429 y revisar saldo y
cabeceras. **Las respuestas, cobertura, latencia y disponibilidad de la API no
se validaron mediante integración real.** No se fabricaron fixtures de Croma.

## Implementación y validación

La CLI separa `--live` de `--offline` (predeterminado). No cambia silenciosamente
a fixtures. Cada nueva consulta guarda descargas en una carpeta fechada.
`--reuse-static` es reutilización explícita, etiquetada como archivo local.

La descarga verifica TLS, aplica timeout de conexión de 10 s y lectura de 20 s,
presupuesto transcurrido de 180 s comprobado entre fragmentos y límites de 256
MiB para ZIP y 32 MiB para Realtime. Una lectura en curso puede añadir su timeout
al presupuesto. Hay máximo dos intentos, con backoff de 0,5 s, ante transporte o
HTTP 500/502/503/504. No se reintenta automáticamente HTTP 401/403/404/429.
Se escribe un parcial y solo se reemplaza el destino al completar la descarga.
El ZIP tiene límite de 3 GiB descomprimidos y no se extrae al disco.
Son límites internos de esta prueba, no cuotas oficiales.

Resultado en Windows x64 / **Python 3.13.14**:

| Verificación | Resultado |
| --- | --- |
| `python -m pytest -q` | **54 passed** |
| `python -m ruff check .` | Sin errores |
| `python -m ruff format --check .` | 22 archivos con formato correcto |
| `python -m pip check` | Sin dependencias incompatibles |

La suite bloquea sockets y transporte HTTP real. Cubre fixtures, campos ausentes,
obsolescencia, timestamps futuros/sin zona, conflictos de IDs, diferenciales,
coordenadas inválidas, ZIP/CSV defectuosos, HTTP 4xx/5xx, DNS/timeouts simulados,
reintentos, tamaño, presupuesto de tiempo y conservación de archivos anteriores.
Los temporales de la suite quedan en `.cache/pytest`.

| Dependencia | Versión probada | Evidencia con Python 3.13 |
| --- | --- | --- |
| httpx | 0.28.1 | Descargas reales y pruebas de errores |
| gtfs-realtime-bindings | 3.0.0 | Mensajes reales y fixtures |
| protobuf | 7.36.2 | Wheel `cp310-abi3-win_amd64`, decodificación ejecutada |
| tzdata | 2026.6 | `ZoneInfo('America/Bogota')` en Windows |
| pytest | 9.2.0 | Suite ejecutada |
| Ruff | 0.17.5 | Lint y formato ejecutados |

`VALIDATION_RESULTS.json` conserva `Requires-Python` y tags instalados. Las
dependencias están fijadas en `requirements*.txt` y `pyproject.toml`. No se
instalaron paquetes de fases futuras. El objetivo Python 3.12+ del plan sigue
vigente, pero aquí solo se probó Python 3.13.14 / Windows x64.

## Archivos y siguiente decisión

Se crearon módulos de lectura/diagnóstico en `src/transmitracker/`, cuatro módulos
de pruebas y fixtures en `tests/`, cuatro herramientas en `scripts/`, este informe
y evidencia en `docs/`, configuración de dependencias y `.env.example`.
Se actualizaron README y `.gitignore` para instrucciones y cachés locales.

La aceptación de Fase 0 se cumple con feeds reales interpretados, datos en
consola, análisis de IDs y suite offline. La propuesta siguiente, **sujeta a
aprobación**, es preparar el catálogo de Fase 1 y definir el tratamiento de
IDs no coincidentes/conflictivos antes de cualquier seguimiento operativo.
No se inició la Fase 1.
