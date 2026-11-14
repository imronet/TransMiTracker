# TransMiTracker — Implementation Plan

**Proyecto:** Aplicación de escritorio para estimar tiempos de desplazamiento en TransMilenio/SITP.

**Lenguaje:** Python 3.12+

**Sistema operativo:** Windows 10/11

**Interfaz:** CustomTkinter

**Zona horaria:** America/Bogota

**Estado inicial:** Proyecto nuevo, implementación incremental.

## 1. Objetivo

Desarrollar una aplicación de escritorio que monitoree vehículos del sistema TransMilenio/SITP de Bogotá para aprender los tiempos reales de viaje y recomendar al usuario:

- A qué hora salir de casa para llegar puntualmente al trabajo.
- A qué hora salir del trabajo para llegar a casa a una hora determinada.
- Cuánto durará cada trayecto, incluyendo caminatas, esperas, transbordos y márgenes de seguridad.
- Cuál es la hora estimada de llegada a casa cuando se conoce la hora de salida del trabajo.

La aplicación tendrá una GUI intuitiva, una base de datos local y un bot de Telegram para notificaciones automáticas.

## 2. Requisitos funcionales

### RF-01. Perfiles de desplazamiento

Crear dos perfiles independientes:

- **Casa → Trabajo**
- **Trabajo → Casa**

Cada perfil admite entre 1 y 3 tramos consecutivos de transporte público.

Cada tramo contiene:

- Paradero o estación de origen.
- Ruta seleccionada.
- Sentido y patrón de servicio válido.
- Paradero o estación de destino.

Los tres selectores serán dinámicos:

1. El usuario busca y selecciona el origen.
2. Se muestran únicamente las rutas válidas para embarcar allí.
3. El usuario selecciona una ruta.
4. Se muestran exclusivamente los destinos posteriores que atiende el recorrido seleccionado.

Se deben considerar variantes de recorrido, sentidos, vagones/plataformas y servicios disponibles según fecha y hora.

### RF-02. Tolerancias y horarios

Permitir configurar:

- Minutos caminando desde casa o trabajo hasta el primer paradero.
- Minutos adicionales por cada transbordo.
- Minutos caminando desde el último paradero hasta el destino.
- Hora límite de llegada.
- Hora de aviso.
- Margen de seguridad personalizable.
- Días de la semana en que aplica el perfil.

El cálculo debe contemplar el tiempo de espera del vehículo, no solamente el tiempo dentro del bus.

### RF-03. Fuentes de información

Implementar dos adaptadores:

**Proveedor principal: GTFS oficial de TransMilenio**

- GTFS estático: rutas, paraderos, viajes, patrones, horarios y geometrías.
- GTFS Realtime: posiciones de vehículos, actualizaciones de viajes y alertas.

**Proveedor alternativo: Croma API**

Documentación:
https://docs.usecroma.com/es/guides/colombia/transmilenio

Funciones documentadas relevantes:

- `POST /co/transmilenio/stops-search/v1`
- `POST /co/transmilenio/routes-search/v1`
- `POST /co/transmilenio/route/v1`
- `POST /co/transmilenio/vehicles/v1`
- `POST /co/transmilenio/stop-arrivals/v1`
- `POST /co/transmilenio/alerts/v1`

No inventar endpoints, campos, autenticación ni límites. Verificar la documentación y realizar pruebas controladas de integración.

Permitir seleccionar proveedor principal, respaldo o modo sin conexión.

No asumir que Croma mantiene datos en vivo cuando el proveedor oficial presenta interrupciones.

### RF-04. Seguimiento de vehículos

Registrar cuatro sesiones de seguimiento al día, separadas inicialmente por 2 horas y 30 minutos.

Permitir configurar:

- Hora de inicio de las sesiones.
- Perfil que se medirá.
- Intervalo de consulta, inicialmente 40 segundos y ajustable.
- Duración máxima y condiciones de finalización.
- Si las sesiones se ejecutarán en fines de semana.

Cada sesión:

1. Identifica la ruta y patrón válidos para el tramo.
2. Obtiene los vehículos activos.
3. Descarta vehículos con datos obsoletos o dirección incorrecta.
4. Selecciona el vehículo elegible que tenga la menor distancia restante por recorrido hasta el origen, siempre que todavía no lo haya superado.
5. Conserva su identidad durante el seguimiento mediante `vehicle_id`, `trip_id` y metadatos disponibles.
6. Registra observaciones GPS con marca de tiempo.
7. Detecta o estima el paso por el origen.
8. Detecta o estima el paso por el destino.
9. Calcula la duración y la incertidumbre.
10. Persiste la medición.

Si el vehículo desaparece, cambia de viaje, se desvía o pierde precisión, registrar el incidente y no inventar una llegada.

### RF-05. Detección del paso por un paradero

No depender únicamente de una distancia circular.

Desarrollar un algoritmo que:

- Proyecte las posiciones GPS sobre la geometría del recorrido.
- Calcule la distancia acumulada a lo largo del recorrido.
- Verifique dirección de desplazamiento y secuencia de paradas.
- Detecte el cruce de la ubicación de cada paradero entre observaciones consecutivas.
- Interpole el instante de cruce cuando resulte razonable.
- Utilice eventos o actualizaciones de parada más fiables cuando estén disponibles.
- Clasifique cada detección por nivel de confianza.

Tolerancias espaciales iniciales sujetas a validación:

- Troncal: 100–150 metros.
- Zonal SITP: 50–75 metros.

Estas tolerancias son candidatas, no mediciones previamente calibradas.

Distinguir entre paso estimado por una estación y detención/embarque confirmado. No atribuir a GPS una precisión inexistente.

### RF-06. Base de datos histórica

Utilizar SQLite con migraciones versionadas.

Guardar, como mínimo:

- Perfiles y tramos configurados.
- Catálogo de rutas, paraderos y patrones.
- Sesiones programadas y ejecutadas.
- Identificadores de vehículo/viaje.
- Observaciones GPS relevantes.
- Tiempo estimado de llegada y paso por paradas.
- Mediciones completas, incompletas y rechazadas.
- Incertidumbre y nivel de confianza.
- Estado y antigüedad de los feeds.
- Predicciones generadas.
- Historial de notificaciones.

