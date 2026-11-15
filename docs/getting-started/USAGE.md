# Configurar recorridos habituales

## Estabilización 0.7.1

El dashboard identifica la versión del producto y el modo GTFS estático. La consulta
separa el resultado principal, las tarjetas de cada tramo, caminatas/margen y las
advertencias. **Ver detalles técnicos** permite consultar códigos originales; no
es necesario interpretarlos para usar la vista principal.

Si el límite de llegada impide recomendar una salida, **Qué se pudo comprobar**
muestra fecha, horizonte real, disponibilidad tras caminar, tramos, tolerancias,
restricción y procedencia. Cuando se demuestra una cadena completa tardía se presenta
como **Alternativa programada descartada — no cumple las condiciones**, con diferencia
frente al límite. Nunca es una recomendación. Si no se demuestra la conexión entre
todos los tramos, no se muestra una llegada final del recorrido.

Una caminata inicial que termina después de la ventana se explica como limitación
del horizonte, sin afirmar ausencia de buses. Revisa **Ventana de búsqueda y ayuda**
en el editor: puedes cambiarla mediante edición y guardado explícitos, sin ajustes
automáticos. Las advertencias identifican primer/segundo transbordo, conservan
caminata y tolerancia, y no significan que una conexión sea imposible.

El contenido largo se desplaza verticalmente. Se revisaron temas claro/oscuro,
ventanas de 1180×820 y 900×650, guardado/reinicio, consultas positivas y negativas.
[Informe consolidado, evidencia y límites de la revisión](../archive/phases/V071_STABILIZATION_REPORT.md).

Abra la GUI con `python -m transmitracker.gui` desde el entorno del proyecto,
con `PYTHONPATH` apuntando a `src`. Los comandos completos están en README.

## Guardar un recorrido

Seleccione Casa → Trabajo o Trabajo → Casa. Cada perfil admite de uno a tres
tramos. Puede buscar primero un origen (nombre, código o ID) o una ruta (número,
nombre corto o largo). Hacer clic en un resultado confirma la selección; escribir
un nombre sin confirmarlo solo crea texto pendiente, que puede guardarse en borrador.

Seleccione un patrón y una ocurrencia del origen. Los destinos se filtran por
patrón, orden y permisos de bajada; los orígenes por permisos de subida. Una parada
repetida se distingue por secuencia. El sentido no publicado se mantiene desconocido.
La modalidad de cada tramo se conserva al guardar desde el editor.

Añadir/eliminar conserva valores y selecciones de los tramos restantes. Eliminar
un tramo cambia una conexión: revise la caminata/tolerancia de ese transbordo.
Una conexión espacial no verificada es una advertencia informativa. La aplicación
conserva los minutos del usuario y no acredita un paso peatonal por cercanía.

Casa → Trabajo solicita el límite de llegada y días activos; la planificación
estática permite consultar una salida orientativa. Trabajo → Casa permite una salida habitual
opcional y no exige llegada. Sin evidencia no hay duración estimada; sin salida
no se inventa una hora absoluta de llegada.

Guardar perfil comprueba relaciones del catálogo y valores de configuración,
sin fecha ni salida de ejemplo. Guardar borrador admite campos incompletos y los
mantiene separados del perfil configurado. No hay autoguardado: antes de cerrar,
pulse el botón correspondiente. Se confirma el resultado y se avisa de cambios
posteriores al guardado que todavía estén pendientes.

## Estados y consulta opcional

| Estado | Significado |
| --- | --- |
| Sin configurar | No hay perfil ni borrador |
| Borrador incompleto/sin validar | Edición reanudable; no acredita un recorrido íntegro |
| Configurado | Relación origen/ruta/patrón/destino válida en el catálogo fijado |
| Horario de ejemplo validado | Consulta programada satisfactoria para esa revisión y un instante concreto |
| Pendiente de migración | El perfil conserva una versión distinta del catálogo activo |

Un borrador puede coexistir con el último perfil configurado. Si otra ventana
cambió el perfil o borrador, se rechaza la escritura con conflicto de revisión;
recargue y reconcilie los cambios. Un borrador basado en una revisión antigua no
sobrescribe automáticamente una revisión reciente.

En **Consultar horario programado**, despliegue fecha y salida concretas. Solo
esa consulta requiere un instante. Respeta la zona America/Bogota, calendario,
excepciones, medianoche y horas GTFS mayores a 24. Un fallo de calendario o de
límite de llegada no borra el formulario ni invalida su guardado estructural.
El límite de llegada se aplica a Casa → Trabajo, no a Trabajo → Casa.

El horizonte en opciones avanzadas limita cuántos minutos hacia adelante se
buscan horarios publicados. **No es espera media ni una estadística histórica**.
El contrato reserva espera esperada como `null`, con base no disponible, hasta
una fase futura. Los horarios programados tampoco acreditan tiempos reales.

