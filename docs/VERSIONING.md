# Política de versiones

La versión declarada antes de Fase 2.1 era **0.0.1**, comprobada en `pyproject.toml`.
Esta entrega usa **0.1.0** por la ampliación del guardado estructural, borradores
y selección por ruta. Se usa `MAJOR.MINOR.PATCH`, conforme a Semantic Versioning.

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