Evitar duplicados por identificador de viaje, tramo e instante. No mezclar identificadores de distintos proveedores sin un mapeo explícito.

### RF-07. Motor predictivo

Implementar inicialmente una predicción estadística interpretable.

Variables:

- Día de la semana.
- Franja horaria.
- Sentido y patrón de ruta.
- Duración observada del viaje.
- Tiempo de espera.
- Tiempo de transbordos.
- Tolerancias de caminata.
- Margen de seguridad.

Fórmula conceptual:

`T_total = caminatas + esperas + trayectos + transbordos + margen`

`hora_salida = hora_limite_llegada - T_total`

Reglas:

- Considerar prioritariamente las mediciones del día anterior cuando sean comparables.
- No confiar en un promedio basado en una sola medición.
- Al acumular suficiente historial, utilizar estadísticos robustos y una duración conservadora, como el percentil 75.
- Separar los históricos de ida y vuelta.
- Usar horarios estáticos como estimación de respaldo cuando no haya observaciones suficientes.
- Identificar la fuente y confianza de cada predicción.

Para el regreso, calcular también:

`hora_llegada_casa = hora_salida_trabajo + T_total_retorno`

Cuando haya información en vivo, actualizar las estimaciones considerando próximas llegadas y esperas.

### RF-08. Bot de Telegram

Permitir configurar mediante la GUI:

- Token del bot.
- Chat ID.
- Activación de notificaciones.
- Horarios de aviso de ambos perfiles.

Guardar las credenciales en un archivo `.env` local, excluido de Git.

Implementar:

- Prueba de conexión.
- Mensaje diario de recomendación.
- Aviso cuando los datos en vivo no estén disponibles.
- Protección frente a notificaciones duplicadas.
- Reintentos controlados ante errores de red.

No imprimir tokens en logs ni incluir credenciales reales en pruebas.

### RF-09. Programación automática

Utilizar APScheduler para:

- Ejecutar las cuatro sesiones diarias.
- Emitir avisos a las horas configuradas.
- Actualizar periódicamente los catálogos estáticos.
- Realizar limpieza y mantenimiento local.

Las tareas deben funcionar aunque la ventana principal esté cerrada, siempre que el proceso de fondo continúe ejecutándose.

Implementar un proceso de fondo separado de la GUI y controlar instancias duplicadas.

En Windows, integrar el Programador de tareas para iniciar el proceso automáticamente al iniciar sesión.

No prometer ejecución cuando el computador esté apagado o suspendido.

## 3. Arquitectura técnica

Utilizar una arquitectura modular y orientada a servicios.

Estructura sugerida:

- `src/transmitracker/__main__.py`: punto de entrada.
- `src/transmitracker/gui/`: interfaz, componentes y formularios.
- `src/transmitracker/models/`: modelos y validación.
- `src/transmitracker/providers/`: GTFS oficial, Croma y contratos compartidos.
- `src/transmitracker/gtfs/`: importación y normalización de datos GTFS.
- `src/transmitracker/tracking/`: selección de vehículos, geometrías y detección de eventos.
- `src/transmitracker/prediction/`: estadísticas y cálculo de horarios.
- `src/transmitracker/services/`: lógica de negocio.
- `src/transmitracker/notifications/`: Telegram.
- `src/transmitracker/scheduler/`: trabajos programados.
- `src/transmitracker/storage/`: SQLite y migraciones.
- `src/transmitracker/core/`: configuración, logging y excepciones.
- `tests/`: pruebas unitarias y de integración.
- `tests/fixtures/`: respuestas GTFS y Croma anonimizadas.
- `docs/`: arquitectura, decisiones y manuales.

Paquetes candidatos:

- `customtkinter`
- `httpx`
- `python-dotenv`
- `pydantic`
- `protobuf`
- `gtfs-realtime-bindings`
- `apscheduler`
- `SQLAlchemy`
- `shapely`
- `pytest`
- `pytest-asyncio`
- `ruff`

Confirmar compatibilidad y seleccionar únicamente las dependencias necesarias.

## 4. Fases de implementación

### FASE 0 — Investigación y prueba de concepto

Objetivo: validar técnicamente las fuentes de datos antes de desarrollar la aplicación.

Tareas:

1. Crear el proyecto, entorno virtual y configuración básica.
2. Verificar la documentación y disponibilidad de los feeds oficiales.
3. Descargar una muestra de GTFS estático.
4. Intentar leer un mensaje GTFS Realtime real.
5. Decodificar vehículos, viajes y marcas de tiempo.
6. Analizar cobertura por sistema, ruta y paradero.
7. Probar cómo relacionar `vehicle_id`, `trip_id`, `route_id` y `stop_id`.
8. Documentar problemas de cobertura y diferencias entre las fuentes.
9. Preparar un modo de prueba con fixtures locales para cuando el feed no esté disponible.
10. Crear el primer test automatizado.

Entregable: diagnóstico reproducible, script de lectura y pruebas.

Criterio de aceptación: poder interpretar al menos un feed válido, real o guardado, mostrar datos útiles en consola y explicar cómo se mapea un vehículo a su recorrido. La conexión en vivo debe quedar marcada como no validada si no se pudo probar.

**No avanzar a la Fase 1 sin entregar el informe de esta fase.**

### FASE 1 — Catálogo y motor de datos

Objetivo: construir las consultas que alimentarán la interfaz.

Tareas:

1. Importar archivos GTFS a SQLite.
2. Normalizar estaciones, vagones y paraderos zonales.
3. Consultar rutas que atienden un origen.
4. Filtrar sentidos y variantes de recorrido.
5. Listar paradas posteriores a un origen dentro del recorrido.
6. Validar que origen y destino formen un tramo posible.
7. Implementar caché y actualización del catálogo.
8. Exponer servicios internos independientes de la interfaz.

Criterio de aceptación: seleccionar origen, ruta y destino en consola mediante datos reales, sin aceptar recorridos imposibles.

### FASE 2 — Interfaz gráfica

Objetivo: disponer de una aplicación de escritorio utilizable.