## Planificación estática (0.7.0)

Desde el dashboard de un **perfil configurado**, pulse **Planificar con GTFS
estático**. Seleccione la fecha civil de salida en Bogotá y consulte. Casa → Trabajo
usa el límite de llegada guardado y su desplazamiento de día; busca la salida más
tardía entre itinerarios con horas publicadas explícitas. Trabajo → Casa usa la
salida habitual o la hora que escriba para esta consulta y busca la llegada más
temprana compatible; no aplica el límite de llegada de ida. Si falta esa hora,
la consulta la solicita sin inventarla. Edite/guarde el perfil aparte para cambiar
sus tolerancias o ventana; consultar no guarda ni modifica esos datos.

La edición de la hora de regreso admite **HH:MM** o **HH:MM:SS** estrictos. Sin
editar el campo precargado, se usa directamente la hora habitual guardada, incluidos
sus microsegundos; cambiar solo la fecha no la convierte en una edición de hora.
Una edición HH:MM significa segundos cero.
Un formato inválido produce error sin recurrir silenciosamente a la hora guardada.
Vaciar el campo solicita una salida explícita y no cambia el perfil.
Escribir fracciones manualmente no amplía el parser: si editó y quiere recuperar
el valor guardado con microsegundos, vuelva a abrir el panel sin editar la hora.

El resultado muestra caminatas, abordajes y llegadas programados, fechas de servicio
GTFS, transbordos con buffers, margen configurado y fecha de importación del catálogo.
Separa llegada con caminata final de llegada incluyendo margen. La espera implícita
es una diferencia entre horas del itinerario, **no una espera real observada**.
Se conserva la advertencia de conexión peatonal no verificada.

**Planificación basada en GTFS estático. No es una predicción en tiempo real.**
No garantiza puntualidad, disponibilidad, conectividad peatonal ni alcanzar el
vehículo. No utiliza GPS ni calcula probabilidades. Frecuencias `exact_times=0`
y llegadas sin hora explícita quedan excluidas; si solo hay alternativas no
resolubles, no se presenta una recomendación puntual.

La ventana `departure_window_minutes` tiene un alcance explícito en esta nueva
consulta: para ida, desde el mayor entre medianoche civil y límite menos ventana,
hasta el límite; para regreso, desde la salida solicitada hasta salida más ventana.
Todos los abordajes deben quedar dentro de ese horizonte y después de la caminata
inicial; en regreso la llegada final puede quedar después. La salida de ida debe
pertenecer a la fecha civil elegida, aunque el abordaje o la llegada correspondan
al día siguiente. Las fechas de servicio GTFS pueden ser anteriores (horas >24).
No se amplía la ventana por cada transbordo ni se transforma en minutos de espera.
Una consulta diagnóstica adicional acotada a 24 horas puede distinguir ausencia de
servicio de ventana insuficiente; no aporta alternativas a la recomendación.

Sin alternativa verificable se muestra el motivo: día inactivo, catálogo ausente
o incompatible, servicio no compatible, horas no determinables, transbordo
incompatible, límite incumplible u horizonte insuficiente. Cambiar fecha/hora o
salir de la página descarta respuestas anteriores; las consultas SQLite van al
trabajador existente, sin bloquear Tk.

Si faltan horas de abordaje, el diagnóstico comprueba el mismo patrón, ocurrencias,
permisos y servicios activos. Los horarios vecinos del mismo viaje solo permiten
excluir ventanas, nunca rellenar una hora. `SCHEDULE_TIME_UNRESOLVED` con el aviso
`SCHEDULE_WINDOW_UNVERIFIED` significa que existe estructura y calendario activos,
pero **no está demostrado que haya un abordaje dentro de la ventana elegida**.
La revisión usa un rango de fechas acotado por las horas GTFS/ventanas de frecuencia
publicadas; no prueba disponibilidad fuera de ese ámbito ni resuelve offsets sin
ancla. Una alternativa explícita válida conserva prioridad sobre este diagnóstico.
En la primera ocurrencia de un viaje por frecuencia, el intervalo publicado es
`[start, end)`: una consulta que empieza en `end` o después queda excluida. Se
identifica la primera secuencia real, aunque no sea 1. Ese final no se impone a
paradas posteriores cuyo desplazamiento temporal siga siendo desconocido.

### Validación y cierre para QA — 2026-11-14

