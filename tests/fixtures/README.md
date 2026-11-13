# Fixtures de Fase 0

Todos los datos de esta carpeta son **sintéticos y escritos a mano**. No son
respuestas reales de TransMilenio ni de Croma. Los IDs `DEMO_*` no representan
rutas, paraderos, viajes o vehículos de Bogotá.

- `gtfs/*.txt`: CSV de un GTFS pequeño con dos rutas, un viaje, dos paradas y
  una estación padre. Incluye horas mayores a `24:00:00`.
- `synthetic_realtime.textproto`: mensaje legible con dos vehículos, un
  TripUpdate y una alerta. El segundo vehículo carece de posición y timestamp
  deliberadamente: esos campos son opcionales en Protobuf.
- `synthetic_gtfs.zip` y `synthetic_realtime.pb`: archivos binarios reproducibles
  construidos por `scripts/build_fixtures.py`, usando únicamente los archivos anteriores.
- `manifest.json`: procedencia, reloj fijo y SHA-256 de ambos binarios.

La referencia fija es el **12 de noviembre de 2026, 07:00, America/Bogota**.
La frescura se evalúa respecto a ese reloj solo en modo fixture. Ningún test
puede demostrar disponibilidad real de una API. No se crean fixtures de Croma
porque en esta fase no se implementa su adaptador ni se obtienen respuestas.

## Fase 0.5

`snapshot_sequence.json` es una secuencia **sintética**, identificada como
`synthetic_scenario_not_real_api_captures`. Simula tres instantes y varios
vehículos, cambio de viaje, desaparición, identidad incompleta y datos obsoletos.
`research/scenarios.py` la convierte en mensajes Protobuf únicamente en memoria.
No representa capturas reales sucesivas, no se mezcla con ellas y no demuestra
eventos de llegada o continuidad operativa de TransMilenio.

## Fase 1B

`phase1b_temporal.json` es una secuencia **sintética** de tres snapshots y dos
vehículos. Simula un `start_time` que cambia con cada GPS y otro estable en
`25:00:00`, sobre el catálogo pequeño de esta carpeta. Su reloj es el
13-11-2026 a la 01:00 America/Bogota y su fecha de servicio es el día anterior.
No son capturas del proveedor ni demuestran que sus identidades cambien.
Los escenarios adicionales de perfiles, catálogos versionados y fallos temporales
se generan en los módulos de prueba, sin internet.
