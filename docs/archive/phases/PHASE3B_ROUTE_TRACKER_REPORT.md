# Fase 3B — Primer rastreador experimental offline por ruta

Fecha: **2026-11-14**. Producto **0.3.0**; algoritmo aislado
`route-tracker-experimental-0.1.0`. Base: commit
`063087039abc9251cf8797e81b0f9596a6f064f2`.

## Entrega y alcance

Se implementa una CLI manual funcional sobre sesiones guardadas, con selección
por ruta exacta, agrupación fuente/vehículo, deduplicación, segmentos candidatos
y proyección sobre shapes del catálogo. Se reutilizan el lector con validación
de hashes, contratos de snapshots, distancia, proyección, catálogo de solo lectura
y restricción de salidas privadas. No hay dependencias nuevas.

`trip_id`, `start_time`, fecha y referencias de parada se conservan como auxiliares
y sus cambios se cuentan, sin bloquear continuidad. La herramienta no modifica
ni sustituye el motor 3A; no verifica identidades operativas ni acepta eventos o
duraciones. [Uso, comando PowerShell y semántica](../../getting-started/OFFLINE_ROUTE_TRACKER.md).

## Ejemplo con datos reales ya guardados

Se procesaron los **12 snapshots existentes** de la primera sesión, sin red ni
capturas adicionales. Se eligió la ruta de la mediana S01 del estudio previo;
la selección con el ID exacto queda privada. Se consultó el catálogo
`data/catalog/official_20261112.sqlite3`, importado el 12/11/2026, procedente de
`https://gtfs.transmilenio.gov.co/GTFS.zip`. No se comprobó ese endpoint ahora.
SHA-256 del ZIP: `c66c7af657371eac892bab4b327e3a1e7be5d19ae0e9e5b4355e231261e3a09d`;
la huella del SQLite se contrasta con la evidencia previa en el agregado enlazado.

| Resultado | Conteo |
| --- | ---: |
| Vehículos candidatos de la ruta | 3 |
| Observaciones originales de la ruta | 36 |
| Timestamps GPS distintos, sumados por candidato | 30 |
| Repeticiones retiradas del movimiento | 6 |
| Segmentos `movimiento_candidato` | 2 |
| Segmentos `interrumpido`, con actividad de movimiento | 1 |
| Segmentos `estacionario` | 1 |
| Observaciones aisladas `ambiguo` | 5 |
| Segmentos de una muestra `descartado` | 1 |

Diez segmentos en total. Los incidentes son cinco ambigüedades geométricas,
seis repeticiones y un retroceso geométrico. No hubo cambios de ruta ni saltos
espaciales incompatibles en este ejemplo. Se registraron **27 cambios de
`start_time`**, sin cambios de los otros auxiliares examinados. Las ambigüedades
no se resuelven mediante IDs de viaje ni seleccionando una rama arbitraria.

Los dos segmentos móviles finalizados normalmente tienen progresos aproximados
de **1.299 m** y **3.208 m**. El interrumpido acumula **1.809 m** de progreso antes
del retroceso; no se enlaza a la porción posterior, de bajo movimiento. Estos
valores describen proyecciones candidatas, sin tiempos de recorrido aceptados.
Todos los segmentos proyectados conservan varios patrones del mismo shape.

### Contraste con diagnósticos anteriores

El estudio geométrico seleccionaba la cadena consecutiva móvil más larga por
candidato; las repeticiones cortaban esas cadenas. Esta herramienta procesa
la ruta completa, conserva todos sus candidatos y retira repeticiones sin
contarlas como movimiento. Por ello los totales y longitudes no deben igualarse.
El criterio conservador anterior sigue produciendo cero desplazamientos
aceptados; esta capacidad separada usa identidad simplificada explícitamente.

La comprobación local localizó una única ventana de cinco muestras con los cuatro
deltas de proyección de S01: distancia **1.323,76 m** (1.324 m redondeados) y
progreso **1.430,06 m**, dentro de un segmento mayor. El resultado concreto figura
en el [resumen agregado](../evidence/ROUTE_TRACKER_REAL_SUMMARY_20261114.json).
Esto contrasta soporte coincidente, sin equiparar identidad candidata con servicio.

## Validación y reproducción

**106 pruebas pertinentes aprobadas en 21,19 s**: 13 nuevas del rastreador,
38 de piloto local, 54 de reconstrucción/almacenamiento y una de versión.
Los tests bloquean sockets y HTTP. Cubren selección exacta, fuentes independientes,
varias rutas, timestamps repetidos/conflictivos, cambio de ruta, ausencia/reaparición,
regresión, huecos, saltos, frescura, segmentos múltiples, patrones compartidos,
ambigüedad, conservación del original, hashes y salidas privadas reproducibles.

Ruff correcto; formato correcto (**118 archivos**); `pip check` correcto con
Python 3.13. No se repitió la suite GUI ni la suite completa: los cambios están
aislados y los consumidores de 3A se probaron directamente.
[Comandos y salidas](../evidence/ROUTE_TRACKER_VALIDATION_20261114.json).
Verificación documental: enlaces locales correctos en los ocho documentos
actualizados/nuevos; sin coincidencias de los IDs reales de la selección en
los archivos de entrega. `data/pilots` permanece excluido de Git y `git diff
--check` no detectó errores de espacios.

Dos ejecuciones reales **offline** del mismo análisis produjeron archivos idénticos
byte a byte; sus hashes y el contraste S01 están en el resumen público. El lector
verificó los hashes de los PB contra sus registros en ambas ejecuciones.
La huella del SQLite coincide con el diagnóstico geométrico anterior.
No se sobrescribieron las capturas ni los diagnósticos anteriores.

Directorio privado, excluido de Git:
`data/pilots/first-real-20261113-223641-1613d2b6/route-tracker-20261114/`.
Contiene `selection.json`, `report.json`, `replay.json` y `summarize_example.py`.
Los informes contienen observaciones originales, coordenadas, IDs y proyecciones;
no se publican. La consola y los agregados compartibles omiten esos datos.

## Archivos y límites de cierre

- Nuevo `src/transmitracker/research/route_tracker.py` y `tests/test_route_tracker.py`.
- Guía de uso enlazada arriba y este informe con dos evidencias nuevas.
- Versión en `pyproject.toml`; README, arquitectura, índice, versiones y adenda
  del plan actualizados para reflejar la capacidad disponible.

Motor 3A, GUI, perfiles y catálogo sin modificaciones. El agrupamiento no detecta
por sí solo reutilización de un ID físico dentro de una ruta; las discontinuidades
solo limitan enlaces. No se resuelven calendario de servicio, viaje ni patrón
operativo, bucles ambiguos o exactitud del GPS. El estado `estacionario` es un
criterio de bajo progreso, no una permanencia observada en parada.

Capacidad implementada y preparada para QA del propietario. Siguiente paso
recomendado: revisar estos segmentos privados y motivos de corte usando la CLI,
antes de autorizar otra capacidad. No se habilita recolección continua, nueva
captura, predictor o siguiente fase. **Sin commits ni push.**
