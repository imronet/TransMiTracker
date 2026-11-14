# Arquitectura vigente — 0.5.0

## Componentes y límites

| Paquete en src/transmitracker/ | Responsabilidad |
| --- | --- |
| gtfs/, providers/, diagnostics.py | Lectura GTFS/Protobuf y diagnóstico explícito; un diagnóstico live sí usa red |
| catalog/ | Importación por lotes y consultas SQLite del catálogo estático inmutable |
| profiles/ | Modelos, contratos, validación estructural/temporal y persistencia de perfiles |
| gui/ | CustomTkinter, controlador y trabajador de datos locales; sin adquisición al navegar |
| research/ | Experimentos y diagnóstico acotado, separados de un colector de producción |
| viewer/ | Visor independiente de reportes GPS offline; modelos visuales y Canvas local |
| reconstruction/ | Motor GPS experimental por lotes y replay exclusivamente offline |

La GUI reutiliza servicios de dominio; consultas SQLite usan conexiones propias.
Los widgets permanecen en el hilo Tk. Perfiles con uno a tres tramos conservan
patrón, ocurrencias y hash de catálogo. Calendarios, medianoche y horas >24 son
programación estática. Caminatas del usuario no prueban conectividad espacial.

## Almacenamiento y versiones independientes

| Almacén | Esquema | Política |
| --- | ---: | --- |
| Catálogo GTFS | 1 | IDs originales como texto, hash/procedencia; nueva versión en otro archivo |
| Perfiles | 2 | Revisiones, borradores y consultas; no remapeo silencioso de catálogos |
| Evidencia GPS | 1 | SQLite separado, ledger de migraciones, originales y ejecuciones reproducibles |

Producto: fuente única en `pyproject.toml`. Algoritmo GPS: `gps-offline-1.0.0`,
con huella de código y parámetros por ejecución; su versión no es la del catálogo.
Véase la [política de versiones](../development/VERSIONING.md).

## Reconstrucción GPS offline

Se separan fuente/endpoint, tiempos de feed, reporte y recepción, y originales de
normalización/proyección. Campos ausentes permanecen ausentes. Cambios de descriptor,
start_time, huecos, saltos y ambigüedad cortan continuidad. No se empareja por sufijo
de trip_id ni por proximidad. Los patrones y las ocurrencias repetidas se conservan.

Las posiciones observadas se separan de animaciones/extrapolaciones. Los cruces
usan soporte antes/después y conservan incertidumbre; no se convierten en llegadas
observadas. Solo extremos justificados del mismo segmento permiten una duración.
Espera y caminata no se infieren. Identidad candidata no es identidad operativa
verificada; 3A no autoriza mediciones reales mediante declaraciones sintéticas.

La clave de ejecución incluye lote, catálogo, algoritmo/huella, parámetros,
objetivos y evidencia. Una ejecución idéntica reutiliza resultados; versiones
diferentes preservan los anteriores. El batch en memoria no es un colector continuo.

Los detalles de campos, umbrales y resultados están en el
[informe 3A](../archive/phases/PHASE3A_REPORT.md); sus métricas son históricas y
sintéticas. El [diseño de proveedores y créditos](../research/CROMA_INTEGRATION_DESIGN.md)
es futuro. No hay cliente Croma, predictor, Telegram operativo ni scheduler.

## Rastreador experimental por ruta (3B, aislado)

`research/route_tracker.py` añade una CLI offline sobre sesiones guardadas.
Reutiliza lectura de PB con hashes, `Catalog` en lectura y utilidades geométricas;
no cambia los criterios conservadores anteriores. Agrupa por fuente/vehículo,
selecciona ruta exacta y trata viaje/start_time como auxiliares. Corta enlaces
ante discontinuidades y conserva todos los patrones de cada shape candidato.
No consulta calendarios ni verifica identidad física o eventos de servicio.
El reporte completo solo puede escribirse bajo `data/pilots`, en un archivo nuevo;
la consola emite conteos. [Contrato de uso y estados](../getting-started/OFFLINE_ROUTE_TRACKER.md).

El visor `viewer/` lee el JSON del rastreador; `data.py` valida pertenencia de
observaciones a segmentos y prepara dataclasses inmutables sin Tk. `app.py`
dibuja GPS observados y uniones visuales, sin recalcular trayectorias o métricas.
Consulta todos los shapes/patrones de la ruta en SQLite de solo lectura, cotejando
la versión GTFS registrada cuando está fijada en el reporte. No selecciona una
alternativa geométrica ni usa interpolación. No importa widgets de la GUI principal,
no escribe perfiles y no inicia adquisiciones. El control temporal avanza por
observaciones originales en orden de captura; las regresiones no se ocultan.

## Análisis OD candidato, separado de la aceptación operativa

`research/od_analyzer.py` consume el JSON existente del rastreador, reutiliza la
validación de pertenencia/orden del visor y construye un `Leg` con consultas del
catálogo. Un adaptador usa `GeometryCatalog`, `select_projection`, `crossing_events`
y `measure` sin modificar 3A. La plantilla GTFS de un patrón no se empareja con un
viaje Realtime; las anotaciones de anclas deben ser consistentes entre plantillas.

Cada evaluación queda dentro de un segmento existente y siempre usa confianza
candidata, incluso con fixtures. La aceptación operativa de 3A permanece falsa.
La nueva capa distingue soporte de cruce, orden temporal e intervalo admisible,
manteniendo los límites conservadores y sin resolver variantes por proximidad.
JSON privado exclusivo en `data/pilots`; sin persistencia adicional o integración
con GUI/perfiles. [Contrato, comandos y límites](../getting-started/OFFLINE_ROUTE_TRACKER.md#análisis-experimental-origendestino-050).