Tareas:

1. Crear una ventana moderna con CustomTkinter.
2. Implementar pestañas Casa → Trabajo y Trabajo → Casa.
3. Añadir de uno a tres tramos por perfil.
4. Implementar buscadores y desplegables dependientes.
5. Añadir campos de horarios, caminatas, transbordos y márgenes.
6. Crear pantalla de proveedores y credenciales.
7. Guardar y recuperar configuración.
8. Añadir panel de estado del sistema.
9. Evitar que las consultas de red congelen la GUI.

Criterio de aceptación: configurar ambos trayectos, cerrar el programa, volverlo a abrir y recuperar correctamente toda la configuración.

### FASE 3 — Tracking GPS

Objetivo: registrar mediciones reales de duración.

Tareas:

1. Crear recolector periódico de posiciones.
2. Desarrollar selector de vehículo por progreso sobre ruta.
3. Implementar seguimiento de identidad del viaje.
4. Registrar eventos de origen y destino.
5. Calcular duración mediante marcas de tiempo.
6. Detectar posiciones desactualizadas y recorridos inconsistentes.
7. Manejar pérdida de conexión y desaparición del vehículo.
8. Persistir observaciones y mediciones.
9. Agregar una vista de sesiones, estados y resultados.
10. Crear pruebas con trayectorias simuladas.

Criterio de aceptación: completar una medición válida sin confundir dirección, vehículo ni trayecto; rechazar las mediciones con evidencia insuficiente.

### FASE 4 — Predicciones

Objetivo: convertir mediciones históricas en recomendaciones de horarios.

Tareas:

1. Consultar el histórico por perfil, ruta, día y franja horaria.
2. Calcular tiempos esperados para cada tramo.
3. Incorporar tiempos estimados de espera.
4. Incorporar caminatas, transbordos y margen.
5. Recomendar hora de salida.
6. Estimar hora de llegada a casa.
7. Mostrar fuentes de datos, antigüedad y confianza.
8. Crear escenarios sin datos y con datos insuficientes.
9. Validar cálculos mediante pruebas unitarias.

Criterio de aceptación: recibir una hora límite, obtener una recomendación reproducible y poder explicar numéricamente cada componente del cálculo.

### FASE 5 — Telegram y tareas programadas

Objetivo: automatizar mediciones y notificaciones.

Tareas:

1. Integrar el bot de Telegram.
2. Enviar y validar un mensaje de prueba.
3. Configurar las cuatro sesiones diarias.
4. Integrar APScheduler.
5. Programar los avisos de ida y vuelta.
6. Evitar ejecuciones y mensajes duplicados.
7. Recuperarse de errores y reinicios.
8. Crear logs de ejecución y diagnóstico.
9. Añadir inicio automático con Windows.

Criterio de aceptación: ejecutar automáticamente una medición programada y enviar una recomendación de prueba, sin depender de que la ventana de configuración permanezca abierta.

### FASE 6 — Estabilización y distribución

Objetivo: preparar la aplicación para uso diario.

Tareas:

1. Ejecutar pruebas unitarias e integrales.
2. Simular interrupciones prolongadas del proveedor.
3. Verificar consistencia de datos históricos.
4. Medir uso de CPU, memoria y red.
5. Implementar límites de consultas y control de costos.
6. Empaquetar con PyInstaller.
7. Crear instrucciones de instalación y configuración.
8. Validar ejecución en una instalación limpia de Windows.
9. Documentar limitaciones y errores conocidos.

Criterio de aceptación: instalar, configurar y ejecutar la aplicación sin necesitar un entorno de desarrollo activo.

## 5. Reglas obligatorias de ingeniería

- Desarrollar únicamente una fase por iteración.
- Mantener separación entre GUI, lógica de negocio, datos y proveedores.
- No inventar respuestas de API ni presentar simulaciones como datos reales.
- Usar fixtures deterministas cuando no haya internet.
- Todos los cálculos horarios deben ser conscientes de la zona horaria America/Bogota.
- No bloquear el hilo principal de la GUI.
- No mezclar mediciones reales con estimaciones sin etiquetarlas.
- No calcular llegadas en vivo basándose en datos obsoletos.
- Implementar timeouts, reintentos limitados y backoff.
- Evitar consultar a Croma de forma excesiva y registrar costos cuando sea posible.
- Escribir pruebas para la lógica crítica antes de considerarla completa.
- No guardar secretos en el repositorio.
- Incluir `.env.example`, `.gitignore` y README.
- Documentar decisiones técnicas relevantes.
- Utilizar Git y cambios pequeños, comprobables y reversibles.

## 6. Forma de trabajar con Codex

Para cada fase:

1. Revisar el código existente.
2. Presentar un plan técnico breve y los archivos que se modificarán.
3. Implementar únicamente el alcance acordado.
4. Ejecutar pruebas, lint y verificaciones disponibles.
5. Corregir errores encontrados.
6. Explicar qué se implementó, qué se probó y qué queda pendiente.
7. Actualizar el README y el estado del proyecto.

No implementar todo el roadmap en una única respuesta.

## 7. Primera instrucción

**Comienza exclusivamente con la FASE 0.**

Crea la estructura mínima del proyecto, investiga los endpoints reales de GTFS oficial, implementa un lector básico de los feeds y prepara un diagnóstico reproducible.

Antes de pasar a otra fase, muéstrame los resultados obtenidos, las pruebas ejecutadas, las limitaciones encontradas y una propuesta de los siguientes cambios.

Si los feeds oficiales están inaccesibles, implementa pruebas con datos de ejemplo válidos y documenta la limitación. No la ocultes ni sustituyas silenciosamente por datos ficticios.
## 8. Adenda propuesta — Fase 0.5: históricos y snapshots de flota

Esta sección se añade después del plan original, sin eliminar requisitos ni
reescribir las Fases 0–6. Documenta la decisión técnica propuesta a partir de la
Fase 0.5. **No autoriza la Fase 1 ni la implementación de un colector continuo.**
La evidencia y limitaciones están en `docs/PHASE0_5_REPORT.md`.

### 8.1. Resultado y límites de la Fase 0.5

