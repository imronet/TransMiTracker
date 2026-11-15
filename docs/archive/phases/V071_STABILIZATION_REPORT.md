# TransMiTracker 0.7.1 — cierre consolidado de estabilización

Fecha: 2026-11-14 (Bogotá). Base: `03a2f3d15268cd4452eff9306cd96c3ce044ae77`.
Estado: **lista para QA independiente, pendiente de aceptación del propietario**.
PATCH compatible de la capacidad existente; no inicia otra fase ni el Camino B.

## Resumen ejecutivo

Se corrigieron el estado histórico del dashboard, la traducción de campos/códigos,
la jerarquía de resultados, la ayuda de ventana y las advertencias peatonales.
La consulta negativa ahora entrega contexto y evidencia separada de la recomendación.
Una alternativa completa tardía solo aparece como **descartada**, con sus tramos,
conexiones, caminatas, margen y diferencia respecto al límite. Si falta una cadena
completa, no se atribuye una llegada de un tramo aislado al recorrido personal.

Se validaron 117 casos distintos, incluidos 11 casos con Tk real. Ruff, formato y
`pip check` correctos. No se ejecutó toda la suite. Se revisaron visualmente 20 PNG
sintéticos en temas claro/oscuro, con desplazamiento y tamaños 1180×820/900×650.
Los perfiles personales produjeron resultados negativos fundamentados, sin cambios
en sus bytes. No se exige obtener una hora que el catálogo o los ajustes no permiten.

## Matriz de cierre de Manual QA

| Hallazgo original | Modificación | Prueba/evidencia | Resultado |
| --- | --- | --- | --- |
| Dashboard muestra Fase 2.1 | Título, sidebar y dashboard leen `app_version()`; textos vigentes | Tests de versión/sidebar; capturas dashboard de ambos temas | Verificado |
| Diseño poco claro | Tarjeta de resultado principal; detalle por tramo, tolerancias y procedencia; scroll | Tests positivos/negativos, navegación y 20 capturas | Verificado en tamaños y temas indicados |
| Advertencia peatonal confusa | Primer/segundo transbordo, tramos conectados, caminata y tolerancia; no implica imposibilidad | Test de dos tramos y tarjetas de advertencia | Preservada, informativa y legible |
| Código TRANSFER_PATH_UNVERIFIED visible | Traducción central de códigos y campos; sección técnica opcional | Scan de etiquetas principales y apertura de detalle técnico | Sin códigos internos en la vista principal |
| ARRIVAL_DEADLINE_EXCEEDED poco explicativo | Contexto tipado y cadena descartada solo si es completa | Tests de 1/2/3 tramos, límite exacto, tardanza y cadena incompatible; consulta real | Verificado; sin falsa llegada final |
| departure_window_minutes confuso | Etiqueta «Ventana de búsqueda de buses programados (minutos)», ayuda por sentido y horizonte efectivo | Tests de editor/ayuda, resultado y caso de caminata fuera de ventana | Verificado; no se modifica automáticamente |
| Regreso personal sin validación completa | Consulta con la hora habitual realmente guardada, sin inventar otra | Ejercicio local privado + flujos sintéticos con segundos/microsegundos | Negativo por horizonte: la caminata inicial excede la ventana. Explicación disponible; no hay itinerario positivo personal demostrado |

## Diagnóstico y contratos

`StaticPlanner.plan()` conserva las decisiones y el contrato previo.
`consult()` añade `PlanningResult`, subtipo de `Result[StaticPlan]`, con diagnóstico
opcional. Los campos previos y códigos no cambian; un fallo mantiene `ok=False`
y `data=None`. Solo la serialización de esta consulta incorpora `diagnostic`.
No se modifica el `Result` base, el esquema SQLite ni el guardado de perfiles.

La búsqueda inversa y la construcción de pasos se extraen para reutilizarlas.
En un fallo por límite se permiten como máximo tres consultas diagnósticas
adicionales (una por tramo), dentro del mismo horizonte original. Se buscan cadenas
completas ignorando **solo para el diagnóstico** el filtro final de llegada. Se
presenta la que tiene menor llegada final, con desempate determinista. No se utiliza
como recomendación ni se relajan estructura, calendario, secuencia o transbordos.

