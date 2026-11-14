# Viabilidad de GPS real previa a Fase 3B

Investigación del **13 de noviembre de 2026, America/Bogota**; referencia de
producto **0.2.0**, algoritmo `gps-offline-1.0.0`. Solo investigación documental
y lectura de código. **Fase 3B no iniciada ni autorizada por este informe.**

## 1. Decisión ejecutiva

Hay dos candidatas documentadas: el feed oficial de posiciones y la API Croma.
No existe todavía una fuente demostrada de trayectorias reales reutilizables,
con identidad operativa verificada, para aceptar duraciones en TransMiTracker.
Recomiendo priorizar **TransMilenio como fuente candidata directa**, condicionada
a permiso aplicable, frescura y validación de identidad. Croma es alternativa
condicionada, no evidencia independiente de la operación que agrega.

La consulta del manifiesto oficial fue exitosa, pero no descargamos ni decodificamos
un nuevo `positions.pb`. Tampoco hicimos solicitudes de datos a Croma. No se puede
afirmar disponibilidad/frescura actual del GPS a partir de esas consultas documentales.
No encontramos en las fuentes examinadas un archivo operativo público por fecha
con contenido validado: los históricos estáticos encontrados **no son históricos GPS**.
Esto no demuestra que tales archivos no existan en otras fuentes o bajo convenio.

El siguiente paso recomendado es obtener aclaraciones del proveedor y un pequeño
lote autorizado con metadatos completos; después decidir el alcance de 3B. Puede
ser una entrega manual de datos, sin capturas automáticas ni integración.

## 2. Estado de partida y verificación del repositorio

Se leyeron README, [índice](../INDEX.md), [política documental](../development/DOCUMENTATION_POLICY.md),
[plan y adendas](../development/IMPLEMENTATION_PLAN.md),
[arquitectura](../architecture/OVERVIEW.md), [diseño de créditos](CROMA_INTEGRATION_DESIGN.md)
y reportes [0.5](../archive/phases/PHASE0_5_REPORT.md),
[1B](../archive/phases/PHASE1B_REPORT.md) y [3A](../archive/phases/PHASE3A_REPORT.md).
Se contrastaron modelos, adaptadores, engine, events y protocolos de reconstruction/.

| Clase de afirmación | Evidencia y alcance |
| --- | --- |
| Implementación inspeccionada | Modelos inmutables, tiempos separados, snapshot completo, hashes, rechazo de campos visuales y corte de discontinuidades |
| Implementación experimental | Proyección local por patrón, velocidades entre fixes, intervalos de cruce y duración condicionada; umbrales sin calibración real |
| Resultado histórico leído, no reejecutado | 237 tests aprobados; 23 escenarios sintéticos. No valida precisión real |
| Resultado real histórico leído | [Replay guardado](../PHASE3A_REAL_SAVED_REPLAY.json): 2.565 observaciones, 16 proyecciones unitarias, cero cruces/duraciones aceptados; `reused: true`, no ejecución nueva |
| Pendiente | Verificador operativo real, adquisición, control efectivo de créditos, predictor y producción |
| Hipótesis futura | Colector compartido útil para muchos perfiles; no existe un colector activo |

**Impedimento de código confirmado:** `engine.py` asigna siempre false a
`operationally_verified`. La confianza que permite aceptar eventos en `events.py`
es exclusivamente `Confidence.SYNTHETIC`, con declaración sintética y continuidad.
`IdentityEvidence` no es un contrato para autorizar GPS real. El protocolo
`OperationalIdentityVerifier` existe, pero no se invoca como verificador real.
Cambiar un adaptador no elimina este bloqueo deliberado. Una eventual extensión
de confianza requerirá diseño, pruebas y aprobación en otra tarea.

## 3. Inventario y comparación de fuentes

Todas las consultas nuevas de esta sección son del 2026-11-13. S01–S15 se
resuelven en las referencias finales. Los estados HTTP de las nueve lecturas
directas se conservan en los JSON asociados; los errores del navegador no se
interpretan como caídas del servicio cuando la lectura HTTP posterior tuvo éxito.