Se probaron perfiles y catálogos sintéticos con uno, dos y tres tramos, servicios
que se adelantan entre sí, frecuencias, calendarios/excepciones y horas GTFS de
25 y 49 horas. Las pruebas Tk abren ventanas reales, consultan ambos perfiles y
descartan respuestas obsoletas. La suite impide conexiones de red.
Resultado: **93 pruebas pertinentes aprobadas** (21 nuevas), 91 de servicios y
regresión más dos ventanas Tk reales; Ruff, formato y `pip check` correctos con
Python 3.13.14. Se ejecutan servicios y Tk por separado según
[VALIDATION](../development/VALIDATION.md#planificación-estática-070), evitando
un error del ejecutor Windows al mezclar módulos; no se modificó ese ejecutor ni
se repitió la suite completa.

Ejercicio distinto con los **dos perfiles personales sin cambios** y catálogo
oficial local, importado el 2026-11-12: fecha civil 2026-11-17, con día del perfil
y servicio del patrón activos. Ida: `ARRIVAL_DEADLINE_EXCEEDED`; regreso:
`DEPARTURE_TIME_REQUIRED` (sin salida habitual). No se obtuvo una recomendación
real ni se cambiaron datos para forzarla. Los hashes de perfiles, preferencias y
catálogo permanecieron iguales. Evidencia detallada privada nueva bajo
`data/pilots/static-planning-20261114/`; solo agregados en la
[evidencia de validación](../archive/evidence/STATIC_PLANNING_VALIDATION_20261114.json).

Entrega disponible para QA Check; sin commit/push ni autorización implícita de
otra capacidad. El Camino B de ampliar capturas sigue pospuesto. La fecha de
importación del catálogo no acredita vigencia operativa ni precisión del horario.

Corrección posterior al QA de `b12c07d`: el panel ya no trunca segundos y se
distinguen las salidas sin hora de la ausencia de servicio compatible. Regresiones
solo sintéticas, incluidas ventanas Tk reales, en la
[evidencia de corrección](../archive/evidence/STATIC_PLANNING_QA_FIX_VALIDATION_20261114.json).
Resultado: **77 casos distintos aprobados** (26 nuevos, tres pruebas Tk reales),
Ruff y formato correctos. La comprobación final de frecuencias repite dos casos
del lote inicial y añade el caso de ancla ausente con ventana de 25 horas.
Se conserva 0.7.0 pendiente de aceptación; no se amplía la fase ni se repite el
ejercicio con perfiles personales. No hay commit/push de esta corrección.

Corrección focalizada posterior a `72bf350`: se descartan frecuencias vencidas en
la primera parada y se conserva la hora habitual intacta con microsegundos mediante
el contrato existente `departure_clock=None`. Sin cambios en búsqueda de itinerarios,
parser explícito, esquemas o dependencias. Regresiones y resultados en la
[evidencia focalizada](../archive/evidence/STATIC_PLANNING_FREQUENCY_CLOCK_FIX_20261114.json).
Resultado: **57 pruebas focalizadas aprobadas**, incluidas cuatro con Tk real
y diez casos nuevos. Ruff y formato correctos; solo fixtures sintéticos, sin
repetir la suite completa ni utilizar perfiles personales.
Continúa pendiente la aceptación de v0.7.0; no se autoriza otra fase ni se hace
commit/push en esta tarea.

## Catálogo, configuración y privacidad

GTFS estático es un catálogo de rutas, paraderos, patrones, calendarios y horarios
publicados. No indica la posición actual de un vehículo. La fecha de importación
no garantiza servicio en todos los días. Los datos Realtime y las predicciones
no están activos; tampoco existen estadísticas históricas útiles en la GUI.

La base de catálogo se abre en modo de lectura. Configurar otro SQLite registra
y activa explícitamente su versión, pero conserva los perfiles antiguos y muestra
el aviso de migración. El cambio no remapea IDs. El asistente gráfico de migración
no está implementado; los servicios explícitos de Fase 1B siguen disponibles.

Los perfiles, revisiones, borradores y consultas de horario de ejemplo se guardan en
`data/gui/profiles.sqlite3`; tema y preferencias en `data/gui/settings.json`.
La nueva planificación estática es de solo lectura y no registra sus resultados.
La demo usa otro directorio. Las credenciales se guardan solo en `.env` en la raíz,
con campos enmascarados en pantalla y sin aparecer en los diagnósticos.
**`.env` es texto sin cifrar**; excluirlo de Git no protege frente a alguien que
pueda leer ese archivo. No coloque claves reales en `.env.example`.

La API key de Croma serviría para autenticar una integración futura; guardarla no
hace consultas ni consume créditos. El token de Telegram identifica un bot y el
Chat ID su chat de destino; guardarlos no envía mensajes. Los intervalos serían
una preferencia de sondeo futuro, no permiso del proveedor. Recolección y avisos
automáticos están deshabilitados. Los enlaces de ayuda externos solo se abren al
hacer clic y no son consultas a una API de datos.

Documentación oficial: [GTFS estático](https://gtfs.org/documentation/schedule/reference/)
y [bots de Telegram](https://core.telegram.org/bots/features#botfather).
