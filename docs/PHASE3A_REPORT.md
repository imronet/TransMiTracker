# Fase 3A — Motor GPS offline

Entrega del **13 de noviembre de 2026, America/Bogota**. Producto **0.2.0**,
algoritmo **gps-offline-1.0.0**, esquema del almacén GPS **1**.
Se autoriza exclusivamente reconstrucción y evaluación offline. **No se declara
validación operativa real ni se inicia Fase 3B.**

## Resultado y alcance

El paquete `src/transmitracker/reconstruction/` procesa lotes guardados, proyecta
observaciones originales sobre geometrías, segmenta discontinuidades, estima
pasos con incertidumbre y calcula duraciones cuando los dos extremos están
justificados. Persiste resultados y rechazos en un SQLite independiente.

La GUI y los servicios de perfiles anteriores no adquieren posiciones ni ejecutan
el motor al abrirse. No hay GPS continuo, predictor, Croma, Telegram, scheduler
ni dependencias nuevas. Las únicas lecturas externas de investigación fueron
documentación/código público; el replay y las pruebas no hicieron HTTP.

## Modelos y procedencia

`models.py` define modelos inmutables para `ProviderSnapshot`,
`OriginalObservation`, `NormalizedObservation`, `IdentityEvidence`,
`CandidateIdentity`, `TrajectorySegment`, `Projection`, `StopEvent`,
`Measurement`, `Rejection`, `Parameters` y `ReconstructionResult`.

Se conserva fuente/endpoint, hash de payload, hash de catálogo, feed_as_of,
reported_at, received_at, vehículo, viaje, ruta, fecha de servicio, inicio original,
coordenadas, parada, secuencia y estado. La observación original conserva JSON
reproducible; el lector PB incluye todos los campos publicados del VehiclePosition
en su representación, además de comprobar el hash del archivo guardado.
IDs originales siguen siendo cadenas.

Los tres tiempos tienen usos distintos: reported_at ordena movimientos; feed_as_of
permite comprobar recencia respecto al feed; received_at solo se registra como tal
si la captura lo verificó. La referencia antigua de inicio de petición se conserva
en `receipt_reference_at`, no se convierte en recepción ni llegada. Timestamps
ausentes no se rellenan a partir de otro reloj. En replay histórico la frescura
se evalúa en el contexto del snapshot, no contra la fecha actual.

