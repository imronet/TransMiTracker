# Evidencias históricas y compatibilidad

## Visor gráfico offline — 2026-11-14

[Validación focalizada y apertura real/sintética](OFFLINE_VIEWER_VALIDATION_20261114.json).
La [captura del visor](../phases/screenshots/offline-viewer-synthetic-20261114.png)
es exclusivamente sintética. La [guía existente](../../getting-started/OFFLINE_ROUTE_TRACKER.md#visor-gráfico-independiente-040)
recoge uso, resultados y límites; no se publican pantallas ni payloads reales.

## Mantenimiento focalizado de v0.3.0 — 2026-11-14

[Validación de limpieza y QA](MAINTENANCE_V030_20261114.json): hashes de las ocho
copias retiradas y sus originales archivados, pruebas del rastreador y enlaces.
No se ejecutaron scripts históricos ni se regeneraron evidencias anteriores.

## Rastreador experimental por ruta — 2026-11-14

- [Pruebas focalizadas y controles](ROUTE_TRACKER_VALIDATION_20261114.json).
- [Ejemplo real offline: agregados no identificables y reproducción](ROUTE_TRACKER_REAL_SUMMARY_20261114.json).
- [Informe de entrega](../phases/PHASE3B_ROUTE_TRACKER_REPORT.md).

## Evidencia anterior preservada

Los JSON originales permanecen en docs/ con bytes idénticos. Este índice los
agrupa sin duplicarlos ni cambiar rutas contractuales. No son resultados nuevos.

Motivos: diagnostics.py consume endpoints.json; lectores de scripts consumen
LIVE_DIAGNOSTIC.json y PHASE1A_DEMO.json; generadores heredados y la CLI GPS
escriben nombres fijos. Los informes guardan además rutas literales originales.
No se modificó src/ ni se ejecutaron generadores. Migrar sus interfaces requiere
una tarea explícita posterior. No reutilizar esos destinos para nuevas ejecuciones.

| Evidencia original | Contexto |
| --- | --- |
| [endpoints.json](../../endpoints.json) | Configuración consumida por diagnóstico; disponibilidad no comprobada ahora |
| [LIVE_DIAGNOSTIC.json](../../LIVE_DIAGNOSTIC.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [OFFLINE_DIAGNOSTIC.json](../../OFFLINE_DIAGNOSTIC.json) | Sintético; no acredita operación real |
| [PHASE0_5_ANALYSIS.json](../../PHASE0_5_ANALYSIS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE0_5_SOURCE_RESEARCH.json](../../PHASE0_5_SOURCE_RESEARCH.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE0_5_SYNTHETIC_REPLAY.json](../../PHASE0_5_SYNTHETIC_REPLAY.json) | Sintético; no acredita operación real |
| [PHASE0_5_VALIDATION_RESULTS.json](../../PHASE0_5_VALIDATION_RESULTS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1A_DEMO.json](../../PHASE1A_DEMO.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1A_IMPORT.json](../../PHASE1A_IMPORT.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1A_VALIDATION_RESULTS.json](../../PHASE1A_VALIDATION_RESULTS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1B_EXPERIMENT_POLICY.json](../../PHASE1B_EXPERIMENT_POLICY.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1B_PROFILE_EXAMPLES.json](../../PHASE1B_PROFILE_EXAMPLES.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1B_PROVIDER_REVIEW.json](../../PHASE1B_PROVIDER_REVIEW.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1B_REAL_SAVED_ANALYSIS.json](../../PHASE1B_REAL_SAVED_ANALYSIS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE1B_SYNTHETIC_TEMPORAL.json](../../PHASE1B_SYNTHETIC_TEMPORAL.json) | Sintético; no acredita operación real |
| [PHASE1B_VALIDATION_RESULTS.json](../../PHASE1B_VALIDATION_RESULTS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE2_1_REAL_CATALOG_QA.json](../../PHASE2_1_REAL_CATALOG_QA.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE2_1_VALIDATION_RESULTS.json](../../PHASE2_1_VALIDATION_RESULTS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE2_REAL_CATALOG_DEMO.json](../../PHASE2_REAL_CATALOG_DEMO.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE2_VALIDATION_RESULTS.json](../../PHASE2_VALIDATION_RESULTS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE3A_INPUT_INTEGRITY.json](../../PHASE3A_INPUT_INTEGRITY.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE3A_PARADERO_REVIEW.json](../../PHASE3A_PARADERO_REVIEW.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE3A_REAL_SAVED_REPLAY.json](../../PHASE3A_REAL_SAVED_REPLAY.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE3A_SYNTHETIC_EVALUATION.json](../../PHASE3A_SYNTHETIC_EVALUATION.json) | Sintético; no acredita operación real |
| [PHASE3A_VALIDATION_INITIAL_FAILURE.json](../../PHASE3A_VALIDATION_INITIAL_FAILURE.json) | Fallo intermedio conservado; no validación exitosa |
| [PHASE3A_VALIDATION_RESULTS.json](../../PHASE3A_VALIDATION_RESULTS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [PHASE3A_VALIDATION_TEMP_COLLISION.json](../../PHASE3A_VALIDATION_TEMP_COLLISION.json) | Fallo intermedio conservado; no validación exitosa |
| [SAVED_FEED_ANALYSIS.json](../../SAVED_FEED_ANALYSIS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [SOURCE_RESEARCH.json](../../SOURCE_RESEARCH.json) | Investigación/validación histórica; fecha y procedencia en el JSON |
| [VALIDATION_RESULTS.json](../../VALIDATION_RESULTS.json) | Investigación/validación histórica; fecha y procedencia en el JSON |

Hashes y correspondencia de todos los documentos originales:
[DOCUMENTATION_INTEGRITY.json](DOCUMENTATION_INTEGRITY.json).
Las ocho copias de `docs/screenshots/` se retiraron en el mantenimiento focalizado
de v0.3.0 tras comprobar SHA-256 contra sus versiones archivadas. Las imágenes
conservadas están en `docs/archive/phases/screenshots/`; los enlaces de los informes
ya apuntan allí. `DOCUMENTATION_INTEGRITY.json` y el informe de reorganización
anterior conservan las rutas originales como registro histórico, no como rutas
vigentes. Los once documentos puente se conservan.

Los informes se conservan sin cambios de contenido en [phases](../phases/).
Sus nombres inline/rutas de comandos describen el contexto de la ejecución original;
no son instrucciones para sobrescribir evidencia. Los comandos actuales están en
[VALIDATION](../../development/VALIDATION.md).