| Fuente | Disponibilidad observada / cobertura | Granularidad y calidad | Acceso, coste y continuidad | Compatibilidad / decisión |
| --- | --- | --- | --- | --- |
| Oficial GTFS-RT, S01–S02 | Portal/manifiesto accesibles; posiciones publicadas en manifiesto. GPS histórico del proyecto sí decodificado en fases previas | Protobuf; campos e IDs históricos incompletos/incompatibles; ninguna serie nueva | Sin clave en consulta de manifiesto; tarifa de acceso no establecida; no SLA ni cadencia autorizada verificados | Preferida **condicional**; separar publicación, transporte y calidad |
| Croma, S03–S08 | API documentada de TransMilenio/SITP; no operación de datos probada | JSON normalizado, GPS reciente según proveedor; IDs pueden ser null; estabilidad no garantizada | Clave de organización, créditos, términos específicos pendientes; dependencia de fuente upstream | Alternativa **condicional**, con presupuesto y permiso de persistencia |
| Datos Abiertos Bogotá, S09 | API CKAN respondió 200; búsqueda GTFS devolvió un conjunto de especificación SITP | Metadatos y recursos estáticos; ningún recurso GPS por fecha validado | Licencia específica del recurso necesaria; no asumir la del portal | Útil para descubrimiento; **no determinado** como histórico operativo |
| ArcGIS oficial, S10 | Ítem consultado por REST: GTFS Estáticos 2026-10-27, Document Link a ZIP | Estático, no puntos GPS temporales; no descargamos ZIP | licenseInfo vacío en ese ítem no concede permiso | **No viable** para validar movimiento; útil como contexto de catálogo |
| Transitland / Mobility Database, S11 | Registros de GTFS Schedule y versiones estáticas consultados | Historia de programación; no se encontró en esos registros una serie de posiciones | Condiciones propias y del feed; estado del catálogo no garantiza GPS | **No viable** como sustituto de GPS en los registros examinados |
| Moovit Transit APIs, S12 | Oferta pública de APIs comerciales, incluidas realtime; no acceso contratado | No verificados esquema de posiciones crudas, identidad ni cobertura GPS Bogotá | Medición por volumen, contacto comercial; precio y retención desconocidos | **No determinado**; pedir muestra/contrato, no recomendar como fuente lista |
| Google Routes Transit, S13 | Documenta rutas e itinerarios de transporte | No es una API documentada de observaciones de flota para este fin | Facturación/licencias propias no investigadas para contratar | **No viable** para validar fixes GPS; una hora de itinerario no es ground truth |
| Paradero, S14 | App/repositorio público sobre datos abiertos de Bogotá | Visualización puede animar/extrapolar; no es fuente independiente de medición | Licencia del código no implica derechos sobre datos upstream | Referencia conceptual; **no viable** como verdad GPS por leer pantalla |
| Entrega directa por operador/TMSA | Posibilidad de convenio, no oferta confirmada | Podría proporcionar AVL y eventos auditados | Acceso, coste y campos por acordar | **No determinado**; opción realista para obtener referencia independiente |

No se usó scraping de aplicaciones ni se investigaron interfaces restringidas.
La noticia oficial S02 respalda la publicación GTFS-RT; no certifica estabilidad de
IDs, completitud de flota o utilidad para históricos. SITP es parte de la cobertura
declarada, no una segunda fuente independiente demostrada.

### Manifiesto oficial comprobado

GET `https://gtfs.transmilenio.gov.co/manifest.json`: HTTP 200 a las 21:04 hora
Bogotá. Declara GTFS.zip, positions.pb, tripupdates.pb y alerts.pb en el mismo
host. Declara generación diaria del estático y cada 26 segundos de los PB.
Para posiciones publica 180.434 bytes y `last_modified` de las 04:19:16 del mismo
día; `generated_at` del manifiesto es 04:19:35. Es un desfase superior a 16 horas
respecto a la consulta, **del metadato**, no una medición nueva de antigüedad GPS.
`available: true` y `realtime_available: true` son afirmaciones del manifiesto.
No se verificaron HTTP, header.timestamp ni vehicle.timestamp de esos PB hoy.

La política histórica [1B](../PHASE1B_EXPERIMENT_POLICY.json) sigue sin establecer
permiso de sondeo. S15 tiene restricciones generales de reproducción de contenidos;
no resolvemos aquí su aplicabilidad específica al subdominio GTFS. La publicación
abierta y su frecuencia no constituyen por sí solas licencia de archivo ni cuota.

