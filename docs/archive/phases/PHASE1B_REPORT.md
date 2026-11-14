# Fase 1B — Servicios de perfil y validación temporal

## Resultado y alcance

Se entregan servicios independientes de GUI, modelos tipados de los dos perfiles,
validación de uno a tres tramos, persistencia separada y actualización explícita
de referencias de catálogo. Se reutiliza la base de Fase 1A sin reimportarla.

El comando de diagnóstico temporal está preparado y probado offline. **No se
ejecutó una nueva serie real**: las condiciones públicas revisadas no establecen
una cadencia aplicable al feed. No se interpretó la publicación cada 26 segundos
como permiso para consultar cada 60. Esto no demuestra una prohibición general;
significa que no quedó establecido el permiso aplicable para esta prueba.

La evolución de identidades **reales** entre capturas sigue sin validar. Se
separan una captura real antigua y tres capturas sintéticas sucesivas. No se
implementaron GUI, Telegram, predictor, colector de producción ni tareas de fondo.
**No se iniciaron las Fases 2 o 3.** No hubo uso de Croma ni paquetes nuevos.

## Servicios de catálogo y contratos

`CatalogService` delega búsquedas y reglas de embarque/recorrido/calendario en
`catalog.queries.Catalog`. No duplica SQL de catálogo, calendarios, excepciones,
frecuencias ni expansión de estaciones. El único cambio al lector de Fase 1A
añade `boarding_at` y `origin_platform_id` a cada destino, tomados **del mismo
viaje de ejemplo** que su llegada programada. Así se valida una conexión con
horas coherentes, sin combinar salida de un viaje y llegada de otro.

| Servicio | Datos tipados |
| --- | --- |
| `search_stops(query)` | `Result[tuple[StopChoice, ...]]` |
| `routes(origin, when)` | `Result[tuple[RouteChoice, ...]]` |
| `patterns(origin, when)` | `Result[tuple[PatternChoice, ...]]` |
| `destinations(leg, when)` | `Result[tuple[DestinationChoice, ...]]` |
| `validate(profile, departure_at)` | `Result[ProfileCheck]` |

`Result.to_dict()` es contrato versión 1, con `ok`, `data`, `errors`, `warnings`
y `contract_version`. Los errores/avisos tienen `code`, `field` y `message`.
La futura GUI puede localizar por código y asociar errores a campos sin analizar
texto de CLI. Los servicios no imprimen ni importan CustomTkinter.

Ejemplo de rechazo consumible por GUI:

```json
{
  "contract_version": 1,
  "ok": false,
  "data": null,
  "errors": [{
    "code": "INVALID_SEQUENCE",
    "field": "legs.0",
    "message": "Destination occurrence must follow origin"
  }],
  "warnings": []
}
```

Códigos relevantes: `INVALID_PAYLOAD`, `LEG_COUNT`, `TRANSFER_COUNT`,
`INVALID_MINUTES`, `INVALID_WEEKDAYS`, `INVALID_DIRECTION`, `INVALID_SEQUENCE`,
`INVALID_DATETIME`, `PROFILE_INACTIVE_DAY`, `LEG_SERVICE_INVALID`,
`SCHEDULE_TIME_UNRESOLVED`, `ARRIVAL_DEADLINE_EXCEEDED`,
`CATALOG_VERSION_MISMATCH`, `CATALOG_UNAVAILABLE` y `PROFILE_REVISION_CONFLICT`.
Los constructores de recursos pueden rechazar una ruta/base incompatible;
las operaciones de selección/validación y persistencia documentadas devuelven
resultados estructurados para sus errores de dominio.

## Modelos y validación

Los dataclasses inmutables `Profile`, `Leg` y `Transfer` modelan:

- Clase de perfil: `home_to_work` o `work_to_home`; hasta uno persistido por clase.
- Hash del catálogo, IDs originales y ocurrencias exactas de origen/destino.
- Entre uno y tres tramos y exactamente un transbordo por conexión entre tramos.
- Minutos de caminata inicial/final, caminata y tolerancia por transbordo,
  margen de seguridad, días activos, hora límite y hora de aviso.