Las alternativas sin horas explícitas no se rellenan. Las fechas de servicio,
horarios >24, frecuencias y calendarios siguen siendo responsabilidad del catálogo.
Una restricción de ventana no se traduce como ausencia de buses en todo el sistema.
Las advertencias y resultados de regreso conservan la precisión de la hora guardada.

La validación detectó además escrituras redundantes al abrir `ProfileStore`: se
reasignaba `user_version=2` incluso cuando ya era 2. Ahora solo se asigna cuando
corresponde; la migración existente desde 1 se conserva. Las consultas de nombres
asociadas a un catálogo usan el lector de perfiles existente. Las pruebas comprueban
bytes de base, preferencias y catálogo antes/después de consultar y navegar.

## Validaciones y reproducción

Desde la raíz con el entorno existente y `PYTHONPATH=src`, `PYTHONUTF8=1`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m 'not gui' tests/test_stabilization.py tests/test_static_planning.py tests/test_planning_gui.py tests/test_gui_controller.py tests/test_phase2_1.py
.\.venv\Scripts\python.exe -m pytest -q -m gui tests/test_stabilization.py tests/test_planning_gui.py tests/test_gui_widgets.py
```

Se separan servicios y Tk por las particularidades del ejecutor Windows existente.
Comandos exactos, XML utilizados, conteos sin duplicados y huellas en la
[evidencia consolidada](../evidence/V071_STABILIZATION_VALIDATION_20261114.json).

| Ejecución | Resultado observado |
| --- | --- |
| Primera validación sin GUI | 104 aprobadas |
| Regresión de integridad, controlador y borradores después de corregir aperturas | 52 aprobadas; solapa casos anteriores |
| Regresión GUI después de corregir integridad | 10 aprobadas; falló la reapertura de un segundo Tk en el mismo proceso |
| Explicación específica de caminata fuera de ventana | Aprobada |
| Guardar → cerrar → reabrir en proceso nuevo | Aprobada, manteniendo todas las aserciones originales |
| Total de casos distintos con resultado satisfactorio | **117**, incluidos **19 nuevos** y **11 GUI** |
| Calidad | Ruff, formato de 12 archivos Python y `pip check`: correctos |

No se ocultan los fallos iniciales: seis pruebas detectaron la escritura redundante
del almacén, corregida antes del cierre. El runtime WindowsApps falló intermitentemente
al inicializar un segundo Tk, aunque los archivos Tcl existían. Una copia local de
las mismas bibliotecas no eliminó por sí sola el problema. La prueba de reapertura
ahora hace un reinicio normal en proceso nuevo, sin skips, mocks de widgets ni
reintentos; conserva revisión, destino, fecha y hora guardados. La primera ejecución
de ese subproceso requirió corregir su ruta de importación `src`.

Para la comprobación gráfica se usaron copias de los scripts Tcl/Tk instalados bajo
`.cache/tk-runtime` y variables `TCL_LIBRARY`/`TK_LIBRARY`; no son dependencias nuevas
ni archivos que deban publicarse. La comparación de huellas se registra en la evidencia.

Preparación de ese entorno de QA, sin descargas:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
$pythonBase = & .\.venv\Scripts\python.exe -c "import sys; print(sys.base_prefix)"
$localTcl = Join-Path (Get-Location).Path '.cache\tk-runtime'
if (-not (Test-Path -LiteralPath $localTcl)) {
    Copy-Item -LiteralPath (Join-Path $pythonBase 'tcl') -Destination $localTcl -Recurse
}
$env:TCL_LIBRARY = Join-Path $localTcl 'tcl8.6'
$env:TK_LIBRARY = Join-Path $localTcl 'tk8.6'
```

### Smoke visual sintético

```powershell
.\.venv\Scripts\python.exe scripts/smoke_stabilization.py --directory data/pilots/smoke-NEW --screenshots docs/archive/evidence/screenshots/smoke-NEW
.\.venv\Scripts\python.exe scripts/smoke_stabilization.py --directory data/pilots/smoke-extra-NEW --screenshots docs/archive/evidence/screenshots/smoke-extra-NEW --additional-views
```

Los directorios deben ser nuevos y permanecer dentro del proyecto. El script genera
GTFS y perfiles sintéticos, abre widgets reales y bloquea red. Captura únicamente
el HWND de la ventana mediante `PrintWindow`; la conversión PNG usa .NET de Windows,
sin instalar Pillow. La generación de imágenes no equivale a revisión visual: en
esta entrega se inspeccionaron las 20 imágenes generadas correctamente.