El estado Protobuf ausente permanece ausente en el modelo original. Aunque la
[referencia GTFS-RT](https://gtfs.org/documentation/realtime/reference/#message-vehicleposition)
define un valor por defecto, 3A solo usa un estado publicado explícitamente como
soporte adicional para desambiguar una ocurrencia. No transforma el valor por
defecto en una observación independiente del productor.

Cada resultado guarda versión de algoritmo, huella SHA-256 del código relevante,
parámetros, entradas y tramos objetivo. La huella permite distinguir cambios de
código previos a una publicación sin reutilizar resultados de otra implementación.
Datos reales y sintéticos no se mezclan en un lote.

## Identidad y continuidad

La agrupación usa fuente + endpoint + vehicle_id. El descriptor conserva trip_id,
route_id, start_date, start_time original y sentido. Una coincidencia de viaje no
demuestra vehículo/instancia operativa. Tampoco lo hacen cercanía, sufijos o
`start_time` aparentemente estable.

Se reusa el análisis exacto de referencias de Fase 1B: trip existente, ruta,
sentido compatible si se publica, parada/secuencia y servicio activo. No hay
emparejamiento por sufijos ni remapeo difuso. Las referencias exactas y la
continuidad son atributos distintos de `operationally_verified`, que permanece
**false** en todos los resultados de 3A.

En fixtures, una declaración separada del generador vincula vehículo, viaje,
ruta, servicio, inicio, patrón y rango temporal. No contiene horas verdaderas de
cruce. Solo esa identidad sintética y una continuidad suficiente permiten calidad
`synthetic_identity_validated_not_real_operation`. Etiquetar datos como sintéticos
sin aportar esa declaración no basta. Intentar aplicarla a snapshots reales se
rechaza. La verdad de eventos se usa exclusivamente en evaluación.

Cambio de descriptor, inicio sospechosamente cambiante, secuencia regresiva,
desaparición en snapshots completos, hueco excesivo, coordenadas inválidas,
conflicto de timestamp, salto o geometría ambigua cortan continuidad. Un inicio
cambiante no se elimina de la identidad. La desaparición y el final de un archivo
no confirman llegada. Ningún segmento cruza un corte para medir ambos extremos.

Los reportes se ordenan por timestamp GPS, conservando el diagnóstico de orden de
entrada. Un gran retroceso respecto a recepciones verificadas se clasifica como
posible reinicio o reporte retrasado, sin afirmar cuál de ambos ocurrió. Se detecta
también regresión del reloj del feed. Ausencia en snapshots parciales no se trata
como desaparición; el adaptador PB guardado solo acepta snapshots completos.

## Geometría, eventos y mediciones

El motor carga la geometría del patrón asociado al **viaje exacto**, con caché
acotada. Dos patrones de la misma ruta pueden usar formas distintas. La proyección
local usa metros longitudinales y residuales; no desplaza las coordenadas originales.
Las velocidades y distancias se derivan de fixes observados, sin velocidad inicial
ni posición animada supuestas.

Se generan candidatos sobre todos los segmentos de la forma. La secuencia/estado
publicado y el progreso previo pueden descartar ramas imposibles. Si quedan ramas
con residuales semejantes y progreso separado, se rechaza la proyección. No se
elige una por simple cercanía ni se usa un recorrido único para toda una ruta.

Las paradas conservan `(pattern_id, stop_id, sequence)`. Para una parada repetida
se usan distancias publicadas coherentes entre stop_times y shapes cuando existen,
transformando sus unidades a progreso medido, sin asumir que son metros. La
[referencia GTFS estática](https://gtfs.org/documentation/schedule/reference/#stop_timestxt)
exige unidades compatibles y recomienda ese campo en bucles. Sin un anclaje
inequívoco se conserva el rechazo de la ocurrencia.

| Evento | Evidencia/interpretación |
| --- | --- |
| `estimated_crossing` | Fixes antes y después del margen GPS de la ocurrencia; intervalo de cruce y, cuando procede, punto interpolado condicional |
| `observed_stationarity_with_published_stop_status` | Al menos tres fixes estacionarios y estado STOPPED_AT explícito, parada/secuencia coherentes; intervalo de detención observada por muestreo |
| `observed_arrival` | Contrato reservado; no lo produce 3A a partir de GPS |
| `not_determinable` | Falta de extremos o anclaje; razón registrada |

Un cruce no acredita detención, puertas, embarque o llegada observada. La
estacionariedad tampoco proporciona automáticamente su instante de llegada.
`position_kind` distinto de observed impide que una posición visual/extrapolada
se acepte como evidencia GPS.

Para cada cruce se guardan identidad/segmento, ruta/patrón, ocurrencia, límite
inferior/superior, observaciones de soporte, método, incertidumbre, calidad y razón.
Solo se interpola con un bracket corto y velocidades observadas suficientemente
estables. Si no se cumplen las condiciones, `estimated_at` permanece null.
El intervalo es una cota bajo los supuestos/umbrales del modelo, no un intervalo
estadístico calibrado con una probabilidad de cobertura real.

Si origen tiene intervalo `[oL,oU]` y destino `[dL,dU]`, la duración se acota como:

`[max(0, dL-oU), dU-oL]`.

Solo hay estimación puntual si ambos eventos la tienen; también se propaga la
incertidumbre de ambos. Se rechaza si falta un extremo, son segmentos distintos,
el destino no es posterior, hay identidad no verificada o el ancho supera el
límite configurado. Espera y caminata se mantienen en null; no se deducen ni se
suman al tiempo dentro del vehículo. Aceptado significa estimación que pasa los
controles configurados, con calidad sintética explícita, no duración operativa real.

### Parámetros iniciales

Todos son configurables mediante JSON en `replay --parameters`, positivos y finitos.
Son candidatos de diagnóstico; **no están calibrados para operación real**.

| Parámetro | Inicial |
| --- | ---: |
| Recencia máxima | 300 s |
| Tolerancia de reloj futuro | 5 s |
| Hueco máximo continuo | 120 s |
| Velocidad observada máxima | 35 m/s |
| Residual máximo sobre forma | 60 m |
| Empate de residuales / separación de ramas | 5 m / 30 m |
| Retroceso tolerado como ruido | 10 m |
| Margen GPS / error temporal de cada fix | 8 m / 1 s |
| Bracket máximo para interpolación puntual | 40 s |
| Variación relativa de velocidad permitida | 0,2 |
| Mínimo de estacionariedad / radio de parada | 20 s / 15 m |
| Ancho máximo de incertidumbre de duración | 85 s |
| Umbral de retroceso grande del reloj GPS | 120 s |

## Aprendizajes de Paradero

Se revisó el commit `e832ee52781e63db7b0f3b61d5cb281499bb51c8` de
[croma-labs/paradero](https://github.com/croma-labs/paradero).
URLs y hashes están en `PHASE3A_PARADERO_REVIEW.json`.

[`moving-buses.ts`](https://github.com/croma-labs/paradero/blob/e832ee52781e63db7b0f3b61d5cb281499bb51c8/src/lib/moving-buses.ts)
distingue fixes de posiciones dibujadas, anima entre reportes y contempla una
velocidad inicial supuesta de 4 m/s cuando aún no se midió.
[`path.ts`](https://github.com/croma-labs/paradero/blob/e832ee52781e63db7b0f3b61d5cb281499bb51c8/src/transit/path.ts)
contiene proyección y progreso sobre polilíneas. Se tomó la separación conceptual
entre observación y visualización, con una implementación analítica propia.
No se copió ese código al motor ni se ejecutó; tampoco se importaron sus
velocidades iniciales, animaciones o suavizado como evidencia de eventos.

## SQLite y reproducibilidad

Nuevo almacén bajo `data/phase3a/`, separado de catálogo y perfiles. Se niega a
abrir como destino una base de otro tipo antes de modificarla. El esquema 1 usa
`engine_migrations`; versiones desconocidas se rechazan. No se migran bases ajenas.

| Tabla | Contenido |
| --- | --- |
| `batches` | Manifest de IDs de snapshots y hash del lote |
| `snapshots` | Fuente/endpoint, origen, hashes, tiempos y procedencia |
| `originals` / `sightings` | Representación reproducible de observación y apariciones por snapshot/ordinal |
| `runs` | Catálogo, algoritmo/huella, parámetros, objetivos, declaraciones sintéticas y fecha de procesamiento |
| `normalized` | Validación de campos/recencia, separada de asociación operativa |
| `segments` / `projections` | Identidad candidata, continuidad, geometría y movimiento observado |
| `events` / `measurements` | Resultados aceptados/rechazados, intervalos y soporte |
| `rejections` | Incidentes de normalización, asociación, geometría y continuidad |

Índices por proveedor/vehículo/tiempo, snapshots/tiempo, catálogo/versión, identidad/
tiempo, ocurrencia de evento, tramo medido y motivo. La observación original se
deduplica por contenido y proveedor; cada sighting conserva su snapshot. Duplicados
GPS no crean tiempo/movimiento; conflictos al mismo vehículo/timestamp se rechazan
conservando ambas representaciones. IDs de entidad cambiantes no unen vehículos.

La clave de ejecución incluye lote, catálogo, versión y huella del algoritmo,
parámetros, tramos y evidencia. Una ejecución idéntica no reescribe filas; una
configuración/versión distinta conserva resultados anteriores y reutiliza originales.
Las pruebas comprueban reimportación sin cambios, roundtrip de snapshots, integridad
SQLite y un cambio simulado de versión en test. No hay dos algoritmos de producción.
Los resultados de geocerca de la evaluación no se almacenan como mediciones históricas.

Los perfiles se leen explícitamente mediante JSON o SQLite **de solo lectura**.
No se instancia `ProfileStore` para leerlos, pues su apertura podría migrar la base.
Se valida su estructura y hash de catálogo antes de usar sus `Leg` como objetivos.

## Evaluación sintética y línea base

`tests/fixtures/phase3a/scenarios.json` declara **23 escenarios**, con un catálogo
GTFS ficticio reproducible. IDs DEMO, coordenadas y tiempos son sintéticos.
La verdad de cruce se calcula a partir de trayectorias analíticas conocidas y no
se entrega al motor. El escenario con ruido usa perturbaciones deterministas
acotadas; no es una muestra de errores GPS de Bogotá.

La línea base marca el primer fix observado dentro de una geocerca de **80 m**,
sin topología, continuidad ni interpolación. Usa los mismos fixes y catálogo,
no animación. El radio es una elección explícita del benchmark, no un ajuste
óptimo ni una calibración del proveedor.

Se evalúan las primeras tres ocurrencias publicadas de cada patrón; el terminal
fuera del tramo de verdad no se incluye. Un matching puntual admite error de
hasta 30 s; los eventos solo intervalares requieren contener la verdad. Duplicados
de detección o no emparejados son falsos positivos. El rechazo de trayectoria
se mide por vehículo sin una medición aceptada entre las ocurrencias objetivo.
La cobertura se calcula sobre eventos emparejados; el porcentaje de detección
indica por separado los eventos omitidos. Los errores puntuales excluyen los
eventos que solo tienen intervalo.

### Matriz de huecos — trayectoria ideal a velocidad constante

| Hueco | Propuesto: detección | Error absoluto mediano / P90 | Cobertura del intervalo | Falsos positivos | Duración aceptada | Base: detección / error mediano / P90 |
| --- | ---: | --- | ---: | ---: | --- | --- |
| 20 s | 100 % (3/3) | 0 / 0 s | 100 % | 0 | Sí, 70 s; límites 58–102 s | 100 % / 3,5 / 5,9 s |
| 40 s | 100 % (3/3) | 0 / 0 s | 100 % | 0 | Sí, 70 s; límites 38–122 s | 66,7 % / 3,5 / 3,5 s |
| 90 s | 100 % (3/3) | Sin punto estimado | 100 % | 0 | No: ancho de incertidumbre excesivo | 33,3 % / 6,5 / 6,5 s |

En 90 s se preservan tres intervalos; el punto medio solo es un proxy de evaluación
(error mediano 31,5 s, P90 37,1 s) y no se guarda como instante de cruce.
El rechazo de trayectoria es 0/0/100 % respectivamente para el propuesto;
la base no obtiene ambos extremos a 40 ni a 90 s. Los errores cero en los otros
casos corresponden a una trayectoria ideal compatible por construcción con la
interpolación; **no son precisión operativa medida**.

Con ruido sintético acotado: mediana **0,314 s**, P90 **0,426 s**, detección y
cobertura **100 %**, cero falsos positivos. En el bucle con parada repetida, el
propuesto mide **160 s** entre secuencias 10 y 30 del mismo stop_id; la base
produce un falso positivo al reutilizar la primera cercanía para otra ocurrencia.

### Matriz de escenarios — hueco nominal 20 s

| Escenario | Mediciones aceptadas | Resultado principal |
| --- | ---: | --- |
| Normal | 1 | Cruces y duración consistentes |
| Ruido GPS acotado | 1 | Error no nulo medido frente a verdad conocida |
| Dos vehículos / patrones distintos | 2 | Procesamiento simultáneo separado |
| Dos buses de misma ruta y viaje publicado | 2 | Identidades sintéticas distintas por vehículo |
| Duplicados | 1 | Apariciones preservadas, sin movimiento nuevo |
| Fuera de orden | 1 | Orden GPS restaurado, diagnóstico de entrada |
| Salto GPS | 0 | Discontinuidad/velocidad imposible |
| Detenido | 1 | Una estacionariedad observada; cero llegadas observadas |
| Velocidad implausible | 0 | Corte del segmento |
| Cambio de viaje | 0 | Descriptor distinto, sin unir extremos |
| start_time cambiante | 0 | Instancias sin continuidad suficiente |
| Datos antiguos | 0 | Recencia inválida |
| Ausencia temporal | 0 | Desaparición en snapshot completo |
| Bucle / parada repetida | 1 | Ocurrencias 10 y 30 conservadas |
| Cruce con contexto | 1 | Rama resuelta con evidencia de secuencia/continuidad |
| Intersección ambigua | 0 | Proyecciones competidoras rechazadas |
| Medianoche | 1 | Fecha de servicio conservada, horas >24 en GTFS |
| Extremos insuficientes | 0 | No se inventa el evento faltante |
| Retroceso | 0 | No se mide a través del corte |
| Posible reinicio/retraso del reloj | 0 | Rechazo y evidencia temporal conservados |
| Coordenadas inválidas | 0 | Normalización rechazada |
| Conflicto de timestamp | 0 | Ninguna versión se elige silenciosamente |
| Ramal, misma ruta y otra geometría | 1 | Se usa el patrón/viaje exacto |

El propuesto no acepta mediciones en los 12 escenarios declarados inseguros.
Se reportan también candidatos inseguros de la base, sin tratarlos como mediciones
reales. La comparación aporta valor en error puntual, ocurrencias y controles de
evidencia de este conjunto; no demuestra superioridad universal ni calibración
para recorridos reales. La matriz de cadencias usa la trayectoria normal; los
escenarios adversarios se ensayan a 20 s, no todas sus combinaciones posibles.

## Replay real guardado — alcance limitado

Se leyó el PB original de Fase 0 mediante su copia/registro de Fase 1B, verificando
SHA-256. **Una sola captura**, 2.565 observaciones originales. La recepción exacta
no se conocía y permanece null; el timestamp del feed sí se conserva.

Resultado: 30 registros antiguos, 2.351 viajes ausentes del catálogo, 156 conflictos
viaje/ruta y 11 conflictos parada/secuencia. De las 17 referencias restantes,
una proyección fue ambigua y 16 produjeron segmentos **unitarios**. Sus 1.340
resultados de parada son no determinables: no hay pares GPS ni velocidades.
**Cero pasos aceptados y cero mediciones de viaje**. El replay no comprueba la
disponibilidad actual de un endpoint ni la estabilidad real de identidades.

Evidencia: `PHASE3A_REAL_SAVED_REPLAY.json`. Los originales y bases previas se
conservan; `PHASE3A_INPUT_INTEGRITY.json` registra hashes de protección.

## CLI y reproducción

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.reconstruction evaluate --directory data/phase3a/final
.\.venv\Scripts\python.exe -m transmitracker.reconstruction replay --catalog data/phase3a/final/fixtures/synthetic_catalog_v1.sqlite3 --scenario normal --gap 40 --db data/phase3a/offline.sqlite3
.\.venv\Scripts\python.exe -m transmitracker.reconstruction replay --catalog data/catalog/official_20261112.sqlite3 --capture data/phase1b/saved_original/capture.json --db data/phase3a/real_saved_reconstruction.sqlite3 --output docs/PHASE3A_REAL_SAVED_REPLAY.json
```

`--capture` acepta varios registros JSON con PB local y hash, nunca una URL.
`--profile-json` o `--profiles-db ... --profile-id ...` reutilizan tramos estructurales
del catálogo correspondiente. Las rutas permanecen dentro del proyecto y la
base destino se valida como almacén GPS. No hay fallback automático de real a fixture.

La especificación para proveedores y `CreditBudgetManager` está en
`CROMA_INTEGRATION_DESIGN.md`. Los valores 1.500/10/1 provienen del usuario y son
configurables, sin clasificación de endpoints verificada ni cliente implementado.

## Pruebas, compatibilidad y límites

Se conservan los 183 casos previos y se añaden 54 de unidad/integración/replay.
Resultado final en Windows/Python **3.13.14**: **237 aprobadas en 274,91 s**,
sin omisiones; Ruff correcto, **89 archivos** con formato correcto y `pip check`
sin requisitos rotos. No se instalaron dependencias nuevas.
No se modifica lógica de GUI, perfiles ni catálogo. Las pruebas nuevas cubren
escenarios, incertidumbre, múltiples vehículos, tipos ausentes, datos visuales,
identidad real no autorizable por fixtures, almacenamiento idempotente,
reprocesamiento, hashes, perfil leído sin escrituras y CLI sin red.

Una ejecución intermedia obtuvo 236 aprobadas y un error al inicializar Tcl de
WindowsApps en un test GUI anterior (`tcl_findLibrary`). Se añadió aislamiento
de proceso por caso GUI en Windows en `tests/conftest.py`, conservando todas las
aserciones, reaperturas y el bloqueo de red del hijo. No se omiten ni reintentan
tests; un fallo del hijo falla el caso padre. Los temporales quedan en directorios
verificados de `.cache/gui-workers`. No se cambió el runtime externo ni la GUI.
El registro inicial se conserva en `PHASE3A_VALIDATION_INITIAL_FAILURE.json`.

Otra ejecución comenzó mientras una anterior seguía usando `.cache/pytest` y
obtuvo 165 aprobadas/72 errores de preparación por archivos SQLite bloqueados
(`WinError 32`), conservados en `PHASE3A_VALIDATION_TEMP_COLLISION.json`. El
verificador ahora asigna un directorio UUID por ejecución bajo `.cache/verification`
y los hijos GUI incluyen el PID del padre en su directorio. No se eliminan
temporales de otras ejecuciones ni se alteran aserciones para evitar el error.
El resultado final completo se conserva en `PHASE3A_VALIDATION_RESULTS.json`.

```powershell
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE3A_VALIDATION_RESULTS.json
```

Archivos nuevos: once módulos de `reconstruction/`, dos módulos de pruebas,
fixtures declarativos, este informe, diseño de créditos y evidencias JSON.
Modificados: versión en pyproject/README/VERSIONING, adenda del plan, conftest
para aislamiento de ventanas y verificador para temporales exclusivos por
ejecución. No se crearon commits ni se cambiaron autores.

Límites técnicos: geometría local y umbrales no calibrados; no se optimizan
trayectorias mediante un modelo probabilístico global; los cruces sin evidencia
inequívoca se rechazan; los intervalos dependen de márgenes y continuidad; un
snapshot aislado no permite velocidad o viaje; no hay verificación de puertas,
embarque o llegada real. El batch actual es en memoria y no es un colector de
producción ni una solución de retención ilimitada.

Antes de 3B se requieren autorización, condiciones/cuotas/costes aplicables,
verificación independiente de identidad, serie real acotada permitida y verdad
de referencia para calibrar errores/intervalos. La agrupación visual por estación
y andén queda como mejora futura. **Fase 3B no iniciada.**