- Desfase explícito de llegada de 0/1 día y ventana de embarque configurable.

Los minutos son enteros no negativos (hasta 1.440; ventana mínima de un minuto).
Los días son 0=lunes a 6=domingo, sin duplicados. Las horas de configuración son
relojes locales de America/Bogota; los instantes de validación requieren zona.
Los IDs no se convierten a números. La dirección desconocida permanece `None`.
El decodificador JSON rechaza campos desconocidos, incluidos campos de secretos.

Para la hora de salida indicada, se suma caminata inicial, se consulta el primer
embarque programado elegible de cada tramo y se valida su destino posterior.
Se usa el calendario de servicio del catálogo, que puede pertenecer al día
anterior en viajes de más de 24 h. Al llegar se conserva íntegramente la caminata
y tolerancia indicadas para el transbordo antes de buscar el siguiente embarque.
Al final se añaden caminata final y margen y se comparan con la hora límite.

Es una **validación de un itinerario programado de ejemplo**, no un predictor
ni una búsqueda de todas las combinaciones óptimas. Si el primer itinerario
probado incumple la hora límite, el código describe ese resultado; no demuestra
que ninguna combinación alternativa pueda llegar antes. No se recomiendan
horas de salida ni se usan posiciones en vivo para esas validaciones.

Las frecuencias sin hora exacta y horas ausentes no prueban conexiones temporales:
se devuelve `SCHEDULE_TIME_UNRESOLVED`. La selección de catálogo sigue disponible,
pero no se guarda como perfil temporalmente validado hasta resolver esa falta de
evidencia. No hay modo de borrador persistente en esta entrega.

### Transbordos

Cada transbordo produce `TRANSFER_PATH_UNVERIFIED`, incluso entre plataformas
de una estación o en el mismo nodo. No hay una red peatonal verificada, ni se
declara conexión por cercanía. El tiempo del usuario no se sustituye por cero
ni por una distancia calculada. Un resultado puede ser `ok=true` **con aviso**:
demuestra la conexión horaria declarada, no la existencia/accesibilidad del paso.

`spatial_connections_verified` se refiere exclusivamente a las conexiones entre
tramos; es vacuamente verdadero si no hay transbordos. **No verifica caminatas
desde casa/trabajo**, cuyas direcciones y trayectorias no forman parte del modelo.
La hora de aviso posterior a la salida genera `NOTICE_AFTER_DEPARTURE`; no se
programan notificaciones.

## Persistencia y cambio de catálogo

`ProfileStore` usa SQLite separado, con esquema versión 1:

| Tabla | Contenido |
| --- | --- |
| `profiles` | Perfil actual, clase, hash de catálogo, revisión y JSON tipado |
| `profile_revisions` | Versiones anteriores y resultado de validación |
| `catalog_registry` | Hash y ruta local de cada catálogo registrado |
| `active_catalog` | Puntero de catálogo activo, sin modificar sus tablas |
| `catalog_events` | Historial de activaciones explícitas |

El almacén se niega a abrir un catálogo como base de perfiles. Se usan consultas
parametrizadas, transacciones y revisión esperada para evitar sobrescribir una
edición concurrente. No existen columnas para claves o credenciales; se guarda
solo el modelo de perfil y metadatos de validación/versión. No se carga `.env`.
Crear usa `expected_revision=0`; actualizar requiere la revisión leída.

Política implementada:

1. Importar un nuevo ZIP a **otro archivo** con el importador de Fase 1A; no hay
   descarga/actualización automática en esta fase.
2. Registrar su hash y comprobar que la ruta no se reutiliza para otra versión.
3. Activar explícitamente el nuevo catálogo. Los perfiles existentes **conservan
   el hash anterior** y el cambio devuelve sus IDs afectados.