Ejemplos: [dashboard claro](../evidence/screenshots/stabilization-071-20261114/light-dashboard.png),
[detalle positivo oscuro](../evidence/screenshots/stabilization-071-20261114/dark-positive-detail.png),
[negativo y restricción](../evidence/screenshots/stabilization-071-20261114/light-negative.png),
[itinerario descartado](../evidence/screenshots/stabilization-071-20261114/dark-negative-detail.png),
[regreso, campos inferiores](../evidence/screenshots/stabilization-071-20261114/additional/dark-return-editor-lower.png),
[ventana 900×650](../evidence/screenshots/stabilization-071-20261114/additional/light-positive-small.png).
La lista completa y sus SHA-256 están en la evidencia. No se observaron superposiciones
o etiquetas cortadas dentro de los formularios; el contenido que sale del viewport
es accesible por desplazamiento. Se verificaron estados positivos, negativos y avisos.

Las primeras capturas de escritorio no correspondían a la ventana: se retiraron de
la ubicación pública y no se cuentan como evidencia visual. Un intento adicional
parcial se conservó en privado; se corrigió el modo de vistas adicionales para que
no ejecutase otra consulta negativa que no producía una captura requerida.

## Ejercicio personal e integridad

Se leyeron los dos perfiles existentes con su catálogo local y una fecha en la que
el perfil y sus servicios de patrón estaban activos. No se cambiaron tramos, fechas
guardadas, tolerancias, límites, salida habitual o ventana para forzar un resultado.

- Ida: `ARRIVAL_DEADLINE_EXCEEDED`, con contexto diagnóstico. La búsqueda no demuestra
  una cadena completa descartada; identifica el primer transbordo como impedimento
  al intentar encadenar las alternativas. No se publica una llegada final personal.
- Regreso: se utilizó su hora habitual existente. Resultado `HORIZON_INSUFFICIENT`:
  la caminata inicial termina después de la ventana configurada. No es una prueba
  de ausencia de buses. Una prueba sintética cubre expresamente esta explicación.

Detalle, payloads y huellas personales únicamente en
`data/pilots/stabilization-real-20261114/results.json`, excluido de Git. El JSON
público contiene solo códigos y agregados no identificables. Los bytes de perfiles,
preferencias y catálogo coinciden antes/después. No se hicieron solicitudes de red,
capturas GPS ni consultas a Croma. Motor 3A, rastreador, visor y OD permanecen intactos.

## Criterios de aceptación y límites residuales

Los criterios 1–17 del encargo se corresponden con: versión/textos (1–2), mensajes y
avisos (3–4), ventana y estados negativos (5–6), diagnóstico y ausencia de horas
fabricadas (7–8), flujos ida/regreso (9–10), navegación y reinicio (11), integridad
(12), calidad (13), imágenes inspeccionadas (14), documentación/versionado (15),
reproducción sintética (16) y matriz anterior (17). Cada grupo tiene prueba o evidencia
concreta; no se considera que un resultado personal negativo sea una aprobación operativa.

- **Defectos funcionales conocidos pendientes en los escenarios autorizados:** ninguno
  reproducido tras las correcciones y comprobaciones indicadas. La revisión independiente
  puede detectar otros casos; esta entrega no se autoaprueba.
- **Entorno:** múltiples raíces Tk sucesivas en un mismo proceso WindowsApps mostraron
  fallos de carga de Tcl. Se verificó el flujo normal de reinicio en proceso nuevo;
  no se garantiza ese uso artificial de múltiples intérpretes.
- **GTFS estático:** no garantiza puntualidad, disponibilidad, conectividad peatonal
  ni horarios fuera del catálogo/horizonte. Frecuencias sin horas exactas siguen
  indeterminadas. Una cadena descartada no es una duración operativa validada.
- **Intervención del propietario:** revisar los ajustes del regreso si desea buscar
  una alternativa admisible; la aplicación no los corrige automáticamente. No hay
  una recomendación personal positiva demostrada en este ejercicio.
- **Futuro:** GPS adicional, Camino B, estadísticas históricas, predictor, Croma,
  Telegram y scheduler permanecen fuera de alcance y sin autorización.

No hay commit ni push de esta entrega. La aceptación del prototipo y la autorización
de cualquier fase posterior corresponden al propietario.
