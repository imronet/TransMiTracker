# Fase 0.5 — Históricos operativos y snapshots de flota

## Conclusión y recomendación

**No se encontró un archivo histórico operativo público verificable** que permita
descargar por fecha trayectorias GPS o eventos de parada de TransMilenio/SITP en
las fuentes consultadas. Esto expresa el resultado y alcance de la búsqueda,
no una prueba de inexistencia universal ni de ausencia de históricos internos.
Los archivos GTFS estáticos fechados sí existen; contienen programación, no
ejecución observada. No sustituyen un histórico operativo.

Recomiendo un **colector de snapshots completos de posiciones, compartido entre
perfiles, con procesamiento por lotes y persistencia filtrada**. Reduce consultas
duplicadas y permite observar varios vehículos, pero medir duraciones todavía
exige reconstruir identidades y trayectorias por vehículo dentro del lote.
Los problemas de IDs detectados impiden considerarlo listo para tracking fiable.
Antes hay que validar la semántica del productor y la asociación al recorrido.

Esta entrega contiene investigación y experimentos offline. No activa colector,
scheduler, GUI, Telegram ni servicios de Fase 1. **La Fase 1 sigue sin autorización.**

## Evidencia, fechas y alcance de la investigación

Consultas documentales del **12-11-2026, 22:20–22:22, America/Bogota (UTC−05:00)**.
El análisis operativo reutiliza exclusivamente las capturas reales del mismo día
a las **21:57** guardadas en Fase 0, verificando sus SHA-256 originales.
No se descargaron posiciones o TripUpdates nuevos ni se ejecutaron sondeos.