4. Al cargarlos aparece `PROFILE_CATALOG_NOT_ACTIVE`. Su catálogo anterior sigue
   disponible; no se borran ni se reinterpretan sus IDs.
5. `preview_migration` crea una propuesta y valida de nuevo patrones, paradas,
   secuencias y servicios para la fecha solicitada, sin escribir el perfil.
6. `apply_migration` exige la revisión esperada, vuelve a validar y solo entonces
   guarda una revisión nueva. Si desaparece un patrón, se rechaza la aplicación
   y permanece el perfil original. Un catálogo ausente se informa; no se sustituyen IDs.

`preview_migration().ok` indica que pudo construirse la propuesta; su
`data.validation.ok` indica si esta es válida. La aplicación nunca confía solo
en ese JSON: revalida. No hay remapeo difuso de perfiles ni limpieza automática
de catálogos antiguos. Cada hilo futuro debe abrir sus propias conexiones.

## Ejemplos reproducidos con el catálogo real

`PHASE1B_PROFILE_EXAMPLES.json` contiene ejemplos técnicos, **no los trayectos
reales del usuario ni una afirmación de dónde están su casa o trabajo**.
Las dos clases de perfil se prueban con el mismo tramo publicado para demostrar
persistencia independiente; la etiqueta de regreso no convierte ese tramo en
el retorno real del usuario.

Tramo del ejemplo: plataforma `74389`, ruta `13766` / 2-1, patrón conservado de
Fase 1A, origen secuencia 2, destino `56059` secuencia 3, dirección desconocida.

| Caso | Resultado estático para 12-11-2026 |
| --- | --- |
| Salida 08:00, caminata inicial 2 min | Disponible 08:02; embarque 08:04:56; llegada de bus 08:12:21 |
| Final 5 min + margen 3 min, límite 09:00 | Fin de ejemplo 08:20:21; válido |
| Segunda clase, salida 17:00 y límite 18:00 | Fin de ejemplo 17:22:45; válido y persistido separadamente |
| Dos tramos con caminata de transbordo 7 min + tolerancia 2 min | Segundo listo 08:21:21; embarque 08:23:51; fin 08:32:59; válido con aviso espacial |
| Forzar dirección 0 cuando el GTFS no la informa | `LEG_SERVICE_INVALID`, campo `legs.0` |
| Límite de llegada 07:00 para la salida 08:00 | `ARRIVAL_DEADLINE_EXCEEDED` |
| Destino en secuencia 1 desde origen secuencia 2 | `INVALID_SEQUENCE` |

Se guardaron dos perfiles de ejemplo, revisión 1, en un archivo
`data/phase1b/profiles_demo_<id>.sqlite3`, separado del catálogo. El script genera
un almacén de ejemplos nuevo en cada ejecución para no modificar perfiles del
usuario. Se verificó hash y mtime del catálogo real antes/después: **sin cambios**.

## Revisión del proveedor y decisión de red

El 12-11-2026 a las **23:45 America/Bogota** se consultaron una vez:

