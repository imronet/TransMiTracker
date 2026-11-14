# Política documental obligatoria

## Fuentes de verdad

README presenta capacidades públicas e instalación. INDEX organiza la navegación.
getting-started contiene uso; architecture, diseño vigente; este directorio,
plan y versiones; research, propuestas no implementadas. Los informes y JSON
archivados son evidencia fechada, no documentación vigente. Mantener un documento
canónico por tema; enlazar/resumir, sin copiar explicaciones completas.

## Entrega por fase

Actualizar solo el documento vigente afectado, el plan si cambia el estado,
el informe de cierre y las evidencias necesarias. Cambiar README únicamente
cuando cambien capacidades públicas, instalación o limitaciones relevantes.
No crear otro documento si uno existente cumple la finalidad.

Cada informe debe indicar fecha/versión, objetivo/alcance, cambios, validaciones,
resultados/limitaciones, evidencias, riesgos/pendientes, decisión de cierre y
estado/autorización de la siguiente fase. Usar nombres descriptivos y enlaces
relativos. Los JSON complementan la explicación humana, no la sustituyen.

## Integridad y archivo

No sobrescribir evidencia histórica con una ejecución nueva. Usar rutas únicas
por fase/fecha/ejecución, conservar procedencia, parámetros, algoritmo y hashes.
No presentar caché como ejecución nueva ni funcionalidades futuras en presente.
Separar estático/Realtime, sintético/real, candidato/verificado y cruce/llegada.
Archivar informes/evidencias de cierre y mantener acceso desde INDEX.

Antes de mover una ruta, inventariar consumidores en código, scripts, tests,
configuración y Markdown. No modificar archivos históricos para reparar sus
resultados. Preservar rutas contractuales y documentar excepciones. Actualmente
los JSON en docs/ se conservan por compatibilidad; véase el
[catálogo de evidencias](../archive/evidence/INDEX.md).

Los generadores heredados pueden sobrescribir rutas fijas: no ejecutarlos sobre
evidencia protegida. Cuando acepten --output, proporcionar un destino nuevo;
si no, adaptar su interfaz en una tarea futura autorizada antes de regenerar.
No duplicar automáticamente las evidencias ni ejecutar proveedores para validarlas.

## Validación proporcional

Comprobar existencia, enlaces, referencias de consumidores y hashes de originales.
Solo ejecutar tests específicos si cambian dependencias/rutas ejecutables; cambios
puramente documentales no justifican repetir la suite completa. Registrar alcance,
resultados y enlaces externos no comprobados. No instalar herramientas sin necesidad.
Las tareas futuras de Codex deben cumplir esta política y AGENTS.md.
