# Mantenimiento documental — 2026-11-13, producto 0.2.0

## Alcance y resultado

Reorganización documental, sin cambios de aplicación, dependencias, versión,
bases SQLite ni capturas. Fase 3B no iniciada. README pasa a presentación pública
en inglés con requisitos, apertura, capacidades actuales/futuras y límites;
las guías e informes permanecen en español. No se añadieron licencias ni badges.
No hay LICENSE en el inventario de raíz; se explicita la ausencia sin conceder permisos.

Auditoría: README, todos los archivos de docs/, AGENTS, pyproject, requisitos,
scripts, tests y src. No existe .github/ en este checkout. Se buscaron referencias
docs/, nombres de documentos/JSON y consumidores con rg antes de mover archivos.
Duplicación detectada: README mezclaba guías, cifras históricas y reportes de fases;
ahora se enlazan los informes y se separan uso, arquitectura y desarrollo.

## Árbol final

```text
README.md / AGENTS.md
docs/
  INDEX.md
  getting-started/  SETUP.md, USAGE.md
  architecture/    OVERVIEW.md
  development/     IMPLEMENTATION_PLAN.md, VERSIONING.md, VALIDATION.md,
                   DOCUMENTATION_POLICY.md, DOCUMENTATION_MAINTENANCE_REPORT.md
  research/        CROMA_INTEGRATION_DESIGN.md
  archive/
    phases/        siete informes íntegros y screenshots/
    evidence/      INDEX.md, DOCUMENTATION_INTEGRITY.json, DOCUMENTATION_VALIDATION.json
  *.json           originales/rutas de compatibilidad (ver índice de evidencias)
  *.md             enlaces breves de compatibilidad para documentos reubicados
  screenshots/     imágenes originales compatibles con rutas históricas
```

## Archivos movidos

Se usó Move-Item dentro del proyecto para mantener el índice Git intacto; Git puede
detectar renombres de los archivos íntegros. No se hicieron commits ni push.

| Ruta anterior | Ruta canónica | Tratamiento |
| --- | --- | --- |
| docs/CROMA_INTEGRATION_DESIGN.md | docs/research/CROMA_INTEGRATION_DESIGN.md | Bytes idénticos; ruta anterior compatible |
| docs/IMPLEMENTATION_PLAN.md | docs/development/IMPLEMENTATION_PLAN.md | Bytes idénticos; ruta anterior compatible |
| docs/PHASE0_5_REPORT.md | docs/archive/phases/PHASE0_5_REPORT.md | Bytes idénticos; ruta anterior compatible |
| docs/PHASE0_REPORT.md | docs/archive/phases/PHASE0_REPORT.md | Bytes idénticos; ruta anterior compatible |
| docs/PHASE1A_REPORT.md | docs/archive/phases/PHASE1A_REPORT.md | Bytes idénticos; ruta anterior compatible |
| docs/PHASE1B_REPORT.md | docs/archive/phases/PHASE1B_REPORT.md | Bytes idénticos; ruta anterior compatible |
| docs/PHASE2_1_REPORT.md | docs/archive/phases/PHASE2_1_REPORT.md | Bytes idénticos; ruta anterior compatible |
| docs/PHASE2_REPORT.md | docs/archive/phases/PHASE2_REPORT.md | Bytes idénticos; ruta anterior compatible |
| docs/PHASE3A_REPORT.md | docs/archive/phases/PHASE3A_REPORT.md | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2_1-dashboard.png | docs/archive/phases/screenshots/phase2_1-dashboard.png | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2_1-profile.png | docs/archive/phases/screenshots/phase2_1-profile.png | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2_1-route-first.png | docs/archive/phases/screenshots/phase2_1-route-first.png | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2_1-saved.png | docs/archive/phases/screenshots/phase2_1-saved.png | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2_1-settings.png | docs/archive/phases/screenshots/phase2_1-settings.png | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2-dashboard-dark.png | docs/archive/phases/screenshots/phase2-dashboard-dark.png | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2-profile-dark.png | docs/archive/phases/screenshots/phase2-profile-dark.png | Bytes idénticos; ruta anterior compatible |
| docs/screenshots/phase2-settings-light.png | docs/archive/phases/screenshots/phase2-settings-light.png | Bytes idénticos; ruta anterior compatible |
| docs/USAGE.md | docs/getting-started/USAGE.md | Bytes idénticos; ruta anterior compatible |
| docs/VERSIONING.md | docs/development/VERSIONING.md | Bytes idénticos; ruta anterior compatible |

| Actualizado/creado | Finalidad |
| --- | --- |
| README.md | Presentación pública concisa; evita informes completos y cifras sin contexto |
| AGENTS.md | Conserva atribución humana y controles; enlaza política y valida proporcionalmente |
| docs/INDEX.md | Entrada por público y propósito, incluyendo todo el archivo histórico |
| getting-started/SETUP.md | Importación local y requisitos de catálogo para un checkout nuevo |
| architecture/OVERVIEW.md | Componentes, contratos, esquemas e identidad/evidencia vigente |
| development/VALIDATION.md | Comandos con salidas nuevas en data/, no sobre archivos históricos |
| development/DOCUMENTATION_POLICY.md | Fuentes canónicas, cierre, integridad y archivo obligatorios |
| archive/evidence/ | Catálogo lógico, hashes y validación documental de esta tarea |

No se fusionaron ni reescribieron informes de fases. El plan y las otras guías
movidas conservan sus bytes. Los enlaces antiguos Markdown son redirecciones
humanas pequeñas; las imágenes duplicadas son compatibilidad, no nuevas capturas.

## Validación y riesgos

Resultado: 31 Markdown revisados, 109 enlaces locales válidos y 49 archivos
originales con SHA-256 idéntico, incluidos los siete informes y los 30 JSON.
Se comprobaron 11 entradas de comandos y 14 referencias literales únicas de
consumidores. README: 127 líneas. Versión, src/, scripts, tests y dependencias
sin cambios. Los 32 enlaces externos se conservaron sin acceder a la red.

La comprobación local de enlaces, archivos y hashes se registra en
[DOCUMENTATION_VALIDATION.json](../archive/evidence/DOCUMENTATION_VALIDATION.json).
La integridad antes/después, con rutas y hashes individuales, está en
[DOCUMENTATION_INTEGRITY.json](../archive/evidence/DOCUMENTATION_INTEGRITY.json).
No se ejecutó pytest: no se modificaron consumidores ni rutas ejecutables.
Tampoco se ejecutaron instalaciones, GUI, importaciones o proveedores externos.
Los comandos se verifican estáticamente contra módulos/scripts/opciones existentes.

Limitación conocida: los generadores heredados pueden sobrescribir destinos fijos
en docs/. Se conservan para no alterar src/ ni reproducibilidad; usar las opciones
--output cuando existan o realizar una migración autorizada posterior del generador.
URLs externas y referencias a entornos/capturas locales históricas no se comprobaron
por red ni se convierten en requisitos de un checkout. No se declaran vigentes las
condiciones del proveedor ni actuales sus datos. Revisar estos puntos antes de 3B.
