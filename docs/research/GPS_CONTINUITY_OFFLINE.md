# Continuidad GPS real — diagnóstico offline

**2026-11-13**, referencia **ffd25ea752fe3ce7540a3eaa117b00222813a046**, producto
0.2.0. Solo los 12 snapshots de la primera sesión: **cero solicitudes de red**.
No se modificaron reglas del analizador, motor 3A, catálogo ni GUI. La alternativa
se calculó en memoria; no sustituyó el diagnóstico conservador guardado.

## Conclusión

El rechazo total se explica por la combinación de dos controles: cada uno de los
**17.340 pares con tiempo GPS creciente cambia start_time**; los **4.506 pares
restantes repiten timestamp y posición**. Ninguno puede mantener el descriptor
completo y avanzar temporalmente en esta muestra.

Ignorar exclusivamente start_time deja **17.132 pares (78,422 % de 21.846)** que
superarían los demás controles, relacionados con **2.164 IDs candidatos**.
**2.107 IDs** tienen alguna cadena de al menos tres fixes en snapshots consecutivos
superando esos controles exploratorios. Hay material para estudiar continuidad
temporal/espacial, pero no identidad operativa demostrada. Conviene mejorar el
diagnóstico experimental en una tarea posterior, antes de investigar otra fuente.

## Método y descriptor actual

Se inspeccionó research/local_pilot.py y se redecodificaron los Protobuf originales
con hash verificado. Se reprodujeron los **21.846 pares y cero candidatos** del
criterio oficial. Los hashes de 26 entradas (12 PB, 12 registros, session.json y
diagnóstico original) permanecen iguales antes/después. No se usó el catálogo.

El agrupamiento es `(source, vehicle_id)`. Se excluyen IDs ausentes/duplicados en
el snapshot o timestamps ausentes. El descriptor compara igualdad de
`trip_id, route_id, start_date, start_time`. Se conserva el último registro por ID,
incluso si estuvo ausente en snapshots intermedios; no se exige presencia consecutiva.
Luego requiere ΔGPS>0, coordenadas disponibles, distancia>0, velocidad media<=35 m/s,
edad **del extremo actual** en [0,300] s y ΔGPS<=300 s. No verifica geometría,
monotonía sobre patrón, fecha de servicio efectiva ni instancia operativa.

El motivo publicado tiene prioridad: descriptor_change tapa posibles defectos
posteriores; observed_pair no significa aceptación y en este lote corresponde a
4.506 pares de tiempo repetido. Se auditaron además los predicados independientes.
La alternativa conserva exactamente esos controles y orden, salvo excluir
start_time de la igualdad del descriptor. No se elimina, corrige ni reescribe el
campo original. No se descartan duplicados para fabricar una cadena más larga.

## Semántica observada frente a hipótesis

| Evidencia del lote | Resultado |
| --- | ---: |
| start_time = HH:MM:SS del timestamp GPS en America/Bogota | 24.104 / 24.104 observaciones |
| Cambia solo start_time | 17.280 pares |
| Cambian route_id y start_time | 60 pares |
| Descriptor sin cambios | 4.506 pares |
| Cambios de trip_id / start_date en pares del mismo ID | 0 / 0 |
| Cambios de start_time sin cambio de timestamp GPS | 0 |
| Tiempo GPS creciente sin cambio de start_time | 0 |

En esta ventana, start_time actúa **observacionalmente** como una copia del reloj
GPS, en lugar de un ancla constante del comienzo de viaje. Que el productor lo
rellene así es una hipótesis compatible con el resultado, no su contrato confirmado.
No demuestra que el campo pueda ignorarse siempre, que nunca identifique instancias
o que debamos normalizar todos los feeds de la misma manera.
trip_id permanece igual en los pares de un mismo vehicle_id, incluso en 60 cambios
de route_id; no prueba equivalencia con el GTFS ni que se mantenga el mismo viaje.
vehicle_id repetido permite agrupar candidatos, no verificar vehículo físico o
ausencia de reciclaje del ID. No se inventó correspondencia entre identificadores.

## Comparación de filtros acumulados

El orden es explícito: cada fila usa los supervivientes de la anterior.

| Control | Conservador | Exploratorio sin start_time |
| --- | ---: | ---: |
| Pares comparables | 21.846 | 21.846 |
| Descriptor estable (4 campos / 3 campos) | 4.506 | 21.786 |
| Tiempo GPS creciente | 0 | 17.280 |
| Coordenadas disponibles | 0 | 17.280 |
| Distancia positiva | 0 | 17.179 |
| Velocidad media <=35 m/s | 0 | 17.178 |
| Edad actual en [0,300] s | 0 | 17.178 |
| Hueco <=300 s | **0** | **17.132** |

Partición de descartes exploratorios, en ese orden: **60** por ruta distinta,
**4.506** por tiempo repetido, **101** sin movimiento con tiempo nuevo,
**1** por velocidad y **46** por hueco. No son aceptaciones guardadas ni tiempos
de viaje: solo pares que pasarían una comparación alternativa en memoria.

### Anomalías independientes (se solapan)