## 4. Croma: evidencia documental y vacíos

Croma ofrece acceso programático comercial a fuentes públicas mediante API/MCP;
su documentación y OpenAPI son públicos, las operaciones de datos requieren
autenticación. No se inspeccionó una cuenta ni se creó una clave. S03–S04.

La guía S03 anuncia posiciones recientes y refresco aproximado de 20 segundos;
no es un SLA ni latencia GPS→respuesta medida. Describe `live: false` cuando la
fuente supera cinco minutos sin novedad; las posiciones pueden ser las últimas
publicadas. Las llegadas pueden volver a programación: no usarlas como observadas.
No se documenta allí una consulta de históricos operativos por fecha.

### Endpoints comprobados en el OpenAPI público S04

Base `https://api.croma.run`; método **POST**, entrada/salida JSON. No se llamaron.

| Ruta bajo /co/transmilenio/ | Clase documental | Uso |
| --- | --- | --- |
| stops-search/v1, stop/v1 | Dataset | Paraderos |
| stop-departures/v1 | Dataset | Horarios programados |
| routes-search/v1, route/v1 | Dataset | Rutas, patrones y geometría |
| vehicles/v1 | Live | Posiciones |
| stop-arrivals/v1 | Live | Predicciones/estimaciones o programación |
| alerts/v1 | Live | Alertas |

Las cinco operaciones dataset llevan `x-served-from` en OpenAPI; las tres live
se clasifican además explícitamente en S03. Esta clasificación es una verificación
documental nueva; no cambia la política ni las constantes de la versión 0.2.0.

S04 documenta respuesta `data`, con `as_of`, `live`, `notice`, paginación y vehicles.
Campos de vehículo: `vehicle_id`, `label`, `license_plate`, coordenadas,
`bearing`, `speed_kmh`, `route_id`, `route_code`, `route_name`, `system`, `trip_id`,
`trip_start_time`, `stop_id`, `stop_name`, `stop_status`, `reported_at`, `distance_m`.
Los IDs, inicio y reported_at admiten null. Que sean propiedades required no
significa valor no nulo. `reported_at` se describe ISO 8601; comprobar zona al recibir.
En este esquema **no aparecen start_date ni current_stop_sequence**. No fabricarlos.
`distance_m` mide distancia al punto de búsqueda, no progreso sobre shape.
`speed_kmh` no es m/s. No existe garantía documental inspeccionada de que IDs se
mantengan entre páginas, observaciones o días, ni de correspondencia exacta con
la versión del ZIP local. Tener license_plate tampoco acredita por sí solo instancia.

Filtro route o punto/radio; page y per_page, máximo 500 vehículos/página. Un código
de ruta puede incluir ambos sentidos. Una página/punto no equivale a snapshot
completo: perder un bus del radio no demuestra desaparición ni fin de viaje.
Páginas sucesivas pueden reflejar instantes distintos; no se encontró token de
snapshot consistente. Capturar todas las páginas puede costar varias operaciones.

### Acceso, créditos, permisos

S05 documenta Bearer por organización. S06 anuncia 10 créditos live, 1 dataset;
cache hit y fallo no gastan según proveedor, aunque caché exige saldo suficiente.
Batch cobra por ítem. S07 confirma Free USD 0 y 1.500 créditos mensuales: 150
solicitudes live sin hits; no se presupone que una captura tendrá hits gratuitos.
S08 aplica límites compartidos por organización; 429 requiere respetar Retry-After.
No se encontró un techo horario propio de TransMilenio. Ausencia de ese techo no
es aprobación de un sondeo específico; Idempotency-Key no garantiza un único cargo.

Los términos generales (S07b, actualizados 2026-08-17) no garantizan continuidad
ni exactitud y condicionan redistribución de servicios a autorización escrita.
Remiten a términos API aceptados al crear clave, no revisados aquí. No está
resuelto permiso para guardar indefinidamente posiciones, redistribuir dataset,
publicar estadísticas derivadas o trasladar adquisición a backend. Pedir respuesta
escrita; esto es un análisis de ingeniería, no una conclusión jurídica.

## 5. Requisitos mínimos y magnitudes validables