| Fuente oficial | Verificación y resultado | Alcance |
| --- | --- | --- |
| [Portal GTFS y manifiesto](https://gtfs.transmilenio.gov.co/manifest.json) | GET 200; publicación de los archivos actuales | No publica allí un índice histórico por fecha |
| [Datos Abiertos Bogotá, organización TransMilenio](https://datosabiertos.bogota.gov.co/api/3/action/package_search?fq=organization:transmilenio&rows=1000) | GET 200; 34 conjuntos revisados por metadatos y recursos | Catálogos, infraestructura, validaciones, salidas de usuarios y GTFS |
| [Búsqueda GPS](https://datosabiertos.bogota.gov.co/api/3/action/package_search?q=GPS&rows=100) y [tiempos de viaje](https://datosabiertos.bogota.gov.co/api/3/action/package_search?q=tiempos%20viaje&rows=100) | GET 200; cuatro resultados por consulta | Ningún recurso operativo utilizable identificado; encuestas no equivalen a AVL |
| [ArcGIS de TransMilenio](https://www.arcgis.com/sharing/rest/search?f=json&q=orgid%3A9unqgkQ8KCOfnzoB%20%28GPS%20OR%20posiciones%20OR%20viaje%20OR%20velocidad%20OR%20GTFS%29&num=100&sortField=modified&sortOrder=desc) | GET 200; 184 resultados, dos páginas, `nextStart=-1` al terminar | Búsqueda por esos términos dentro de la organización; no es inventario universal |
| [Catálogo nacional](https://api.us.socrata.com/api/catalog/v1?search_context=www.datos.gov.co&q=transmilenio&limit=100) | GET 200; 40 resultados | Principalmente referencias federadas, infraestructura y pasajeros |
| [Observatorio de Movilidad](https://observatorio.movilidadbogota.gov.co/indicadores-movilidad/tiempos-de-viajes-por-minutos) | Página consultada; indicador de tráfico mixto y publicación anual | No son tiempos observados de bus entre paradas |

El resultado ArcGIS `VOLUMENES_VELOCIDAD` se inspeccionó en su
[metadato de servicio](https://services5.arcgis.com/9unqgkQ8KCOfnzoB/arcgis/rest/services/service_e89aa66a98be4ad5b990d83fb91648a7/FeatureServer?f=json).
Su configuración declara `allowAnonymousToQuery=false` y capacidades de captura
de formulario; no se descargaron registros ni se intentó eludir acceso.
El título no demuestra un archivo abierto de GPS. `Conexion operacional` y
`Retorno operacional` son capas geográficas según sus metadatos, no bitácoras.
Los conjuntos de validaciones y salidas de pasajeros tampoco demuestran eventos
de llegada de buses. No se afirma haber validado los cuerpos de todos esos recursos.

Se descargó **un único archivo estático histórico publicado**:

- [GTFS_20261027.zip](https://storage.googleapis.com/gtfs-estaticos/GTFS_20261027.zip),
  publicado en el [ítem oficial ArcGIS](https://www.arcgis.com/home/item.html?id=6d0043cf1ba443a699bad973539a1422).
- HTTP 200, consulta 22:22:24; 119.305.053 bytes; `Last-Modified` 27-10-2026.
- SHA-256 `f72c48df3d6461663dc0d47f2ba06191b6943ab9f37e5a1ed95fd73a4df7be12`.
- Se leyeron y compararon rutas, viajes, paradas, calendarios, frecuencias y
  `feed_info`. Los miembros son tablas GTFS de programación. `feed_info` indica
  vigencia anual 2026 y `feed_version=1`, como el archivo del 12 de noviembre.
  Esa fecha del nombre/objeto no representa fechas de eventos de operación.

Por tanto, el enfoque de histórico remoto queda **no validado para este uso**.
Una futura fuente candidata debe aportar contenido descargable, fechas de
servicio/evento comprobables, IDs enlazables, cobertura y licencia. Un anuncio,
un nombre de archivo o un tablero agregado no satisface ese criterio.

## Distribución temporal real

Referencia: instante de descarga original de cada feed, no la hora del replay.
Las cabeceras eran del 12-11-2026 a las 21:56:56. Los intervalos siguientes usan
300 s como umbral diagnóstico, sin convertirlo en garantía de calidad.

| Antigüedad de la entidad | Posiciones | TripUpdates |
| --- | ---: | ---: |
| Hasta 5 minutos | 2.535 | 426 |
| Más de 5 y hasta 30 minutos | 2 | 2.911 |
| Más de 30 minutos y hasta 2 horas | 7 | 9.684 |
| Más de 2 y hasta 6 horas | 15 | 18.899 |
| Más de 6 y hasta 24 horas | 1 | 52.372 |
| Más de 1 y hasta 7 días | 2 | 0 |
| Más de 7 días | 3 | 0 |
| **Total** | **2.565** | **84.292** |

Posiciones: timestamp mínimo **03-09-2026 08:49:59**, máximo **12-11-2026 21:56:10**.
Hay 2.560 observaciones fechadas el 12 de noviembre y una en cada fecha:
03/09, 25/09, 19/10, 06/11 y 09/11. Son puntos antiguos aislados conservados
en un snapshot; no una serie temporal de cada vehículo.

TripUpdates: todos sus timestamps son del **12-11-2026**, de **00:12:11** a
**21:56:01**. La mediana de antigüedad es unos **30.878 s / 8,58 h**.
La captura contiene actualizaciones de distintas horas del día, pero no
posiciones ni secuencias de eventos de parada.

Campos realmente presentes en los **83.866 TripUpdates con más de cinco minutos**:

| Campo | Entidades que lo contienen |
| --- | ---: |
| `trip.trip_id`, `trip.route_id`, `trip.start_date`, `trip.start_time`, `trip.schedule_relationship` | 83.866 cada uno |
| `timestamp` y `delay` | 83.866 cada uno |
| `vehicle.id`, `vehicle.label`, `vehicle.license_plate` | 38.111 cada uno |
| `stop_time_update` | **0** |

En el conjunto completo, los 84.292 incluyen `delay`: 12.588 ceros, 39.874
positivos y 31.830 negativos, con rango −9.090 a 21.992 segundos. Es desviación
de programación a nivel de viaje, **no duración observada ni hora de llegada**.
La [referencia GTFS-RT](https://gtfs.org/documentation/realtime/reference/)
distingue generación del feed, medición de posición, actualización de progreso
y eventos de parada. De `TripUpdate.timestamp` no puede recuperarse una llegada.
Tampoco sumar un `delay` genérico a horarios produce un histórico medido.

Hay **72.875 actualizaciones SCHEDULED sin `stop_time_update`**, contrarias al
requisito semántico condicional documentado para ese estado. Aclara la conclusión
de Fase 0: eran mensajes Protobuf interpretables por el lector mínimo; eso no
certificaba validez semántica completa. No se cambia silenciosamente su contenido.

## Investigación de las 30 coincidencias

Se conservaron IDs como cadenas, sin normalizar ni recortar sufijos.

| Resultado de posiciones frente a estático | ZIP del 12/11 | Archivo del 27/10 |
| --- | ---: | ---: |
| Viaje y ruta consistentes | 30 | 35 |
| `trip_id` existe pero su ruta difiere | 159 | 236 |
| `trip_id` ausente | 2.376 | 2.294 |
| `route_id` existe | 2.565 | 2.321 |
| `stop_id` existe | 2.451 | 2.448 |

**Versiones:** cambiar a la versión anterior no resuelve el problema. Entre
ambos estáticos hay 104.842 IDs de viaje comunes y ninguno cambia su `route_id`.
Sin embargo, no se probaron todas las versiones posibles: no se descarta toda
desalineación temporal. Realtime no incluye `feed_version`; los dos estáticos
declaran `1`. Hay que preservar hash y procedencia para distinguirlos.

**Calendario:** los 189 viajes encontrados en el estático del 12/11 tienen
servicio activo para la fecha declarada, incluidas las 159 rutas conflictivas.
Filtrar por servicio activo no repara esos conflictos ni crea los viajes ausentes.
No se verificó que todo vehículo estuviera dentro de una ventana de salida
concreta; actividad del calendario e identidad de instancia son cosas distintas.

**Identificadores y productor:** en las **2.565 posiciones**, `start_time` es
exactamente la hora local del timestamp GPS y `start_date` su fecha local.
Es una correlación observada, compatible con que esos campos estén siendo
rellenados con la hora del reporte. **Una sola captura no prueba cómo cambian
entre snapshots ni autoriza a ignorarlos como regla de emparejamiento.**

Solo 181 posiciones tienen sufijo de `trip_id` igual a su `route_id`, frente a
181.056 de 181.070 viajes estáticos. Es un diagnóstico de formato, no una regla
de unión: no se extrae la ruta del sufijo para sustituir campos contradictorios.

Hay 131 IDs de viaje presentes en ambos feeds Realtime: en 111 difiere la ruta,
en los 131 difiere `start_time`, en dos la fecha y solo en tres coincide el
vehículo. No hay ambigüedad por duplicación de `trip_id` en esos TripUpdates.
**Compartir `trip_id` no prueba compartir instancia operativa** cuando otros
descriptores difieren. Esta evidencia apunta a semántica/identificadores del
productor por aclarar; no identifica una causa única ni una corrección segura.

Falta confirmación del productor y una muestra temporal acotada que permita
validar estabilidad de descriptores. No se la sustituye por heurísticas ni se
inició esa recolección durante esta fase.

## Arquitectura propuesta

```mermaid
flowchart LR
    A[Un GET compartido de positions.pb] --> B[Validar y medir frescura]
    B --> C[Filtrar rutas y corredores relevantes]
    C --> D[Identidad y asociación al catálogo versionado]
    D --> E[SQLite: observaciones y procedencia]
    D --> Q[Cuarentena de ambigüedades]
    E --> F[Procesar trayectorias de varios vehículos]
    F --> G[Eventos estimados y mediciones con confianza]
```

El colector sería único por proveedor y proceso. Las cuatro sesiones diarias
originales pasan a ser ventanas de interés para las mediciones, preservando sus
horarios, separación inicial de 2 h 30 min y configuración. Los perfiles pueden
compartir un snapshot. La selección individual permanece como estrategia de
análisis/compatibilidad, sin duplicar descargas completas por vehículo.

Flujo futuro, aún no implementado como servicio:

1. Una consulta por intervalo configurable; timeouts, backoff y exclusión de
   consultas simultáneas. Respetar 429/`Retry-After` y detener/reducir tras fallos.
2. Validar feed, timestamps por entidad, coordenadas y duplicados; no actualizar
   una trayectoria por cambiar solo la hora de recepción del mismo dato.
3. Filtrar el conjunto de rutas de todos los perfiles y una zona/corredor
   justificable. No persistir la flota completa por defecto.
4. Mantener observaciones crudas relevantes con asociación `unresolved` si no
   puede verificarse viaje/patrón. No utilizarlas como mediciones fiables.
5. Procesar por lotes varias trayectorias: geometría, dirección, secuencia y
   cruces interpolados conservan RF-05. Una desaparición no confirma llegada.
6. Un escritor SQLite, transacciones por snapshot y restricciones de unicidad.
   En producción: migraciones, índices y WAL/checkpoint medidos; no se instalan
   ni programan en esta prueba. Retención propuesta inicial: datos relevantes
   crudos 30 días, agregados de mediciones configurables; retención y límites
   de disco por aprobar. Payload completo solo para diagnóstico con plazo/límite.

### Identidad y procedencia

Para una instancia **validada**, la clave propuesta incluye namespace del
proveedor/feed, `vehicle_id`, `trip_id`, fecha de servicio, inicio de instancia
verificado, ruta/patrón/sentido y relación con el horario. No se usa `entity.id`
como sustituto de vehículo. El catálogo se referencia por hash/versión en la
procedencia; actualizar el catálogo no debe inventar un nuevo recorrido físico.

Si la fecha/inicio son ausentes o no fiables, se conserva el descriptor bruto
y una identidad candidata/segmento en cuarentena. No se infiere fecha de servicio
de la fecha civil del GPS, particularmente al pasar medianoche. Un inicio
verificado admite horas GTFS mayores a 24. Cambios de vehículo, viaje, sentido
o patrón cortan segmentos; huecos y contradicciones invalidan continuidad.

El prototipo usa conservadoramente la tupla:

```text
(provider, vehicle_id, trip_id, start_date, raw_start_time,
 route_id, direction_id, schedule_relationship)
```

Es una **clave del descriptor bruto**, no una solución validada de instancia real.
No oculta el problema de `start_time`: si cambia con cada reporte, fragmentaría
la trayectoria y aumentaría el almacenamiento. Todas las observaciones del
prototipo mantienen `mapping_status=unresolved`. No se enlazan candidatos por
suponer estabilidad del productor.

La unicidad de observación añade timestamp GPS a esa clave. Si coincide el
contenido se deduplica; si cambia contenido al mismo instante se cuenta conflicto,
sin sobrescribir. Un dato anterior al último se pone en cuarentena. Una futura
política de recepción tardía puede conservarlo separado sin alimentar eventos
hacia adelante. La base guarda hash del payload, recepción, timestamp de cabecera,
hash de catálogo, identidad y coordenadas relevantes; no necesita placas.

## Experimentos offline

**Real:** hay una sola captura guardada de posiciones, no snapshots reales
sucesivos. Se filtró la ruta real `11836` (K721) como ejemplo técnico, no como
perfil del usuario: seis vehículos, cinco observaciones recientes persistidas y
una obsoleta descartada. Repetir exactamente la captura insertó cero filas.
Esto valida lectura, filtro y deduplicación; **no valida movimiento ni eventos**.

**Sintético:** `tests/fixtures/snapshot_sequence.json` declara su origen simulado.
Tres snapshots a 07:00, 07:01 y 07:02 incluyen dos vehículos simultáneos,
desplazamiento, cambio de viaje, desaparición, un descriptor incompleto y un dato
obsoleto. Resultado: cinco observaciones, tres identidades candidatas, una
cuarentena de identidad y un rechazo por obsolescencia. **Cero llegadas inferidas**.
No se mezclan estas coordenadas con las reales para calcular tiempos.

Se implementó solo `research/snapshots.py` y generador/replay offline, sin red,
temporizadores, bucles de recolección o consultas operativas de Fase 1.
Las bases experimentales quedan en `data/phase0_5/`, fuera de Git.

## Almacenamiento y volumen

Mediciones de los archivos reales:

- Posiciones completas: **298.066 bytes**; comprimidas localmente con gzip:
  **108.697 bytes**. No está verificada compresión HTTP del servidor.
- TripUpdates completos: **8.211.671 bytes**, sin eventos de parada observados.
- Ejemplo K721: seis registros antes de calidad, 2.511 bytes JSONL; cinco
  aceptados, **2.094 bytes JSONL**. Filtrar SQLite no reduce la descarga del PB
  completo si el servidor no ofrece un filtro documentado.
- SQLite con esquema, índices de claves, metadatos y cinco observaciones:
  **32.768 bytes**, páginas de 4.096. No dividir ese costo fijo entre cinco y
  tratarlo como tamaño marginal.

Un benchmark **sintético**, que replica formas de filas reales y modifica tiempos,
midió 368,64 bytes por observación adicional con identidades estables, 421,888
bytes por metadato de snapshot y 712,704 bytes por observación si cada una crea
una identidad nueva. No son mediciones de evolución de flota real. Los escenarios
incluyen el riesgo de fragmentación por `raw_start_time`.

Estimación a 24 h/día, payload constante, cinco registros nuevos relevantes por
consulta, MB/GB decimales. La deduplicación real y las horas de operación podrían
reducir filas; crecimiento de flota, índices y retención podrían aumentarlas.

| Intervalo | Consultas/día | PB posiciones MB/día | gzip local MB/día | TripUpdates GB/día | JSONL filtrado MB/día | SQLite estable MB/día | SQLite identidad nueva MB/día |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 40 s | 2.160 | 643,823 | 234,786 | 17,737 | 4,523 | 4,893 | 8,608 |
| 60 s | 1.440 | 429,215 | 156,524 | 11,825 | 3,015 | 3,262 | 5,739 |
| 120 s | 720 | 214,608 | 78,262 | 5,912 | 1,508 | 1,631 | 2,869 |

En 30 días: PB completos **19,315 / 12,876 / 6,438 GB** respectivamente;
SQLite con fragmentación de identidad en este ejemplo **258,254 / 172,170 /
86,085 MB**, más base inicial. No son un límite universal ni una garantía.

Fórmula reproducible: `consultas = segundos_activos / intervalo`;
`PB = consultas × bytes_PB`; `SQLite ≈ base + consultas × (metadato +
vehículos_relevantes × fracción_nueva × bytes_registro)`, añadiendo nuevas
identidades e índices según el escenario. Las cifras incluyen las claves del
prototipo, no WAL, copias de seguridad, nuevas migraciones ni eventos derivados.
No extrapolar los cinco vehículos de K721 a todos los perfiles o a toda la ciudad.

El tráfico orientativo de la columna PB supone entrega sin compresión HTTP y
excluye TLS, cabeceras, reintentos y cambios de tamaño: no se midieron bytes de
red a nivel de conexión. No conviene descargar TripUpdates a esa cadencia para
este objetivo mientras no aporten eventos útiles.

## Restricciones, riesgos y comparación

El acceso público sin clave no demuestra cuota ilimitada, SLA ni permiso para
sondeo intensivo. El manifiesto anuncia intervalos de publicación, no concede
una tasa de consultas. Se conserva el intervalo inicial de 40 s como requisito;
para una futura prueba acotada propongo evaluar 60 s antes de fijar operación.
120 s reduce tráfico pero aumenta huecos e incertidumbre de cruces. Ninguno
garantiza detectar una detención corta ni confirmar embarque.

No se usó Croma ni se incurrió en llamadas de pago. No se encontró una tarifa
de acceso al feed público; el costo de conectividad/almacenamiento depende del
equipo y plan de internet, no estimados aquí. Un único recolector evita multiplicar
descargas idénticas; debe detenerse o retroceder ante indisponibilidad.

El catálogo GTFS estático declara CC BY-SA 4.0. La licencia específica del feed
Realtime no se confirmó por separado. No se atribuye automáticamente la licencia
de otra capa a los GPS. La [licencia CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/)
requiere atribución e impone condiciones al compartir adaptaciones; antes de
redistribuir capturas/derivados hay que confirmar alcance con el publicador.
La investigación no redistribuye binarios reales en Git.

| Enfoque | Ventaja | Problema para este proyecto | Estado/recomendación |
| --- | --- | --- | --- |
| Histórico remoto | Podría permitir estudiar días pasados sin esperar a recolectarlos | No hay archivo operativo público verificado con eventos/fechas suficientes | Mantener adaptador opcional y criterio estricto; no depender de él |
| Tracking individual | Lógica enfocada en un vehículo elegible por tramo | El endpoint entrega toda la flota; varios seguimientos pueden repetir la misma descarga y sesgar muestra | Conservar como estrategia de análisis sobre un feed compartido |
| Colector multiposicional | Un snapshot sirve a varios perfiles y vehículos; filas filtradas reducen disco | Aún exige identidad, asociación, control de frescura y reconstrucción por vehículo | Arquitectura preferida, condicionada a resolver asociaciones y validar temporalmente |

No se recuperan días anteriores a partir de snapshots que nunca se guardaron.
Una arquitectura por lotes no elimina la incertidumbre GPS ni arregla IDs del
productor. Ante ambigüedad se conserva evidencia y se rechaza la medición.

## Pruebas, archivos y reproducción

Resultado final: **69 pruebas aprobadas = 54 anteriores + 15 nuevas**;
Ruff sin errores, 29 archivos con formato correcto y `pip check` sin conflictos.
Python 3.13.14 / Windows x64, sin dependencias nuevas. La suite bloquea red.
Los resultados de Fase 0 se conservan y los nuevos se guardan por separado.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE0_5_VALIDATION_RESULTS.json
.\.venv\Scripts\python.exe scripts/replay_phase0_5.py
.\.venv\Scripts\python.exe scripts/analyze_phase0_5.py
```

Los tres comandos son offline; el último requiere las capturas originales y el
ZIP histórico local para repetir toda la comparación. `research_phase0_5.py`
es una herramienta separada que sí consulta fuentes públicas; no forma parte
del replay o de las pruebas y solo descarga el archivo histórico con `--archive`.

Evidencia nueva:

- `PHASE0_5_SOURCE_RESEARCH.json`: consultas documentales reales, hashes y alcance.
- `PHASE0_5_ANALYSIS.json`: distribución temporal, versiones, campos y mediciones.
- `PHASE0_5_SYNTHETIC_REPLAY.json`: resultados de la secuencia simulada.
- `PHASE0_5_VALIDATION_RESULTS.json`: comandos y resultados finales.
- `src/transmitracker/research/`, `tests/test_snapshots.py` y fixture de secuencia.
- Scripts de investigación, análisis y replay; verificador ampliado para guardar
  resultados en un archivo elegido dentro del proyecto.

## Propuesta para el plan y aceptación de la migración

Se añadió una **adenda de Fase 0.5** al final de `IMPLEMENTATION_PLAN.md`, sin
eliminar ni modificar el texto original. Es una propuesta de diseño y migración,
no autorización de fases posteriores. Mantiene cuatro sesiones, dos perfiles,
uno a tres tramos, selección, controles de calidad y cálculo de espera.

Antes de medir con el nuevo diseño deben cumplirse estos criterios:

1. Procedencia/hash de catálogo y reglas de identidad explícitas. Resolver o
   rechazar el caso `start_time` correlacionado con timestamp; no ignorarlo sin
   evidencia temporal suficiente.
2. Snapshots sucesivos **reales** acotados y autorizados, diferenciados de fixtures,
   que prueben estabilidad de identidad/recorrido y permitan cuantificar huecos.
3. Una descarga compartida por proveedor/intervalo, sin duplicarla por perfil.
4. Replay idempotente, sin mezclar proveedores, fechas, viajes o sentidos; datos
   obsoletos, duplicados contradictorios y desapariciones no generan llegadas.
5. Detección por geometría y secuencia con incertidumbre, separando paso estimado
   de detención/embarque. Los tiempos de actualización nunca son eventos de parada.
6. Mediciones completas verificables o rechazo documentado; almacenamiento,
   retención y frecuencia contrastados con una prueba controlada y revisión de
   condiciones del proveedor. Mantener todas las pruebas anteriores.

La siguiente decisión es aprobar o ajustar esta arquitectura y planificar la
resolución de IDs. **No se inició la Fase 1 ni recolección continua.**