| Predicado sobre todos los pares | Cantidad |
| --- | ---: |
| Posición cambia | 17.239 |
| Timestamp repetido / regresión GPS | 4.506 / 0 |
| Mismo timestamp con posición diferente | 0 |
| Tiempo nuevo y posición estacionaria | 101 |
| Coordenadas ausentes | 0 |
| Velocidad >35 m/s | 1 |
| Hueco GPS >300 s | 57 |
| Edad actual >300 s / futura | 449 / 0 |
| Pares que saltan algún snapshot sin el candidato | 124 |

Los **449** son extremos de pares; no contradicen las 490 observaciones antiguas
del informe de captura, que usa otro denominador. El filtro de edad no elimina
pares adicionales después de los controles anteriores, pero no deja de existir
el problema de obsolescencia en el lote. De los 57 huecos, solo 46 llegan al último
filtro tras los anteriores. Coordenadas decodificables no garantizan posición válida
sobre una ruta: el único salto excede ampliamente 35 m/s (máximo observado ~7.918 m/s).
En tiempos positivos: mínimo 20 s, mediana 60 s, máximo 1.083 s. La mediana de
velocidad media es ~4,305 m/s, incluyendo estacionariedad; no es precisión validada.

## Ejemplos sin coordenadas ni identificadores

Etiquetas A/B/C creadas solo para la exposición; no contienen hashes de IDs ni
una tabla de correspondencia persistida. Se eligieron deliberadamente cadenas
con mayor distancia muestreada: **ilustran movimiento, no una muestra representativa
de la flota**. Cada una tiene cinco fixes de snapshots consecutivos, cuatro cambios
de start_time y trip_id/route_id/start_date constantes. Distancias redondeadas a 10 m.

| Ejemplo | Intervalos GPS entre fixes (s) | Desplazamientos (m) | Velocidades medias (m/s) |
| --- | --- | --- | --- |
| A | 102, 60, 40, 120 | 1.370, 790, 670, 1.690 | 13,5; 13,2; 16,8; 14,1 |
| B | 98, 60, 40, 120 | 1.020, 920, 620, 1.900 | 10,4; 15,3; 15,4; 15,9 |
| C | 100, 60, 60, 92 | 1.130, 910, 870, 1.100 | 11,3; 15,1; 14,6; 12,0 |

Las edades de sus extremos actuales están aproximadamente entre 40 y 100 s.
Todos esos pares fallan conservadoramente por start_time. Los intervalos son
separaciones entre muestras GPS, **no duraciones entre paraderos**.
Como contraste, 4.506 pares mantienen tiempo/posición y no demuestran movimiento;
el salto de velocidad y los cambios de ruta continúan excluidos en la alternativa.

Las cadenas de pares consecutivos exploratorios tienen mediana y máximo de cuatro
pares (cinco fixes). Un timestamp repetido rompe esa cadena estricta aunque sea
compatible con la continuidad física; no se borró para mejorar cifras. El resultado
de 17.132 pares incluye comparaciones no necesariamente adyacentes del analizador;
el resultado de 2.107 cadenas exige además snapshots consecutivos y >=3 fixes.

## Garantías debilitadas y siguiente paso

Omitir start_time pierde una distinción potencial entre instancias de servicio;
podría unir una reasignación, vuelta de bucle o ID reciclado que conserve otros
campos. Los predicados restantes son coherencia básica, no prueba de identidad,
servicio activo ni seguimiento del patrón. La edad previa tampoco se valida
independientemente en el criterio actual. No se alteró para esta comparación.

Recomendación futura, **no implementada**: diagnóstico exploratorio separado,
etiquetado y opt-in que muestre motivos múltiples y estabilidad de descriptores;
conservar siempre start_time publicado y el diagnóstico conservador. Caracterizar
reasignaciones, huecos y progresión geométrica sobre este mismo lote antes de
proponer un verificador. No pasar esa exclusión al motor 3A ni a mediciones de
duración. Otra fuente no es necesaria para investigar este bloqueo concreto;
podría aportar referencia independiente en otra tarea, no en este encargo.

## Evidencia y QA

[Agregados y ejemplos](../archive/evidence/GPS_CONTINUITY_OFFLINE_20261113.json);
[pruebas focalizadas](../archive/evidence/GPS_CONTINUITY_QA_20261113.json).
Se fortaleció el test de salida usando cuatro snapshots sintéticos válidos en
vez de una entrada inexistente: fallaría si se quitara la restricción del destino.
**3 casos aprobados en 0,28 s**, Ruff y formato del test correctos. No suite completa.
INDEX refleja ahora cierre de captura y autorización consumida.

El programa de aplicación no tiene diff. El cálculo puntual privado está en
`data/pilots/first-real-20261113-223641-1613d2b6/continuity_offline_20261113.py`,
SHA-256 `ea1a603fcac90798585e7343b81eebe6c4324a7caf21d40d223145a40c37a13a`;
guarda únicamente agregados en `continuity-offline-20261113.json`. Sus conexiones
socket/HTTP están bloqueadas por aserción durante el análisis. No escribió el
diagnóstico original, payloads ni resultados de aceptación por par.
Para reproducirlo se necesitan los datos privados locales, no disponibles en Git;
la salida exclusiva no sobrescribe una ejecución anterior. Ningún ID operativo,
coordenada o payload real forma parte de estas evidencias compartibles.

**Cierre:** diagnóstico completado. No hubo capturas, solicitudes de red,
duraciones aceptadas, cambios en las garantías oficiales, commits ni push.
Cualquier mejora del analizador o nueva captura requiere otro encargo autorizado.