Propuesta conceptual; no nuevo contrato implementado. Basada en semántica GTFS S16
y riesgos comprobados en el repositorio.

| Elemento | Condición para investigación útil |
| --- | --- |
| Original | Payload reproducible, hash de bytes originales, fuente/endpoint, parámetros/página, fechas, content-type, esquema, condición de caché; sin claves |
| Coordenadas | Lat/lon decimales; WGS84 para GTFS. Confirmar CRS del proveedor y registrar conversión si existiera. Rango finito, área plausible; no corregir anomalías silenciosamente |
| Relojes | reported_at por fix, feed_as_of y received_at UTC independientes, zona/desfase explícitos; reloj local sincronizado. No suplir GPS por recepción |
| Identidad | Namespace de proveedor + vehículo publicado; descriptor viaje/ruta/servicio/inicio originales opcionales, evidencia de vigencia temporal y correspondencia de catálogo |
| Recorrido | Hash de catálogo vigente al observar, patrón/shape/ocurrencia verificables. Una parada repetida requiere secuencia/anclaje inequívoco |
| Serie | Al menos dos fixes válidos para desplazamiento medio; varios antes/después de cada extremo para cruce y duración, sin unir cortes |
| Completitud | Filtros, paginación, ámbito espacial y temporal explícitos; diferencial no interpretado como feed completo |
| Calidad | Ordenar por GPS conservando recepción, deduplicar sin borrar sightings; conflictos simultáneos, cambios de descriptor, ausencia, saltos y reinicios en cuarentena |

No hay una clave universal demostrada. Clave candidata: proveedor/endpoint,
vehicle_id e intervalo de instancia, descriptor original y fecha de servicio **si
está respaldada**; la versión del catálogo forma parte del procesamiento, no de
la identidad física. Un hash de payload identifica evidencia, no vehículo.
Con null o IDs reciclados, conservar sin unir; una fecha civil GPS no sustituye
start_date, especialmente después de medianoche. No usar sufijos de trip_id.

Cadencia de consulta y cadencia de observación son diferentes: repetir el mismo
timestamp no aumenta resolución. Contar diferencias de reported_at y novedades
por vehículo; medir latencia recepción−GPS solo cuando ambos relojes sean válidos.
Desfase negativo puede ser reloj/formato incorrecto, no velocidad instantánea.

Validable con serie autorizada: parsing, cobertura de campos, duplicados, frescura,
estabilidad de identidad publicada, continuidad, residuales y velocidad media
entre fixes. Con referencia independiente: errores de cruce, duración y cobertura
de intervalos. No basta que un punto se proyecte cerca de una línea.
GPS solo no identifica puertas, embarques ni espera personal. Velocidad media no
es velocidad instantánea. Llegadas predichas del mismo feed no son verdad externa.

## 6. Viabilidad económica y almacenamiento

Cálculos propios, no compromisos de precio ni cadencias autorizadas. Supuestos:
20 días/mes, ventana de dos horas/día, intervalos [inicio,fin), sin reintentos,
sin hits gratuitos, una solicitud/página por tick, coste live publicado 10 (S06–S07).
`N/h=3600/s`; `N/día=N/h × horas`; `N/mes=N/día × días × P × R`;
créditos `=N/mes × 10`. P=páginas; R=consultas separadas de rutas/ámbitos.
Si una solicitud cubre varias rutas no multiplicar por vehículos; si exige páginas
sí multiplicar. R=1 no demuestra cobertura completa de la red.

| Intervalo | Solicitudes/h | Día (2 h) | Mes P=R=1 | Créditos/mes | Frente a 1.500 |
| --- | ---: | ---: | ---: | ---: | --- |
| 20 s | 180 | 360 | 7.200 | 72.000 | No viable |
| 40 s | 90 | 180 | 3.600 | 36.000 | No viable |
| 60 s | 60 | 120 | 2.400 | 24.000 | No viable |
| 120 s | 30 | 60 | 1.200 | 12.000 | No viable |