- No se encontró un histórico operativo público verificable por fecha en las
  fuentes consultadas. Los GTFS estáticos archivados contienen programación.
- La captura de TripUpdates carece de eventos de parada; sus timestamps y delays
  no son tiempos históricos de llegada ni duración de viaje.
- Comparar dos versiones estáticas no resuelve la baja coincidencia de viajes.
  Debe aclararse la semántica del productor, especialmente `start_time`, que
  coincide con la hora GPS en todas las posiciones de la captura estudiada.
- El prototipo offline conserva identidades candidatas sin validarlas como
  instancias operativas, y no genera llegadas a partir de desapariciones.

### 8.2. Cambios propuestos en requisitos, manteniendo sus objetivos

**RF-03, fuentes:** mantener GTFS oficial, Croma y modo offline. Añadir una vía
opcional de importación de históricos operativos únicamente si se comprueban
contenido, fechas, cobertura, licencia e identificadores. No equiparar archivos
GTFS estáticos fechados con ejecución real, ni depender de un histórico remoto
que aún no está validado. Croma sigue sujeto a autorización y control de costos.

**RF-04, seguimiento:** separar adquisición de datos y medición. Proponer una
única descarga periódica del snapshot completo de posiciones por proveedor,
compartida entre perfiles y vehículos. Mantener cuatro sesiones diarias, su
separación inicial de 2 h 30 min, intervalo inicial configurable de 40 s,
selección de perfil, fines de semana, duración y finalización. Las sesiones
actúan como ventanas de interés; cada lote puede alimentar varios candidatos.
Conservar la selección individual del vehículo elegible como estrategia de
análisis o compatibilidad, sin que cada selección duplique la descarga del feed.
No se presupone que todas las rutas tengan un patrón identificable.

**RF-05, eventos:** aplicar proyección sobre geometría, dirección, secuencia,
cruces e interpolación a cada trayectoria candidata. Mantener niveles de
confianza y distinción entre paso estimado y detención/embarque. Si falta
identidad o continuidad, rechazar la medición. Ningún timestamp de actualización
se convierte en llegada por suposición.

**RF-06, persistencia:** añadir metadatos de snapshot, hashes de payload/catálogo,
recepción y observación separadas, asociaciones versionadas y estados de
cuarentena. Persistir solo observaciones relevantes y conservar trazabilidad.
Usar unicidad e índices para deduplicar; no sobrescribir contenido contradictorio
al mismo instante. No almacenar placas sin una necesidad funcional explícita.
Mantener todos los datos históricos y controles de duplicados originales.

**RF-07, predicción:** alimentar estadísticas únicamente con mediciones
verificadas o estimaciones etiquetadas, conservando espera, caminatas,
transbordos y margen. Snapshots por sí solos no crean tiempos de trayecto.
Mantener diferenciados datos reales, inferencias GPS y programación estática.

**RF-09, programación:** cuando se implemente la fase correspondiente, usar un
job compartido de adquisición por proveedor, coordinado con las cuatro ventanas
y evitando instancias simultáneas. Mantener proceso de fondo, inicio en Windows,
notificaciones y límites del computador apagado/suspendido. No se implementan
ahora scheduler, inicio automático ni servicio de adquisición.

No cambian los dos perfiles, uno a tres tramos, selectores dinámicos, tolerancias,
horarios, SQLite con migraciones, motor predictivo ni funciones de Telegram
previstas en las fases originales.

### 8.3. Identidad y calidad propuestas

La identidad de una instancia validada incluirá proveedor/feed, vehículo, viaje,
fecha de servicio, inicio verificado, ruta/patrón/sentido y relación con el
horario. El catálogo se registra como procedencia versionada. No usar el ID de
entidad como sustituto del vehículo ni deducir fecha de servicio de la fecha
civil del GPS. Respetar horarios GTFS mayores a 24 horas.

Conservar los campos brutos cuando falten o sean dudosos y asignar candidatos o
segmentos sin confirmar. La clave experimental con `raw_start_time` puede
fragmentarse si el productor cambia ese campo con cada reporte. No eliminarlo,
normalizarlo ni fusionar segmentos hasta disponer de evidencia temporal y una
regla documentada. Cambios de viaje, vehículo, sentido/patrón o huecos deben
cortar continuidad. Resolver o rechazar conflictos de catálogo explícitamente.

Datos antiguos, futuros, repetidos, fuera de orden o contradictorios no avanzan
una trayectoria válida. Una desaparición registra incidente; no implica llegada.

### 8.4. Migración propuesta de la Fase 3

Antes de iniciar esta fase, aprobar diseño y verificar con una muestra real
acotada la identidad y asociación al recorrido. No se autoriza aquí su ejecución.

1. Definir contratos `SnapshotSource`, filtros relevantes, asociación al catálogo,
   identidad candidata/validada y salida de mediciones con confianza.
2. Incorporar migraciones de metadatos, observaciones filtradas e incidentes.
   No importar los experimentos SQLite como si fueran mediciones reales.
3. Construir adquisición compartida desacoplada de las ventanas de medición;
   reusar transporte con timeouts, backoff, límites y control de concurrencia.
4. Reproducir snapshots guardados de forma idempotente antes de habilitar red.
5. Adaptar selector individual para consumir snapshots compartidos y desarrollar
   análisis simultáneo de candidatos sin mezclar identidades.
6. Aplicar el algoritmo de eventos original por trayectoria; persistir completas,
   incompletas y rechazadas con procedencia e incertidumbre.
7. Medir almacenamiento, memoria, huecos y frecuencia en una prueba controlada;
   contrastar 40/60/120 s y condiciones del proveedor. Propuesta inicial de
   retención: observaciones relevantes crudas 30 días, agregados configurables y
   payload completo solo con límite/plazo diagnóstico, todo sujeto a aprobación.
8. Mantener la vista de sesiones y estados cuando corresponda su implementación,
   sin perder los criterios originales de aceptación de Fase 3.

### 8.5. Criterios de aceptación adicionales

- Una fuente remota histórica solo se declara usable tras descargar muestras,
  verificar fechas/eventos y demostrar asociaciones y cobertura del tramo.