- Portal GTFS: HTTP 200.
- `manifest.json`: HTTP 200; metadatos de frecuencia de generación, no cuota.
- `robots.txt`: HTTP 404; no se infiere autorización.
- [Términos públicos del sitio](https://www.transmilenio.gov.co/comunicaciones/publicaciones/2025/terminos-y-condiciones-en-el-sitio-web-de-transmilenio):
  HTTP 200; condiciones generales y restricciones de uso, sin una cadencia
  específica identificada para el feed de este subdominio.

Se guardaron URLs, fecha y hashes en `PHASE1B_PROVIDER_REVIEW.json`. La decisión
`not_established` está en `PHASE1B_EXPERIMENT_POLICY.json`. **No es un permiso
ni una conclusión de que todo acceso al feed esté prohibido.** Para esta entrega
se optó por el fallback offline autorizado en la solicitud. No se solicitó una
clave, no se contactó al proveedor ni se ejecutaron consultas sucesivas.

## Comando diagnóstico preparado

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
.\.venv\Scripts\python.exe -m transmitracker.research.snapshot_diagnostic capture --review docs/PHASE1B_EXPERIMENT_POLICY.json --count 3 --interval 60
```

**Con la revisión actual se rechaza antes de cualquier HTTP o creación de captura.**
Una futura revisión sustentada en condiciones aplicables deberá declarar endpoint,
evidencia, límite de capturas, intervalo mínimo y fecha vigente. No basta cambiar
un booleano sin evidencia del proveedor. El comando no determina por sí solo
permisos legales.

Límites internos, independientes de lo que llegue a permitir el proveedor:

- 2–16 capturas solicitadas, intervalo mínimo 60 s y plan de hasta 900 s.
- Una petición por intento; sin reintento ni ráfagas de recuperación. Un error,
  incluido 429, detiene la serie. No sigue redirecciones ni acepta otro endpoint.
- Reserva de 60 s antes del límite de 15 minutos para finalización HTTP. Por ello
  una solicitud de 16 capturas a 60 s puede terminar en 15, en vez de prolongarse.
- Timeouts/tamaño acotados, directorio único, revisión copiada y registro final.
  No hay cron, scheduler, daemon ni ejecución indefinida.

Cada captura nueva guardaría PB y JSON con fuente, hash, inicio de petición,
recepción al completar la descarga, timestamp del feed y de cada vehículo,
vehículo/viaje/ruta/inicio/fecha/parada/secuencia/estado y coordenadas.
`reported_fields` distingue campos publicados de valores por defecto GTFS.
`analyze` reabre el PB, verifica su hash y reconstruye los datos; no confía en
coordenadas JSON editadas. Las rutas de CLI quedan dentro del proyecto.

## Evidencia real guardada y clasificación

Se reutilizó **una** captura de Fase 0, verificando su hash original. Solo quedó
registrado entonces el inicio de consulta, no la recepción exacta: se conserva
como referencia aproximada con `receipt_timestamp_verified=false`. **No se
inventó un timestamp de recepción.** El comando nuevo sí registra recepción.

Con referencia de frescura a ese inicio de consulta y catálogo de Fase 1A:

| Asociación de referencia | Observaciones |
| --- | ---: |
| Verificadas respecto a IDs de catálogo, parada/secuencia y calendario | 17 |
| Contradictorias | 167 |
| No resueltas | 2.381 |
| Ambiguas en esta captura | 0 |

Desglose: 2.351 viajes no encontrados, 30 registros sin frescura suficiente,
156 conflictos viaje/ruta y 11 conflictos parada/secuencia. El filtro temporal
se aplica antes de contar el resultado final, por lo que estas cifras no son
idénticas al conteo más simple de Fase 0/0.5.

**“Verificada” aquí solo significa referencias exactas, no instancia operativa
probada ni dirección observada.** Los ejemplos y motivos están en
`PHASE1B_REAL_SAVED_ANALYSIS.json`. Hay cero pares reales comparables, por lo que
`real_temporal_validation=false` y `operational_identity_validated=false`.
No hay evidencia nueva de que los IDs reales sean estables o cambien entre capturas.
La correlación entre `start_time` y reloj GPS observada antes permanece como
hipótesis sobre el productor, no como una regla autorizada para fusionar viajes.

## Validación temporal sintética y política para Fase 3

`phase1b_temporal.json` simula tres snapshots y dos vehículos sobre un catálogo
sintético separado. Uno cambia `start_time` siguiendo el reloj GPS; el otro
conserva `25:00:00` de su día de servicio anterior. Resultado:

- Cuatro pares de vehículo comparados; dos cambios de `start_time` con GPS nuevo.
- Dos pares pasan a **ambiguos** por inicio cambiante; dos conservan referencias
  verificadas y geometría compatible, sin declarar probada la instancia.
- Se comparan viaje, ruta, fecha, secuencia, cohorte de IDs y progreso geométrico.
  Los fixtures adicionales ejercitan las cuatro clases, desaparición, cambio de
  viaje, secuencia regresiva, datos viejos y replay sin movimiento nuevo.
- La superposición de IDs de vehículo no prueba identidad física: un ID que
  aparece/desaparece no se renombra por suposición. Se informa por cohorte y fuente.
- **Cero llegadas y cero duraciones de trayecto inferidas.** Los resultados
  sintéticos se guardan separados y nunca se etiquetan como verificación real.

La proyección usa polilíneas publicadas del patrón asociado exactamente. Informa
distancia residual, progreso, desplazamiento y tiempo entre GPS. Los umbrales
diagnósticos —150 m residuales, ruido de progreso de 15 m, empate de 5 m y
velocidad aparente de 40 m/s— son candidatos, no calibración de tracking. Las
intersecciones con varias proyecciones plausibles no se declaran inequívocas.
Progreso significa avance sobre el orden de la geometría, no sentido 0/1 inventado.

Recomendación para Fase 3:

1. Conservar observación bruta, proveedor/feed, catálogo y fecha/hora de recepción
   separadas del timestamp GPS. La clave de observación no debe perder revisiones
   contradictorias al mismo instante.
2. Usar vehículo + viaje + fecha de servicio + ruta/patrón/sentido e inicio de
   instancia **verificado** para agrupar un recorrido. No usar el sufijo de `trip_id`.
3. Si `start_time` cambia con cada GPS, mantenerlo como evidencia y clasificar
   el segmento como ambiguo hasta aclarar semántica. No eliminarlo de la identidad
   ni sustituirlo automáticamente por la primera hora observada.
4. No inferir fecha de servicio de la fecha civil GPS al cruzar medianoche.
   Cambios de viaje, fecha, proveedor, patrón, huecos o regresiones cortan o ponen
   en duda la continuidad; desaparecer nunca confirma una llegada.
5. Antes de habilitar tracking, obtener una serie real acotada permitida, comprobar
   estabilidad y asociación a recorrido y calibrar las reglas con evidencia.

## Pruebas, reproducción y archivos

**138 pruebas aprobadas: 99 anteriores + 39 nuevas**. Python 3.13.14 / Windows;
Ruff y formato correctos, `pip check` sin conflictos. Evidencia de ejecución en
`PHASE1B_VALIDATION_RESULTS.json`. Los tests bloquean sockets/transporte real;
el comportamiento HTTP del diagnóstico se prueba con MockTransport y reloj
simulado, no mediante consultas reales al proveedor.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE1B_VALIDATION_RESULTS.json
.\.venv\Scripts\python.exe scripts/demo_phase1b.py
.\.venv\Scripts\python.exe -m transmitracker.research.snapshot_diagnostic analyze data/phase1b/synthetic_captures/snapshot_0.json data/phase1b/synthetic_captures/snapshot_1.json data/phase1b/synthetic_captures/snapshot_2.json --catalog data/phase1b/synthetic_catalog.sqlite3 --output data/phase1b/cli-synthetic-analysis.json
```

Estos comandos son offline. `review_phase1b_conditions.py` es la herramienta
separada de lectura documental que sí hace los cuatro GET públicos.

Archivos principales:

- `profiles/models.py`, `contracts.py`, `services.py`, `store.py`.
- `catalog/queries.py`: dos campos aditivos de procedencia horaria, sin cambio de base.
- `research/temporal.py` y `snapshot_diagnostic.py`.
- Dos módulos de pruebas, fixture temporal y scripts de revisión/demo.
- Informe, política de experimento y cinco registros JSON de revisión/ejemplos/
  análisis/validación; bases y PB de ejemplo en `data/phase1b/`, excluidos de Git.
- README y adenda del plan actualizados, sin borrar requisitos anteriores.

Pendiente explícito: permiso/cadencia aplicable y evidencia temporal real suficiente.
No se prometen identidades operativas verificadas. **Fases 2 y 3 requieren una
nueva autorización del usuario.**