Ni siquiera ese escenario acotado diario cabe en Free sin hits; dos rutas
consultadas aparte duplican cifras. Dataset no reemplaza GPS live por costar menos.
Un experimento de 10 minutos a 40 s, una página/ruta: 15 solicitudes, 150 créditos;
cinco sesiones: 750. Con dos páginas o dos rutas: 1.500. Son presupuestos máximos
de llamadas previstas sin reintentos; reservar margen y bloquear antes de agotarlo.
Un punto final inclusivo añadiría una solicitud por sesión. Con 150 llamadas al
mes el intervalo medio continuo 24/7 sería 4,8 horas (mes de 30 días): inútil para
cruces entre paradas. El coste no soluciona continuidad ni frescura.

Para fuente oficial no se estableció tarifa por llamada; no equivale a servicio
gratuito garantizado, capacidad ilimitada ni permiso. Los mismos conteos sirven
para valorar carga, con descarga completa aunque solo interesen cinco buses.

Tamaños **históricos medidos**, no nuevos ni atribuidos a Croma: informe 0.5,
PB de posiciones 298.066 bytes; gzip local 108.697; cinco registros filtrados
2.094 bytes JSONL (418,8 por registro). El manifiesto actual declara otro tamaño;
no es una medición de payload descargado. Para Croma no se midieron bytes.

| Intervalo (ventana anterior) | PB completo MB/mes | gzip local MB/mes | JSONL 5 vehículos nuevos/tick MB/mes |
| --- | ---: | ---: | ---: |
| 20 s | 2.146,1 | 782,6 | 15,08 |
| 40 s | 1.073,0 | 391,3 | 7,54 |
| 60 s | 715,4 | 260,9 | 5,03 |
| 120 s | 357,7 | 130,4 | 2,51 |

MB decimales; fórmulas `N × bytes_payload`, `N × k × fracción_nueva × bytes_fila`.
Con 20/100 vehículos, el JSONL sería 4/20 veces la columna de cinco; el PB no
disminuye por filtrar después. No sumar gzip y original si se conserva solo uno.
No incluyen TLS, cabeceras, páginas extras, índices, eventos ni catálogo. SQLite
3A conserva originales, sightings, ejecuciones, eventos no determinables y versiones:
no equivale a JSONL ni al experimento SQLite de 0.5. Medir crecimiento marginal
real y retención antes de presupuestar su almacén; no dividir tamaño inicial entre
pocas filas ni afirmar aquí bytes por registro nuevos.

## 7. Compatibilidad y riesgos de integración

Mantener adquisición fuera del dominio/GUI y reconstrucción; entregar un lote
inmutable con esquema, origen y manifiesto de integridad. Un normalizador futuro
debe preservar null y originales, convertir unidades explícitamente y producir
ProviderSnapshot sin afirmar una recepción antigua que nunca se midió.
Replay debe funcionar sin conexión. No abrir catálogo/perfiles como destino GPS.

Croma requiere un adaptador JSON nuevo; el lector de captura actual espera PB
local completo. Sus páginas son parciales, así que `complete=True` por defecto de
snapshot_from_rows no debe heredarse sin validación. Faltan fecha de servicio y
secuencia en su esquema inspeccionado: no inferirlas de geometría ambigua.
Una coincidencia de route_id podría referirse a otra versión estática. El patrón
local no puede sustituirse por un shape_id remoto sin evidencia de equivalencia.

Hay acoplamiento actual a Catalog/TemporalAnalyzer y representación SQLite de
resultados. Los protocolos permiten separar proveedor, pero no prueban portabilidad
de un backend. Cualquier adaptador/verificador debe ser explícito y testeable;
este informe no diseña ni implementa infraestructura distribuida.

El almacén GPS solo admite esquema 1; versiones desconocidas se rechazan.
Definir migración futura en archivo nuevo/copias auditadas con hashes y rollback,
sin tocar perfiles/catálogos. Conservar versión de algoritmo/parametrización al
reprocesar; nunca sobrescribir resultados antiguos para aparentar mejora real.