- Separar y etiquetar pruebas sintéticas, replay real y conexión en vivo.
- Validar estabilidad del descriptor de viaje en snapshots reales sucesivos,
  incluyendo el caso `start_time`, o rechazar la medición por evidencia insuficiente.
- Una única petición compartida por proveedor/intervalo aun con varios perfiles.
- Replay sin duplicados; cambio de fecha/viaje/vehículo/sentido no mezcla instancias.
- Datos obsoletos, conflictos de timestamp y desapariciones no generan llegadas.
- Dos eventos de paso verificables por recorrido/tiempo, o rechazo documentado;
  nunca usar un timestamp de actualización como sustituto de un evento.
- Límites de disco/retención configurables y medición de crecimiento SQLite con
  índices y WAL; filtros reducen disco, no necesariamente la descarga completa.
- Conservar las 54 pruebas de Fase 0 y las 15 adicionales de Fase 0.5; añadir
  escenarios reales para cualquier regla nueva de identidad o asociación.

La Fase 0.5 entrega investigación, diseño y experimentos offline. **La Fase 1
permanece pendiente de autorización expresa del usuario.**

## 9. División de la Fase 1: Fase 1A y Fase 1B

Adenda aprobada por el usuario para ejecutar exclusivamente la Fase 1A. Se
conservan íntegros el plan original y la adenda de Fase 0.5. La arquitectura de
colector compartido se acepta como dirección futura; **no se autoriza tracking
operativo ni se inicia la Fase 1B**.

### 9.1. Fase 1A — Catálogo GTFS estático (entregada)

Alcance: importar a SQLite el ZIP local validado, con esquema versionado,
procedencia y hash; preservar IDs como cadenas y procesar horarios/geometrías
por lotes. Una base por versión evita mezclar relaciones de distintos ZIP.

Incluye búsquedas de paraderos por nombre/código, estaciones y plataformas,
rutas disponibles por origen, selección de patrón y sentido publicado, servicios
activos según calendario/excepciones y ventana horaria, destinos estrictamente
posteriores y CLI demostrativa. Maneja medianoche, horas mayores a 24 y frecuencias
sin atribuir precisión puntual a ventanas no exactas. Se conservan las 69 pruebas
anteriores y se añaden pruebas offline del catálogo.

Criterios de aceptación cumplidos:

- Catálogo real importado, con hash/procedencia y sin cargar íntegramente los
  9,4 millones de horarios en memoria.
- Importación atómica y reproducible; reimportación idempotente de la misma versión
  sin modificar la base; rechazo de otro ZIP sobre ese destino.
- Flujo origen → ruta/sentido/patrón → destinos, manteniendo plataformas y
  ocurrencias de una parada en bucles.
- Rechazo de destinos anteriores/ajenos, sentidos incompatibles, horarios fuera
  de la ventana y servicios inactivos.
- Calendario semanal, altas/bajas excepcionales, días de servicio anteriores
  tras medianoche y valores GTFS superiores a 24.
- Índices, búsqueda FTS5, controles de integridad, pruebas y lint correctos.
- Informe `docs/PHASE1A_REPORT.md` con mediciones reales y limitaciones de fuente.

La ausencia de `direction_id` en el ZIP real se conserva como desconocida; no se
infiere 0/1 de nombres o geometrías. Los sentidos explícitos se prueban con
fixtures. Los patrones derivados conservan los recorridos publicados.

### 9.2. Fase 1B — Normalización e integración de selección (propuesta, no autorizada)

Propuesta de continuidad para aprobar antes de implementarla:

1. Definir reglas verificables de normalización/presentación de estaciones,
   vagones y paraderos, conservando IDs y plataforma original. No fusionar
   nodos por proximidad ni inventar sentidos ausentes.
2. Exponer contratos estables de selección para los perfiles Casa → Trabajo y
   Trabajo → Casa, de uno a tres tramos, sin implementar todavía la GUI.
3. Definir política de actualización/caché, registro de múltiples versiones,
   activación del catálogo y manejo de selecciones que cambien entre versiones.
4. Ampliar validación y mensajes de servicio condicional, horarios incompletos y
   variantes del GTFS según necesidades acordadas; documentar incertidumbre.
5. Resolver criterios pendientes de selección y servicios internos de la Fase 1
   original, preservando su aceptación de recorridos posibles y reproducibles.

La Fase 1B no incluirá tracking operativo sin aprobación expresa adicional.
Persisten todos los requisitos originales de GUI, medición, predicción,
notificaciones y distribución para sus fases correspondientes. La investigación
de asociaciones Realtime de Fase 0.5 no se sustituye por el catálogo estático.

**No avanzar a la Fase 1B sin autorización expresa del usuario.**

## 10. Adenda de Fase 1B — Servicios de perfil y validación temporal

El usuario aprobó el cierre de la Fase 1A y autorizó exclusivamente esta Fase 1B.
Esta adenda actualiza el estado histórico de autorización de la sección 9.2;
conserva todos los requisitos originales y las adendas anteriores. La arquitectura
del colector compartido sigue siendo dirección futura, sin tracking operativo.

### 10.1. Servicios de catálogo y perfiles entregados

- Reutilizar el catálogo inmutable de Fase 1A mediante servicios tipados de
  paraderos, rutas, patrones y destinos, independientes de CustomTkinter y CLI.
- Mantener IDs y plataformas originales, dirección desconocida cuando no esté
  publicada, ocurrencias de parada y hash de la versión de catálogo.
- Modelar Casa → Trabajo y Trabajo → Casa, de uno a tres tramos, con caminata
  inicial/final, caminata y tolerancia por transbordo, límite de llegada, aviso,
  días activos y margen de seguridad. Mantener explícito el día de llegada.
- Validar secuencias, patrones, calendario, medianoche y horarios mayores a 24.
  Las horas programadas se toman del mismo viaje. Una frecuencia no exacta no
  acredita conexión puntual. La validación de un itinerario de ejemplo no es
  un predictor ni un buscador exhaustivo de todas las combinaciones.
