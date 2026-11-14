# Política de versiones

La versión declarada antes de Fase 2.1 era **0.0.1**, comprobada en `pyproject.toml`.
Fase 2.1 usó **0.1.0** por la ampliación del guardado estructural, borradores
y selección por ruta. Fase 3A usa **0.2.0**, una ampliación compatible con motor
GPS offline y CLI independientes. Se usa `MAJOR.MINOR.PATCH`, conforme a Semantic Versioning.
La entrega del rastreador experimental offline por ruta usa **0.3.0** por añadir
una capacidad compatible nueva. No cambia el algoritmo ni el esquema GPS de 3A.
El visor gráfico independiente añade otra capacidad compatible en **0.4.0**;
no modifica reglas ni versión del algoritmo del rastreador.
**0.4.1** corrige el cambio entre pares reporte–catálogo en una misma ventana,
conservando validaciones y contratos. Se aplica PATCH por ser una corrección compatible.
El analizador OD offline añade una capacidad compatible en **0.5.0** (MINOR), con
algoritmo independiente `od-candidate-offline-0.1.0`. No modifica el rastreador,
el algoritmo conservador 3A o los esquemas SQLite.

`pyproject.toml` es la única fuente de verdad. `version.app_version()` la lee en
el proyecto; en una distribución instalada utiliza los metadatos generados desde
ese mismo proyecto. No existe una constante de versión duplicada en código.
La GUI muestra la versión en título, dashboard y pie lateral. README la refleja
como documentación de la entrega; al publicar una versión debe actualizarse.

- **MAJOR:** cambios incompatibles en contratos públicos o formatos persistentes.
  Requieren política explícita de migración y preservación de datos.
- **MINOR:** capacidades compatibles nuevas, como el guardado sin simulación y
  las consultas estructurales. Durante `0.x`, la API aún puede evolucionar; todo
  cambio incompatible debe describirse y migrarse, sin pérdida silenciosa.
- **PATCH:** correcciones compatibles, mejoras de mensajes y ajustes visuales
  que no cambian el significado del modelo ni agregan capacidades públicas.

La versión de producto es distinta de `PRAGMA user_version` (almacén de perfiles:
2; catálogo GTFS: 1) y de `Result.contract_version` (1). Ninguna identifica la fecha
de los datos GTFS: cada catálogo conserva su hash y procedencia.
El empaquetado final no se realiza en esta fase; deberá reutilizar los metadatos
del proyecto en lugar de introducir otra versión manual.

El motor tiene además una versión de algoritmo independiente (`gps-offline-1.0.0`),
huella SHA-256 del código relevante y parámetros por ejecución. El almacén GPS
usa su propio esquema 1 y ledger de migraciones; no cambia los esquemas de
catálogo ni perfiles. Versiones/huellas distintas nunca sobrescriben resultados
analíticos anteriores. Una nueva capacidad de producto incrementa MINOR; los
cambios de algoritmo deben declarar su versión y conservar su procedencia.