| Riesgo | Probabilidad cualitativa | Impacto | Mitigación / evidencia pendiente |
| --- | --- | --- | --- |
| GPS obsoleto/caché | Alta preocupación por metadatos antiguos; tasa desconocida | Alto | Medir timestamps por vehículo, no solo HTTP/live |
| IDs incompatibles o inicio variable | Alta en evidencia histórica; recurrencia actual desconocida | Crítico | Confirmación del productor y serie etiquetada independiente |
| Permisos de retención no claros | Incertidumbre alta | Crítico | Condiciones por escrito antes de adquirir/redistribuir |
| Páginas incoherentes y buses fuera del radio | Plausible, no medido | Alto | Ámbito parcial, no interpretar ausencia como desaparición |
| Coste multipágina/reintentos | Alto si se opera sostenidamente | Alto | Reserva por solicitud máxima, caché y límites efectivos en fase autorizada |
| Catálogo de otra fecha | Plausible | Alto | Fijar ZIP/hash correcto; no forzar remapeos |
| Ground truth insuficiente | Confirmado en el lote histórico | Crítico | Referencia independiente con incertidumbre declarada |
| Dependencia upstream común | Confirmada conceptualmente Croma/TMSA | Alto | No tratar acuerdo entre derivados como validación independiente |

Probabilidades son juicio de ingeniería, no frecuencias estadísticas medidas.

## 8. Matriz de decisiones

| Decisión | Categoría | Justificación |
| --- | --- | --- |
| Seguir inspeccionando documentación y datos ya guardados | **Viable** | Sin crédito ni cambio de producción; límites conocidos |
| Entrega manual autorizada de AVL + referencia | **Condicional** | Requiere oferta, derechos y campos/fechas verificables |
| Pequeño piloto oficial de snapshots | **Condicional** | Publicación respaldada; permiso, frescura e identidad no resueltos |
| Piloto Croma de pocas sesiones | **Condicional** | Coste documental calculable; falta contrato aplicable, muestra e identidad |
| Operación Croma de 2 h/día a 20–120 s con Free sin hits | **No viable** | Excede 1.500 créditos incluso una página/ruta |
| Históricos estáticos para demostrar tiempos reales | **No viable** | Miden programación, no movimiento |
| Moovit como proveedor GPS crudo Bogotá | **No determinado** | Oferta comercial genérica, muestra/coste/derechos no verificados |
| Histórico operativo público por fecha | **No determinado** | No localizado con contenido operativo validado; no afirmar inexistencia universal |
| Duraciones reales aceptadas por el motor 0.2.0 sin cambios | **No viable** | Gate de confianza solo sintético; requiere otra fase autorizada |

## 9. Propuesta mínima para 3B, pendiente de aprobación

**Objetivo verificable:** obtener un lote real autorizado, reproducible y útil para
caracterizar identidades y determinar si un subconjunto admite validación geométrica
y temporal con referencia independiente. No objetivo de seguimiento ni predictor.

1. Precondiciones: respuesta sobre sondeo/archivo/derivados, muestra sin claves,
   definición de IDs/CRS/relojes, catálogo compatible, presupuesto y referencia.
2. Preferir inicialmente una exportación manual de una ruta/patrón con varias
   instancias y fechas de servicio. Si no hay serie autorizada, 3B puede limitarse
   a normalización offline y calidad; no habilitar confianza operativa.
3. Solo si se aprueba adquisición: experimento pequeño, máximo acordado de
   llamadas/duración, páginas limitadas y margen de créditos. La simulación de
   15 llamadas/10 min/40 s es un cálculo, **no autorización ni elección definitiva**.
4. Registrar captura y versiones antes de normalizar; validar esquema, hashes,
   clocks, flags de caché, completitud, límites y motivos de rechazo. SQLite nuevo,
   sin migrar almacenes previos para iniciar el estudio.
5. Caracterizar vehicle_id, trip_id, route_id, start_time y fecha/secuencia cuando
   existan: colisiones, cambios por observación y continuidad por instancia.
   No declarar estables IDs que solo se vieron dos veces sin referencia externa.
6. Medir cobertura de campos, proporción de fixes nuevos, Δt mediano/P90/máximo,
   huecos, duplicados, antigüedad, relojes negativos, residuales y asociaciones por
   clase (candidata, ambigua, contradictoria, no resuelta; operativa solo con prueba).
7. Para cruce/duración, comparar con registro observado independiente, con tolerancia
   y error temporal propios. Reportar error mediano/P90, detección, FP, rechazo e
   intervalos cubiertos. Sin esa referencia, cerrar únicamente calidad de datos.