- Conservar los minutos de caminata declarados. Todo transbordo advierte que su
  conexión espacial no está verificada; proximidad y pertenencia a una estación
  no prueban un paso peatonal accesible. No implementar una red peatonal ficticia.
- Exponer `Result` versión 1 con datos tipados, errores y advertencias por código
  y campo. La futura GUI no debe interpretar mensajes de una CLI.
- Persistir en SQLite separado del catálogo, sin campos de credenciales, con
  revisión esperada e historial. Un perfil por dirección de desplazamiento.

Política de catálogo: importar cada ZIP a un archivo nuevo, registrar hash/ruta,
activar explícitamente la versión y avisar qué perfiles conservan referencias
antiguas. No reemplazar sus IDs silenciosamente. Una migración exige vista previa,
revalidación contra el nuevo catálogo y aplicación explícita con revisión
esperada. Si falta un patrón o una versión, informar el conflicto y conservar
el perfil y catálogo anteriores. No hay descarga automática ni limpieza de versiones.

### 10.2. Diagnóstico Realtime y límite de evidencia

Se entrega un comando separado de cualquier colector de producción. Para una
futura prueba real exige revisión documentada de condiciones aplicables, con
fecha, endpoint, evidencia y límites. El máximo interno es 16 capturas en un
plan de 15 minutos, con al menos 60 segundos entre intentos, sin recuperación
en ráfagas ni reintentos; reserva tiempo de finalización antes del límite.
Los límites internos no constituyen permiso del proveedor.

La revisión pública del 12-11-2026 no estableció una cadencia aplicable. Se usó
el fallback offline autorizado; **no se ejecutaron snapshots reales sucesivos**.
Esto no afirma una prohibición general del proveedor. La política actual
`not_established` bloquea la captura antes de HTTP. No hay Croma ni claves.

El formato conserva fuente/hash, inicio de petición, recepción, timestamps de
feed y GPS, vehículo, viaje, ruta, inicio/fecha de servicio, parada, secuencia,
estado y coordenadas, distinguiendo presencia real de valores por defecto.
Las capturas antiguas sin recepción exacta se etiquetan como tal.

El analizador contrasta referencias exactas con el catálogo y clasifica
asociaciones verificadas, ambiguas, contradictorias y no resueltas. Verificar
referencias de catálogo **no verifica identidad operativa**. Compara campos
de viaje/vehículo, cohorte, frescura, continuidad y progreso sobre geometría;
umbrales diagnósticos no son calibración de producción. No usa sufijos de IDs,
no fuerza coincidencias y no convierte timestamps GPS en llegadas.

Una captura real antigua no aporta pares temporales. Los tres snapshots
sintéticos prueban que cambios de `start_time` se detectan y generan ambigüedad;
no prueban cambios del productor real. Los resultados permanecen separados.

### 10.3. Criterios de aceptación y continuidad

- Conservar las 99 pruebas anteriores y añadir contratos GUI, perfiles de uno a
  tres tramos, errores, calendarios, medianoche, transbordos y versionado explícito.
- Activar un catálogo no cambia perfiles; una migración inválida no los modifica.
  Rechazar el catálogo como destino del almacén de perfiles.
- Probar límites del diagnóstico, bloqueo sin condiciones establecidas, errores
  HTTP sin reintentos y replay offline con datos claramente etiquetados.
- Entregar `docs/PHASE1B_REPORT.md`, ejemplos y evidencia separada de ejecución.
  Resultado: **138 pruebas aprobadas (99 + 39)**, Ruff/formato y `pip check`
  correctos en Python 3.13.14; no se añadieron dependencias.

Los servicios y el diagnóstico offline quedan entregados. **La estabilidad de
identidades reales sigue pendiente de validación**, no se declara resuelta por
los fixtures. Antes de Fase 3, además de su aprobación, se requiere una serie
real acotada permitida y evidencia para la política de identidad.

La identidad futura debe conservar proveedor, vehículo, viaje, fecha de servicio,
ruta/patrón/sentido e inicio de instancia verificado, con procedencia de catálogo.
Si el inicio cambia con GPS, mantener el campo bruto y la ambigüedad hasta aclarar
su semántica; no descartarlo ni fusionar automáticamente. No inferir fecha de
servicio del día civil GPS. Cambios, huecos y regresiones cortan o ponen en duda
continuidad; desapariciones no confirman llegadas. Se mantienen los criterios
de migración de Fase 3 de la sección 8.4 y sus requisitos originales de eventos.

**No iniciar Fase 2 ni Fase 3 sin autorización expresa del usuario.** No se
implementan aquí GUI, Telegram, predicción, seguimiento continuo ni scheduler.

## 11. Adenda de Fase 2 — GUI de escritorio

El usuario aprueba el cierre de Fase 1B y autoriza exclusivamente la GUI de
escritorio. Esta adenda actualiza el estado de autorización anterior sin eliminar
requisitos ni conclusiones de las fases previas. La identidad operativa real
continúa pendiente; implementar la GUI no resuelve esa investigación.

### 11.1. Alcance entregado

- Paquete `src/transmitracker/gui/`, separado del dominio. CustomTkinter con tema
  oscuro inicial/claro, navegación lateral, panel desplazable, estados de carga,
  textos en español y adaptación de ventana/textos al escalado DPI de Windows.
- Dashboard, Casa → Trabajo, Trabajo → Casa, Configuración y Diagnóstico.
- Autocompletado con debounce y límite de resultados sobre la búsqueda FTS del
  catálogo; selección explícita de estación/plataforma y búsqueda exacta por ID.
  No cargar más de 8.000 paraderos en un selector ni duplicar consultas SQL en GUI.
- Flujo origen → ruta → patrón → destino posterior basado en `CatalogService`.
  Mostrar nombres y ocurrencias, mantener sentido desconocido cuando falte y
  distinguir patrones por destino habilitado, plataforma y secuencia.
- Uno a tres tramos y todos los campos de `Profile`/`Transfer`: caminatas inicial/
  final, transbordos con tolerancia, margen, límite, aviso, días, ventana y llegada
  al día siguiente. Validación exclusivamente mediante los servicios anteriores.
