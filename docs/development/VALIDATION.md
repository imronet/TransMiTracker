# Validación y replay local

Ejecute desde la raíz con PYTHONPATH=src y PYTHONUTF8=1, como en el README.
Los resultados anteriores están en el [catálogo histórico](../archive/evidence/INDEX.md).
No sobrescriba esos JSON con otra ejecución. Los comandos siguientes escriben
en data/, excluido de Git; elija un nombre nuevo para cada ejecución.

```powershell
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output data/validation-NEW-RUN.json
# Solo ventanas Tk reales:
.\.venv\Scripts\python.exe -m pytest -m gui -q
# Servicios y controladores sin ventanas:
.\.venv\Scripts\python.exe -m pytest -m 'not gui' -q
```

El verificador ejecuta pytest, Ruff, formato y pip check. La suite bloquea red;
el verificador usa temporales exclusivos en .cache/verification y los casos GUI
en Windows usan procesos separados. La última validación registrada en 3A fue
237 aprobadas; no representa una ejecución en esta tarea documental.

## Motor GPS sintético

```powershell
.\.venv\Scripts\python.exe -m transmitracker.reconstruction evaluate --directory data/replay-NEW-RUN --output data/replay-NEW-RUN/evaluation.json
.\.venv\Scripts\python.exe -m transmitracker.reconstruction replay --catalog data/replay-NEW-RUN/fixtures/synthetic_catalog_v1.sqlite3 --scenario normal --gap 40 --db data/replay-NEW-RUN/replay.sqlite3 --output data/replay-NEW-RUN/summary.json
```

El catálogo y la verdad son sintéticos. Para capturas antiguas locales, replay
acepta --capture con registros JSON/PB verificados y --catalog con su catálogo.
No descarga datos ni hace fallback a fixtures. --profile-json o --profiles-db
con --profile-id leen perfiles explícitamente; SQLite es de solo lectura y debe
coincidir el hash de catálogo. Los argumentos completos y escenarios están en
el [informe 3A](../archive/phases/PHASE3A_REPORT.md).

## Herramientas heredadas

Los scripts de análisis/demo de fases previas están documentados en sus informes.
Algunos leen/escriben rutas fijas de docs/; no ejecutarlos para renovar resultados
archivados. scripts/research_sources.py, research_phase0_5.py y el diagnóstico
--live sí consultan fuentes externas: no son parte de una validación documental.
scripts/build_fixtures.py regenera fixtures sintéticos, no evidencia real.