Aceptación propuesta: 100 % de entradas trazables y originales íntegros; cero
solicitudes fuera de presupuesto/autorización; cero asociaciones ambiguas aceptadas;
replay offline determinista; métricas con denominadores y desconocidos explícitos.
Para un subconjunto de prueba, proponer al menos tres instancias distintas con
ambos extremos observables y referencia independiente, sin presentarlo como muestra
representativa. Umbrales de error y tamaño estadístico final deben acordarse antes
de validar precisión; no elegirlos después de ver resultados.

Detener adquisición ante 401/403, cuota/402, 429 hasta revisión, condición legal
incierta, coste inesperado, límite acordado, falta persistente de novedades, cambios
de esquema o conflicto de reloj. Cuarentenar registros con IDs/coordenadas dudosos;
si impiden el objetivo, detener el experimento, no fabricar asociaciones.

Fuera: colector de producción, polling prolongado, VPS, móvil, Telegram, scheduler,
ETA a usuario, espera/embarque inferidos y compra de planes. Si no hay fuente apta,
mantener fixtures para regresiones y pedir AVL/eventos a TMSA u operador; un GPS
voluntario de pasajero solo validaría su trayecto personal, no identidad de toda
la flota ni llegadas observadas de otros buses, y exigiría diseño/consentimiento.

## 10. Preguntas y decisiones pendientes

Para TMSA: ¿licencia específica y cuotas del host GTFS? ¿archivo AVL por fecha?
¿fechas de actualización reales y causa de metadatos antiguos? ¿cobertura por
componente/operador? ¿semántica y reciclaje de vehicle_id, trip_id, start_time?
¿catálogo exacto/crosswalk y eventos de parada auditados disponibles bajo convenio?

Para Croma: ¿se permite guardar payloads/placas y por cuánto tiempo? ¿publicar
estadísticas derivadas y reutilizar en backend? ¿términos API aplicables a Free?
¿un coste por página y cómo se factura un timeout con respuesta no recibida?
¿TTL/cache/actualización GPS y SLA? ¿snapshot consistente entre páginas, historial,
start_date/current_stop_sequence o crosswalk de IDs disponibles? ¿qué reloj usa
as_of? ¿se conserva el timestamp original por vehículo? ¿se normaliza start_time?
¿límites específicos de TransMilenio y muestreo permitido para investigación?

Para operador alternativo/Moovit: ¿Bogotá con posiciones observadas descargables,
IDs estables, históricos y permiso de investigación? ¿precio y muestra documentada?

El propietario debe decidir si solicita primero entrega manual/condiciones a TMSA,
si reserva parte de los 1.500 créditos para un piloto Croma solo después de permiso,
y qué error/alcance pretende validar (cruce/duración, no espera personal).
No se enviaron esas preguntas a terceros en esta tarea.

## 11. Fuentes y evidencia verificable

**Fecha de consulta para todas: 2026-11-13.** D=hecho documental inspeccionado;
P=afirmación del publicador, no validada con datos; I=inferencia del informe;
ND=no determinado. Las secciones económicas y el diseño son I sobre supuestos
explícitos. No se atribuyen a proveedores las decisiones de arquitectura.