- Invalidar selecciones dependientes cuando cambia el origen, el horario o un
  tramo previo. En los siguientes tramos consultar desde la llegada programada
  anterior más la caminata/tolerancia del usuario, sin asumir conexión espacial.
- Un trabajador controlado para datos locales, conexiones SQLite propias por
  operación y cola de resultados procesada en el hilo Tk. Cancelación de tareas
  pendientes y descarte de respuestas obsoletas, sin widgets en hilos secundarios.
- Persistencia con `ProfileStore`: crear, editar, recuperar, revisión esperada,
  avisos de conflicto y catálogo antiguo. Ninguna migración silenciosa. El editor
  de un perfil antiguo conserva su catálogo; la migración sigue siendo explícita
  mediante los servicios de Fase 1B, sin un asistente de remapeo automático.
- Preferencias locales en JSON, perfiles en SQLite separado y secretos opcionales
  solo en `.env` excluido de Git. Campos enmascarados y aviso de ausencia de cifrado.
  Configurar claves, intervalos o avisos no activa integraciones ni un scheduler.
- Dashboard y diagnóstico distinguen programación estática, validación por fecha
  y estado pendiente de Realtime. No presentar predicciones ni tracking activo.

### 11.2. Criterios de aceptación

1. Abrir la ventana, buscar una estación real de Bogotá, elegir ruta/patrón y
   destino posterior, configurar tolerancias y guardar un perfil.
2. Cerrar/reabrir y recuperar configuración, selección y revisión del perfil.
3. Mantener las 138 pruebas previas; añadir controladores, persistencia, errores,
   privacidad de configuración, conflictos/versiones y ventanas Tk separadas.
4. Verificar origen → ruta → patrón → destino y guardado/reapertura con ventanas
   reales; comprobar navegación con catálogo ausente y ausencia de HTTP inesperado.
5. Ruff, formato, pytest y `pip check` correctos en Python 3.13; informe
   `docs/PHASE2_REPORT.md`, evidencia y README con el comando de apertura.
6. Ejemplo offline con catálogo oficial en un espacio de demostración separado,
   sin inventar recorridos personales ni modificar el catálogo inmutable.

Se conservan las limitaciones de horarios no exactos, validación de un itinerario
programado de ejemplo y transbordos sin red peatonal verificada. No se inicia
recolección para suplir esas limitaciones.

**No iniciar Fase 3 sin autorización expresa.** Permanecen fuera de esta entrega
tracking continuo, reconstrucción operativa, predictor, scheduler de producción,
envío real de Telegram, consultas de pago de Croma y empaquetado PyInstaller.

## 12. Adenda de Fase 2.1 — QA, persistencia y recorridos habituales

El usuario aprueba el cierre de Fase 2 y autoriza correcciones y refinamiento de
UX exclusivamente. Se mantienen los requisitos originales y las adendas como
historial; esta sección sustituye la exigencia anterior de fecha/salida para
guardar, sin eliminar la herramienta opcional de horarios programados.

### 12.1. Integridad del formulario

- Estado por tramo con identidad estable, valores, textos, nombres, opciones y
  modalidad. Añadir/eliminar conserva los tramos restantes y cancela respuestas
  asíncronas de widgets destruidos. Revisar los transbordos cuya conexión cambió.
- Errores y resultados temporales separados del formulario. Una consulta fallida
  no ejecuta limpieza anticipada. Solo selecciones explícitamente incompatibles
  invalidan sus dependencias; cambiar caminatas u horarios no borra el recorrido.
- Callbacks y referencias a widgets en el hilo principal; el trabajador recibe
  únicamente datos/controladores sin Tk. Descartar resultados obsoletos y liberar
  ciclos de ventanas destruidas en el hilo de interfaz al reabrirlas.

### 12.2. Guardado y validaciones

- Guardar configuración estructural sin fecha ni salida: validar catálogo fijado,
  ruta/patrón/sentido, ocurrencias, subida/bajada y destino posterior.
- Casa → Trabajo requiere límite de llegada y días activos; la recomendación de
  salida pertenece al predictor futuro. Trabajo → Casa no exige llegada y admite
  salida habitual opcional. No fabricar duraciones ni horas absolutas sin datos.
- Borradores incompletos en tabla separada del último perfil configurado, con
  revisión propia, revisión base y presentación reanudable. Un conflicto no
  sobrescribe otra edición. Preservar el historial y JSON de perfiles de Fase 2.
- Migración aditiva del almacén de esquema 1 a 2: tablas de borradores y consultas
  programadas, sin reescribir perfiles o versiones antiguas del catálogo.
- Estados: incompleto/borrador, configurado, horario de ejemplo validado para una
  revisión e instante, pendiente de migración. La consulta temporal es opcional
  y conserva calendarios y reglas de medianoche de Fase 1B.
- `ARRIVAL_DEADLINE_EXCEEDED` solo en consulta Casa → Trabajo; no bloquea guardado
  estructural. `TRANSFER_PATH_UNVERIFIED` es informativo y conserva caminatas.
- «Horizonte de búsqueda de buses programados» en opciones avanzadas con ayuda;
  no se presenta como espera histórica. Contrato de espera esperada nulo y base
  no disponible hasta que exista evidencia y autorización para su cálculo.

### 12.3. Selección, diseño y versiones

Mantener origen → ruta → patrón → destino y añadir ruta → patrón → origen →
destino por tramo. Buscar rutas por número, nombre corto y largo; filtrar nodos
por patrón, permisos y secuencia. Alternar modalidad conserva selecciones
compatibles y el sentido desconocido no se inventa.

Dashboard con tarjetas de ambos perfiles, estados, resúmenes y distinción entre
programación, históricos sin estimaciones y Realtime deshabilitado. Ayuda visible,
tooltips, enlaces de documentación y controles futuros claramente deshabilitados.
Explicar almacenamiento local y `.env` sin cifrado.

Versión inspeccionada 0.0.1 → entrega 0.1.0. Semantic Versioning con fuente única
`pyproject.toml`; versión visible en GUI, README y futura distribución.
Política documentada en `docs/VERSIONING.md`, uso en `docs/USAGE.md`.

### 12.4. Aceptación y límites

