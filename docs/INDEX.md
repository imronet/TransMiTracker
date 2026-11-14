# Índice de documentación — TransMiTracker 0.3.0

## Para empezar

- [Presentación e instalación](../README.md)
- [Preparar el catálogo y ejemplos](getting-started/SETUP.md)
- [Uso de perfiles, estados y privacidad](getting-started/USAGE.md)
- [Piloto GPS local: primera sesión cerrada y análisis offline](getting-started/LOCAL_GPS_PILOT.md)
- [Rastreador offline por ruta: comando y resultados candidatos](getting-started/OFFLINE_ROUTE_TRACKER.md)
- [Decisión experimental consumida y evidencia de licencia](research/LOCAL_PILOT_CONDITIONS.json)

## Para desarrollar

- [Arquitectura vigente y límites de evidencia](architecture/OVERVIEW.md)
- [Plan completo y adendas de autorización](development/IMPLEMENTATION_PLAN.md)
- [Versiones de producto, algoritmo y almacenes](development/VERSIONING.md)
- [Validación y replay sin sobrescribir evidencia](development/VALIDATION.md)
- [Política documental obligatoria](development/DOCUMENTATION_POLICY.md)
- [Instrucciones de contribución asistida](../AGENTS.md)
- [Informe de esta reorganización](development/DOCUMENTATION_MAINTENANCE_REPORT.md)

## Investigación y trabajo futuro

- [Continuidad GPS offline: start_time, comparación de filtros y límites](research/GPS_CONTINUITY_OFFLINE.md)
- [Correspondencia GTFS y progresión geométrica offline](research/GPS_GTFS_GEOMETRY_OFFLINE.md)
- [Viabilidad de GPS real previa a 3B: fuentes, costes y condiciones](research/GPS_REAL_FEASIBILITY.md)
- [Diseño de proveedores y créditos: no implementado](research/CROMA_INTEGRATION_DESIGN.md)
- [Históricos operativos, snapshots y limitaciones de IDs](archive/phases/PHASE0_5_REPORT.md)
- [Diagnóstico temporal e identidad candidata](archive/phases/PHASE1B_REPORT.md)

Fase 3A está entregada. La primera sesión GPS real terminó el 13/11/2026;
su autorización está consumida y no se permite otra captura sin nueva autorización.
El plan conserva requisitos originales y adendas:
las posteriores precisan el alcance vigente sin borrar historia.
No existe todavía precisión operativa real validada ni recolección continua.

## Informes archivados (contexto de cada fase)

Los informes se mantienen íntegros, sin traducir ni revisar resultados retrospectivamente.
Sus instrucciones de reproducción conservan las rutas usadas entonces; para nuevas
salidas consulte la guía de validación. No ejecute comandos históricos sobre JSON protegidos.

- [PHASE0_5_REPORT.md](archive/phases/PHASE0_5_REPORT.md)
- [PHASE0_REPORT.md](archive/phases/PHASE0_REPORT.md)
- [PHASE1A_REPORT.md](archive/phases/PHASE1A_REPORT.md)
- [PHASE1B_REPORT.md](archive/phases/PHASE1B_REPORT.md)
- [PHASE2_1_REPORT.md](archive/phases/PHASE2_1_REPORT.md)
- [PHASE2_REPORT.md](archive/phases/PHASE2_REPORT.md)
- [PHASE3A_REPORT.md](archive/phases/PHASE3A_REPORT.md)
- [PHASE3B_P0_REPORT.md](archive/phases/PHASE3B_P0_REPORT.md)
- [PHASE3B_P2_REPORT.md](archive/phases/PHASE3B_P2_REPORT.md)
- [Primera sesión GPS real: agregados, QA y límites](archive/phases/PHASE3B_FIRST_REAL_REPORT.md)
- [Rastreador experimental offline por ruta: entrega y QA](archive/phases/PHASE3B_ROUTE_TRACKER_REPORT.md)

- [Catálogo de evidencias, hashes y excepciones de rutas](archive/evidence/INDEX.md)