| ID | Fuente / URL | Respaldo y límite |
| --- | --- | --- |
| S01 | [Manifiesto TMSA](https://gtfs.transmilenio.gov.co/manifest.json), [portal](https://gtfs.transmilenio.gov.co/) | D HTTP 200 y JSON; P frecuencia/disponibilidad. No nuevo PB |
| S02 | [Publicación oficial de GTFS-RT](https://www.transmilenio.gov.co/comunicaciones/noticias-de-transmilenio/especiales-transmilenio/datos-abiertos-tiempo-real-transmilenio-conecta-operacion-sistema-tecnologia-ciudad) | P apertura del servicio; no garantía de calidad/permiso de sondeo |
| S03 | [Guía Croma TransMilenio](https://docs.usecroma.com/guides/colombia/transmilenio) | D clasificación y P refresco/fallback; no ejecución. Ruta /es falló en navegador, se consultó la inglesa |
| S04 | [OpenAPI Croma](https://api.croma.run/openapi) | D HTTP 200, esquemas/operaciones; no respuestas GPS reales |
| S05 | [Autenticación](https://docs.usecroma.com/authentication) | D Bearer/organización; no cuenta privada inspeccionada |
| S06 | [Créditos](https://docs.usecroma.com/credits) | D tarifa publicada, reglas de caché/fallo; no saldo ni cargos reales |
| S07 | [Precios](https://usecroma.com/pricing) | D HTTP 200 Free 1.500; no contratación |
| S07b | [Términos generales](https://usecroma.com/terms) | D HTTP 200; términos API específicos no revisados, retención ND |
| S08 | [Límites](https://docs.usecroma.com/rate-limits) | D HTTP 200 por lectura directa tras fallo navegador; cuota GPS específica ND |
| S09 | [CKAN Bogotá: búsqueda GTFS](https://datosabiertos.bogota.gov.co/api/3/action/package_search?q=GTFS&rows=10) | D HTTP 200, un conjunto; no búsqueda universal ni validación de históricos GPS |
| S10 | [Metadatos ArcGIS oficiales](https://www.arcgis.com/sharing/rest/content/items/6d0043cf1ba443a699bad973539a1422?f=json) | D HTTP 200, vínculo estático, licenseInfo vacío; no ZIP descargado |
| S11 | [Transitland](https://www.transit.land/data/feeds/f-d2g6-transmilenio~troncal~transmilenio~alimentadores~transmile), [Mobility Database](https://mobilitydatabase.org/feeds/gtfs/mdb-3358) | D registros estáticos consultados; no afirmar cobertura RT ausente en todos los catálogos |
| S12 | [Moovit Transit APIs](https://moovit.com/maas-solutions/transit-apis/) | P oferta comercial de APIs; cobertura GPS y contrato ND |
| S13 | [Google Routes Transit](https://developers.google.com/maps/documentation/routes/transit-route) | D itinerarios documentados; no se documenta allí dataset de posiciones de flota |
| S14 | [Paradero](https://github.com/croma-labs/paradero) | D repositorio público; conceptual, no observaciones independientes |
| S15 | [Condiciones web TMSA](https://www.transmilenio.gov.co/comunicaciones/publicaciones/2025/terminos-y-condiciones-en-el-sitio-web-de-transmilenio) | D HTTP 200; aplicabilidad específica a feed/licencia de sondeo ND |
| S16 | [GTFS-RT referencia](https://gtfs.org/documentation/realtime/reference/), [buenas prácticas](https://gtfs.org/documentation/realtime/realtime-best-practices/) | D semántica de coordenadas/tiempos/identificadores; estándar no es garantía del productor |

Evidencias nuevas de consulta pública (esquemas/metadatos, **sin datos de vehículos**):
[PUBLIC_HTTP](evidence/GPS_FEASIBILITY_20261113_PUBLIC_HTTP.json) y
[METADATA](evidence/GPS_FEASIBILITY_20261113_METADATA.json). El primero conserva
hora, tamaño y SHA-256 del texto UTF-8 recibido (no necesariamente bytes de transporte),
manifiesto y extracto estructural de operaciones; el segundo los esquemas seleccionados
y metadatos CKAN/ArcGIS. No son copias completas de OpenAPI/HTML ni captura GPS.
La lectura inicial en sandbox falló por red; la repetición puntual aprobada obtuvo
los estados indicados. No se interpretó ese fallo como indisponibilidad externa.

## 12. Cierre y recomendación

Investigación documental completada con límites explícitos. Es defendible elegir
una **candidata** para solicitar datos, no elegir aún una fuente operativa validada.
Priorizar TMSA directo/entrega autorizada; mantener Croma como alternativa limitada
por presupuesto y términos. No iniciar adquisición sostenida con Free ni desbloquear
confianza real del motor sin evidencia independiente y aprobación expresa.

Solo se crean este informe y evidencias públicas asociadas y se actualiza INDEX.
La [verificación documental](evidence/GPS_FEASIBILITY_20261113_CHECKS.json)
comprobó 34 enlaces locales del informe/índice antes de añadir este enlace al acta,
parseo de los JSON nuevos y 49 archivos históricos con hashes idénticos. No hay
diff en src/, scripts, tests, versión ni requisitos. `git diff --check` pasó.
Sin modificación de código, migraciones, dependencias, catálogos, perfiles, capturas
previas, credenciales, commits ni push. No se repitió pytest ni el replay histórico.
La siguiente fase permanece **pendiente de decisión del propietario**.