Conservar las 160 pruebas; ajustar con explicación las que exigían la limpieza
del diseño anterior, sin eliminarlas. Añadir regresiones de pérdidas de estado,
borradores/reapertura, los dos perfiles, selección por ruta, cambios de modalidad,
respuestas obsoletas, revisiones, catálogos antiguos y versión. Ejecutar pytest,
Ruff, formato y pip check en Python 3.13. Entregar `docs/PHASE2_1_REPORT.md`,
evidencia offline, ejemplo estático real separado y capturas actualizadas.

Resultado de entrega: **183 pruebas aprobadas (160 anteriores + 23 nuevas)**,
Ruff/formato y pip check correctos en Python 3.13.14; sin dependencias nuevas.
QA con catálogo real: guardado/recuperación de tres y un tramos sin fecha/salida,
advertencias no bloqueantes y hash del SQLite original conservado.

No se modifican datos GTFS originales. No implementar GPS, reconstrucción,
predictor, Croma de pago, Telegram operativo ni scheduler. **No iniciar Fase 3A
sin aprobación expresa.**

## 13. Adenda de Fase 3A — Reconstrucción GPS offline

El usuario acepta Fase 2.1 y autoriza exclusivamente Fase 3A. Esta adenda conserva
los requisitos originales y las investigaciones anteriores. Actualiza la entrega
a **0.2.0**, sin habilitar seguimiento, predictor, Croma, Telegram ni scheduler.

### 13.1. Evidencia e identidad

- Motor modular en `src/transmitracker/reconstruction/`, independiente de Tk.
  Modelos tipados de snapshots, originales/normalizados, identidades candidatas,
  segmentos, proyecciones, eventos, mediciones y rechazos.
- Conservar fuente/endpoint, hashes, tiempos de feed/reporte/recepción separados,
  descriptor original, patrón y ocurrencia de parada. No completar campos ausentes.
- Agrupar por proveedor/endpoint/vehículo; conservar cambios de viaje e inicio,
  cortes, desapariciones y conflictos. No usar sufijos ni cercanía para inventar
  asociaciones. Distinguir referencias exactas, continuidad e identidad operativa.
- La identidad sintética requiere declaración independiente de la verdad de cruce;
  nunca puede autorizar una asociación real. `operationally_verified` sigue false.

### 13.2. Geometría y mediciones

- Proyectar sobre geometría del viaje/patrón exacto, con progreso y velocidad
  observados. Soportar patrones distintos de una ruta, ramales, bucles, cruces y
  ocurrencias repetidas; rechazar candidatos ambiguos y anclajes insuficientes.
- Ordenar GPS, deduplicar, validar recencia/campos y segmentar saltos, retrocesos,
  huecos y cambios de descriptor con umbrales configurables/documentados.
- Separar GPS observado de posiciones animadas/extrapoladas, conforme al aprendizaje
  conceptual de Paradero. No importar velocidades iniciales como verdad operacional.
- Estimar cruces con observaciones a ambos lados, intervalo y soporte. Interpolar
  un punto solo con continuidad, bracket corto y velocidad compatible. Mantener
  null cuando solo existe un intervalo; no etiquetar cruces como llegadas observadas.
- Distinguir estacionariedad con estado publicado, cruce y evento no determinable.
  Medir únicamente entre ocurrencias posteriores del mismo segmento y propagar
  incertidumbre de extremos; espera y caminata no se infieren.

### 13.3. Persistencia, replay y contratos futuros

- SQLite GPS separado de catálogo/perfiles: migración inicial de esquema 1,
  índices, originales reproducibles, sightings, parámetros, versión/huella del
  algoritmo y rechazos. Repetir una ejecución idéntica no reescribe filas;
  otra configuración/versión conserva procedencia y resultados anteriores.
- CLI local con capturas guardadas verificadas por hash y fixtures sintéticos
  explícitos. Perfil JSON o SQLite de solo lectura como entrada de tramos,
  sin descargar datos, modificar la GUI ni generar tareas de fondo.
- Interfaces desacopladas de proveedores y presupuesto de créditos; especificar
  reservas, consumo estimado/confirmado, bloqueo, caché, singleflight y dry-run.
  Valores 1.500/10/1 suministrados por el usuario, configurables; clasificación de
  endpoints pendiente. No implementar cliente Croma ni realizar consultas.

### 13.4. Aceptación y transición

1. Conservar los 183 casos anteriores y añadir 54 de unidad/integración/replay;
   ejecutar pytest, Ruff, formato y pip check en Python 3.13.
2. Evaluar 23 escenarios sintéticos, cadencias de 20/40/90 s, error mediano/P90,
   detección, falsos positivos, cobertura y rechazo frente a geocerca simple.
   Documentar que la matriz de cadencias corresponde al recorrido normal y no
   sustituye calibración con errores reales.
3. Acreditar incertidumbre, ocurrencias repetidas, múltiples vehículos, cortes e
   idempotencia. Ninguno de los 12 escenarios inseguros debe aceptar una medición.
4. Reprocesar evidencia real guardada solo para parsing/asociaciones, sin declarar
   velocidades, llegadas ni validación operativa con un snapshot aislado.
5. Entregar `docs/PHASE3A_REPORT.md`, métricas/evidencias y
   `docs/CROMA_INTEGRATION_DESIGN.md`; conservar originales y hashes previos.

Resultado de entrega: **237 pruebas aprobadas (183 anteriores + 54 nuevas)** en
274,91 s; Ruff, formato (89 archivos) y pip check correctos en Python 3.13.14.
Las cinco entradas protegidas mantienen sus hashes. La evaluación es sintética;
el replay de una captura real produce cero cruces/mediciones aceptados.

Para Fase 3B son necesarios autorización expresa, revisión de condiciones/costes
y clasificación de operaciones del proveedor, presupuesto con reservas, identidad
verificada independientemente y un experimento real acotado permitido con verdad
de referencia para calibrar errores e intervalos. Antes del colector compartido
de producción siguen pendientes calidad operativa, rendimiento, retención y
política de sondeo. La agrupación visual por parent_station/andén queda posterior.
**Fase 3B no iniciada; no activarla sin autorización expresa.**
