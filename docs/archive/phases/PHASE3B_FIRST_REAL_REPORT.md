# 3B — Primera sesión GPS real doméstica controlada

Fecha local **2026-11-13, America/Bogota**; producto de referencia 0.2.0.
El propietario autorizó **exactamente una sesión**, tras corregir dos observaciones
QA. No autoriza una segunda sesión ni operación continua. Este informe incluye
solo agregados; payloads y diagnósticos identificables permanecen privados.

## Alcance y decisión experimental

Se actualizó [LOCAL_PILOT_CONDITIONS.json](../../research/LOCAL_PILOT_CONDITIONS.json)
separando operator_decision de license_evidence. La decisión autoriza una prueba
personal, acotada, temporal y sin redistribución, aceptando la incertidumbre
documentada. No declara verificación jurídica ni autorización individual de TMSA.
El valor allowed_private_temporary permite usar el mecanismo existente, como
decisión del operador; no demuestra una licencia específica del feed Realtime.

Hay [publicación oficial de apertura GTFS-RT](https://www.transmilenio.gov.co/comunicaciones/noticias-de-transmilenio/especiales-transmilenio/datos-abiertos-tiempo-real-transmilenio-conecta-operacion-sistema-tecnologia-ciudad)
y una referencia pública a CC BY-SA 4.0 en el conjunto GTFS de Datos Abiertos
Bogotá, preservada en la evidencia de investigación del mismo día. La página del
catálogo agotó el tiempo de consulta del navegador en esta tarea: no se presenta
como nueva lectura exitosa. La [licencia](https://creativecommons.org/licenses/by-sa/4.0/)
fue consultada, pero su aplicación exacta al feed Realtime no está confirmada.
La [revisión anterior](../evidence/FIRST_REAL_CONDITIONS_BEFORE_20261113.json)
se preservó antes de actualizar la decisión. No se contactaron proveedores.

## QA previo

- Salidas completas de analyze: `pilot_path(project_path(...))` restringe destino
  resuelto a data/pilots **antes** de leer capturas. Evita docs/, rutas exteriores
  y escapes con ..; continúa rechazando sobrescrituras.
- Pruebas de permiso: no adulteran expires_at para simular vencimiento; avanzan
  un reloj simulado con permiso original a 899 s (aceptado), 900 y 901 s (rechazado).
  Revisión de más de siete días se rechaza al emitir y al consumir permiso.

**38 pruebas focalizadas aprobadas en 1,24 s**; lint de los dos archivos correcto.
Evidencia: [FIRST_REAL_QA_20261113.json](../evidence/FIRST_REAL_QA_20261113.json).
No se repitió suite completa. El motor 3A y sus reglas permanecen intactos.

## Controles de ejecución y privacidad

Permiso con ventana de inicio de 15 minutos, ligado al directorio exacto, marcador
.used exclusivo antes de red y ambas confirmaciones existentes. Máximo 12 GET de
posiciones, mínimo 60 s entre inicios y un GET de manifiesto. Sin reintentos,
paralelismo, scheduler, Croma, fallback o compensación de fallos.

Directorio privado nuevo bajo data/pilots, con herencia ACL desactivada y acceso
para propietario, cuenta local de ejecución aislada y SYSTEM; sin grupos públicos.
Git excluye captura, permiso, marcadores y diagnóstico. No se enviaron ni publicaron
payloads, placas, IDs operativos ni coordenadas. No hubo commits ni push.

Un fallo local inicial al emitir permiso ocurrió antes de toda consulta: la ACL
incluía la cuenta sandbox pero omitía la cuenta propietaria que ejecuta Python.
Se corrigió el acceso local, comprobando que no había permiso ni sesión creados.
No fue una captura fallida ni un reintento de descarga; queda registrado en privado.

## Resultados de la única sesión

Inicio: **2026-11-13 22:38:52,075 Bogotá** (2026-11-14 03:38:52,075 UTC).
Finalización: **22:49:54,820 Bogotá** (03:49:54,820 UTC). Unos 11 min 2,74 s.
Salida del proceso 0; causa **limit_reached**, no error ni cancelación.

| Magnitud | Resultado real |
| --- | ---: |
| GET de manifiesto | 1, HTTP 200 |
| GET de posiciones | 12, todos HTTP 200 |
| Snapshots guardados / decodificables | 12 / 12 |
| Observaciones totales | 24.104 |
| Intervalo mínimo/máximo de inicio registrado | 60,000111 / 60,000573 s |
| Novedades GPS después del primer snapshot | 17.495 |
| Repeticiones de timestamp GPS por ID candidato | 4.506 |
| Duplicados respecto al total de observaciones | 18,694 % (4.506 / 24.104) |
| Duplicados tras la línea base | 20,481 % (4.506 / 22.001) |
| Payloads completos distintos | 11 de 12; una repetición byte a byte |
| IDs candidatos que reaparecen | 2.206 |
| IDs candidatos en >=3 instantes GPS distintos | 2.122 |
| Pares comparados / con cambio de posición | 21.846 / 17.239 |
| Intervalo GPS entre pares: mínimo / mediana / máximo | 0 / 60 / 1.083 s |
| Pares con cambio de descriptor | 17.340 |
| Desplazamientos plausibles según todos los controles actuales | 0 |

Novedades por snapshot (el primero es línea base):
`2103, 2024, 1993, 0, 1978, 1959, 1945, 1928, 0, 1913, 1889, 1866`.
Los snapshots 4 y 9 no aportaron tiempo GPS nuevo; no fueron tres consecutivos,
por lo que no correspondía activar esa parada. Un header renovado no garantiza
novedad de los timestamps por vehículo.

### Frescura y campos

| Categoría respecto a recepción | Observaciones | Porcentaje |
| --- | ---: | ---: |
| Reciente, <120 s | 20.465 | 84,903 % |
| Retrasado, 120–300 s inclusive | 3.149 | 13,064 % |
| Antiguo, >300 s | 490 | 2,033 % |

Edades mínima/mediana/máxima: **32,751 / 86,742 / 6.184.795,689 s**.
El máximo equivale a unos **71,58 días**. El rango de timestamps GPS del lote
va de 2026-09-03 13:49:59 UTC a 2026-11-14 03:48:49 UTC. No se observan edades
futuras ni GPS timestamps ausentes en esta muestra. No todo el feed es reciente
aunque responda 200 o cambie su header.

Publicado en las 24.104 observaciones: vehicle_id, trip_id, route_id, start_date,
start_time, stop_id, current_stop_sequence, latitud, longitud y timestamp GPS.
**current_status ausente en todas**; no se usó su enum predeterminado como evidencia.
Presencia no significa validez operativa ni correspondencia con el catálogo.
El parser aceptó las coordenadas de los 12 snapshots; no es una validación de
pertenencia a trazado, cobertura completa de flota o precisión geográfica.

### Continuidad candidata: hay material, no asociación demostrada

Sí existe material real para **estudiar** continuidad candidata offline: IDs
recurrentes, timestamps que avanzan y coordenadas que cambian. Sin embargo, el
diagnóstico conservador no clasifica ningún par como desplazamiento plausible
tras todos sus controles, debido a cambios de descriptor y timestamps repetidos.
No hay trayectorias operativas verificadas ni duraciones aceptadas.

El desglose offline de las mismas capturas cuenta **17.340 cambios de start_time**
y **60 de route_id**; los conjuntos pueden solaparse. No se detectaron cambios
de trip_id/start_date en los pares inspeccionados. En **24.104/24.104** observaciones,
start_time coincide con la hora HH:MM:SS del timestamp GPS en Bogotá. Es evidencia
de asociación temporal en esta muestra, **no demostración de la semántica del campo**
ni autorización para quitarlo de la identidad o forzar emparejamientos.

Evidencia sin IDs ni coordenadas: [agregados](../evidence/FIRST_REAL_AGGREGATES_20261113.json).
Los PB se analizaron offline con verificación SHA-256 y el analizador existente;
el desglose posterior solo leyó archivos locales ya conservados. No hizo nuevas
solicitudes. El registro completo permanece en el directorio privado.

## Interpretación y límites

El primer snapshot es una línea base, no novedad respecto a una captura anterior
inexistente. Repeticiones de timestamp no equivalen necesariamente a duplicados
de payload completo; ambas métricas se deben distinguir y explicitar denominadores.
Edades se comparan con recepción UTC, no con fecha de importación del catálogo.
La continuidad candidata requiere estudiar progreso temporal y espacial; compartir
ID no verifica instancia operativa. No se infieren llegadas, embarques, espera o
duraciones reales ni se aplican reglas sintéticas para autorizar datos reales.

Datos originales y derivados identificables: revisar dentro de siete días y
decidir su eliminación después de la revisión del propietario; no hay borrado
automático. Un resumen sin identificadores puede conservarse para auditoría.
La incertidumbre de licencia no desaparece por la decisión experimental.

## Rutas locales y siguiente decisión

Control privado: `data/pilots/first-real-20261113-223641-1613d2b6/`.
Capturas y metadatos: subdirectorio `session/`; permiso `permit.json` y
`permit.json.used`; decisión congelada `operator-review.json`; ejecución
`execution.json`; diagnóstico completo `diagnostic.json`; agregados
`safe-summary.json` y su ampliación `safe-summary-v2.json`. El localizador `data/pilots/FIRST_REAL_20261113_LOCATOR.json`
no está versionado. Las rutas son locales y no estarán disponibles en un checkout.

**No iniciar una segunda captura sin nueva autorización.** La revisión vigente
se marcó consumed_single_session / execution_authorized=false; el permiso original
permanece consumido y su revisión congelada se conserva en privado. No se emitió
otro permiso tras el fin de la sesión.

Recomendación: continuar **solo offline** con este lote para caracterizar cambios
de start_time, timestamps repetidos y cobertura de los IDs/rutas publicados. No
modificar las garantías 3A para conseguir asociaciones positivas. Ya se obtuvo
evidencia real de disponibilidad y novedades GPS; todavía no de identidad operativa,
llegadas o tiempos de viaje. El siguiente paso no necesita descargar otra muestra.
