# Correspondencia GTFS y progresión geométrica — offline

**2026-11-13**, referencia `e6551a8108caf70abe746f72196601beb072de62`.
Solo el lote existente de 12 snapshots/24.104 observaciones y SQLite local.
**Cero red, nuevas capturas, cambios de motor o duraciones aceptadas.**

## Resultado ejecutivo

Los route_id coinciden, pero los descriptores de viaje/parada son mucho menos
compatibles. Las 2.107 cadenas exploratorias previas tienen un trazado candidato
por referencia de ruta; **esto no identifica su patrón de servicio**.
En una muestra dirigida de 40 cadenas, **33** progresan coherentemente sobre la
geometría: 23 tienen un solo patrón geométricamente candidato y 10 conservan
ambigüedad entre patrones. Solo **12 cadenas de la muestra** combinan referencias
exactas completas al catálogo y progresión coherente; tampoco verifican identidad
operativa. Es defendible continuar offline con correspondencia parcial y cuarentena
de conflictos, no tratar el feed entero como viajes GTFS identificados.

## Catálogo y reproducibilidad

`data/catalog/official_20261112.sqlite3`, esquema 1, abierto mediante `Catalog`
con SQLite `mode=ro`. Importado **2026-11-12 22:51:27 -05:00**, procedencia declarada
`https://gtfs.transmilenio.gov.co/GTFS.zip`; ZIP local de **180.271.992 bytes**.
Se comprobó el ZIP presente: SHA-256 coincide con la versión registrada:
`c66c7af657371eac892bab4b327e3a1e7be5d19ae0e9e5b4355e231261e3a09d`.
SHA-256 SQLite: `30502df8428df296b29aa1d1ffb3bbe6f79efe0b90d551812a89ad106c579c3c`.
feed_info declara versión «1», 2026-01-01–2026-12-31; eso no demuestra que fuera
la misma versión usada por el productor GPS el 13/11. No se descargó ni reemplazó nada.

Se reutilizaron `Catalog`, `active_services`, `TemporalAnalyzer.association`,
`decode_capture`, `distance_m`, `MeasuredShape` y `select_projection`.
Se verificaron hashes y redecodificaron PB. Se reprodujeron los 17.132 pares
exploratorios y las 2.107 cadenas de >=3 fixes del diagnóstico anterior, sin cambiar
la exclusión experimental de start_time ni trasladarla a reglas oficiales.

## 1. Datos observados y correspondencias exactas

Existencia de IDs: igualdad literal, sin sufijos, remapeos o unión por cercanía.
No hay valores ausentes en estos tres campos; «no coincide» significa publicado
pero inexistente en este catálogo. Sus restricciones de unicidad hacen inequívoca
la existencia individual; **no** la combinación ruta/viaje/parada.

| Campo | Apariciones coincidentes / 24.104 | Porcentaje | IDs distintos coincidentes / publicados |
| --- | ---: | ---: | ---: |
| route_id | 24.104 | 100 % | 559 / 559 |
| trip_id | 1.729 | 7,173 % | 165 / 2.258 |
| stop_id | 23.166 | 96,109 % | 1.589 / 1.651 |

Partición del análisis exacto de referencias:

| Resultado | Observaciones |
| --- | ---: |
| trip_id no existe | 22.375 |
| trip_id existe pero su ruta contradice route_id publicado | 1.463 |
| Viaje/ruta consistentes pero parada/secuencia incompatibles | 97 |
| Ruta, viaje, parada/secuencia y servicio activo consistentes | **169 (0,701 %)** |

Los 1.463 conflictos son el **84,615 % de los 1.729 trip_id coincidentes**.
Una coincidencia textual de viaje es insuficiente. Las 169 observaciones completas
corresponden a **13 rutas/14 patrones estáticos**; se desglosan por alias en el JSON.

Un contraste independiente, sin exigir trip_id, encuentra solo **5.445/24.104**
paradas incluidas en algún patrón de la ruta publicada. Para parada **y secuencia**:
860 observaciones encajan con un patrón de su ruta; 1.096, con varios; **22.148,
con ninguno**. Reconocer globalmente stop_id no demuestra que corresponda al
recorrido anunciado. No se corrigieron los datos para hacerlos encajar.

## 2. Cadenas con geometría disponible: universo completo

Una cadena es el segmento más largo del candidato con pares exploratorios válidos
y snapshots consecutivos; longitud >=2 pares. Se mantiene el universo previo de
**2.107**, no se forman cadenas operativas nuevas.

| Referencia disponible | Cadenas |
| --- | ---: |
| trip_id inexistente: solo ruta publicada | 1.959 |
| trip_id contradictorio: solo geometría de la ruta publicada, conflicto preservado | 126 |
| Viaje/ruta exactos con patrón asignado | 22 |
| Subconjunto con referencias completas exactas en todos sus fixes | 14 |

Las **2.107/2.107 (100 %)** tienen alguna geometría utilizable (>=2 puntos) entre
sus candidatos. En 1.160 hay un solo patrón candidato; en **947 hay varios**.
En este catálogo/cohorte esos candidatos comparten un único shape por cadena:
es un resultado inspeccionado, **no una regla de que cada ruta tiene una geometría**.
Se enumeraron todos los patrones; no se escogió el primero como sustituto del resto.

## 3. Muestra reproducible y criterios exploratorios

Se proyectaron **40 cadenas móviles**: mediana de distancia muestreada, los tres
extremos A/B/C previos, mínimo móvil, las 14 cadenas de referencias completas
y resto por ranking SHA-256 del namespace del candidato, sin exportar esos hashes.
La selección obligatoria tiene prioridad; se completa hasta 40 sin duplicados.
Se agregaron **tres controles separados**: estacionariedad, salto máximo y cambio
de ruta. Es muestra **dirigida**, sobrerrepresenta coincidencias exactas y extremos;
no permite estimar el porcentaje global de trayectorias coherentes.

Por viaje/ruta exactos se usa su patrón; en ausencia/conflicto de viaje se enumeran
los patrones de la ruta publicada, etiquetados como hipótesis. Formas compartidas
se proyectan una sola vez, preservando todos los patrones. No se buscan otras rutas
por cercanía. Rutas cambiantes no se enlazan sobre una misma geometría.

Proyección local y sobre segmentos existentes, **sin interpolar GPS**. Cada fix se
proyecta independientemente para hacer visibles retrocesos/saltos: no se pasa una
proyección previa que elimine silenciosamente ramas. Como current_status está ausente,
no se inventa un estado para resolver ocurrencias de parada.

Tolerancias copiadas de Parameters 3A: residual <=60 m; empate a 5 m del mejor;
ramas con separación longitudinal >30 m son ambiguas; retroceso tolerado 10 m;
salto longitudinal máximo 35 m/s × ΔGPS +8 m. Además se exige progreso neto >10 m
para separar movimiento del mismo margen exploratorio de ruido/retroceso.
El sentido medido es el orden longitudinal de los puntos del shape; no se inventa
un direction_id ni una asignación de sentido operacional cuando falta evidencia.
No son garantías de calidad operativa. Distancia al shape no es error GPS frente
a una verdad independiente. Una forma debe tener todos los fixes resolubles,
sin retrocesos >10 m ni saltos, para llamarla coherente en esta prueba.

## 4. Hipótesis geométricas y contraste por patrón

| Resultado sobre las 40 cadenas móviles | Cantidad |
| --- | ---: |
| Progresión coherente, único patrón geométricamente candidato | 23 |
| Progresión coherente, varios patrones indistinguibles por geometría | 10 |
| Proyección cercana sin progreso neto suficiente | 1 |
| No se resuelve un shape completo sin ambigüedad | 6 |

**33/40 (82,5 %) muestran progresión coherente en la muestra**, no en toda la flota.
Las seis fallas tienen ambigüedad de rama; no son seis cadenas alejadas del trazado.
Entre proyecciones resolubles no se observaron retrocesos >10 m; una cadena ambigua
también muestra un salto longitudinal de ~24,8 km y sigue rechazada. Las partes
ambiguas no permiten afirmar sentido ni ausencia de retrocesos.

Contrastar paradas/secuencias y servicio activo en las fechas publicadas reduce
las 33 cadenas geométricamente coherentes a **14 con algún patrón también compatible
en todos sus fixes**: 12 son las de referencias completas exactas y **dos siguen
con varios patrones candidatos**. No se fuerza una selección para estas últimas.
Las otras 19 muestran que verse cerca del trazado no resuelve metadatos incompatibles.

En las 12 cadenas de referencias completas y geometría coherente aparecen estos
alias (son etiquetas del estudio, no IDs publicados):

| Ruta alias | Patrón alias | Cadenas de la muestra |
| --- | --- | ---: |
| R024 | P0141 | 1 |
| R059 | P0775 | 1 |
| R055 | P0283 | 1 |
| R047 | P1168 | 1 |
| R027 | P1081 | 2 |
| R132 | P0394 | 1 |
| R079 | P0538 | 1 |
| R013 | P0642 | 1 |
| R078 | P1370 | 1 |
| R123 | P0706 y P0974 | 2 |

La tabla identifica casos estáticos defendibles en esta muestra, no habilita
generalizar por ruta. Los alias se resuelven **solo localmente** en el mapa privado.
El JSON no identificable incluye todos los 43 casos y resultados por patrón/ruta.

Cambios de patrón: en **240 pares** con viaje/ruta exactos en ambos extremos se
observan cero cambios de patrón estático. En los **21.606 restantes** no se puede
medir ese cambio sin forzar asociación. No equivale a demostrar patrón constante
en el servicio real; la ambigüedad entre variantes permanece.

### Cadena mediana frente a extremos y controles

| Caso | Distancia GPS muestreada | Residual mediano / máximo | Progreso neto | Interpretación |
| --- | ---: | ---: | ---: | --- |
| S01, mediana de las 2.107 cadenas | 1.324 m | 2,47 / 7,01 m | 1.430 m | Coherente con un shape, dos patrones; sin viaje exacto ni patrón compatible con todas las paradas publicadas |
| S02, extremo A previo | 4.535 m | 3,76 / 7,45 m | 4.536 m | Tres patrones geométricos; dos además compatibles con paradas/servicio; ambigüedad persiste |
| S03, extremo B | 4.461 m | 3,94 / 4,98 m | 4.462 m | Patrón geométrico único, pero sin viaje exacto y con metadatos de parada incompatibles |
| S04, extremo C | 4.012 m | 0,46 / 3,78 m | 4.025 m | Dos patrones geométricos; no identidad de servicio resuelta |
| S05, mínimo móvil | ~2 m | 0,46 / 1,30 m | 0,07 m | Variación pequeña compatible con ruido/estancamiento; no progreso suficiente |
| S41, control estacionario | 0 m | 1,06 / 1,06 m | No determinable | Ramas longitudinales ambiguas incluso con residual pequeño |
| S42, salto anómalo | ~792 km | Máximo ~789 km | No determinable | Un punto fuera de la geometría; descartado |
| S43, cambio de ruta | ~169 m | No enlazado | No determinable | No se compara progreso entre dos rutas diferentes |

Las sumas de distancias entre GPS y el progreso sobre una polilínea curva son
magnitudes distintas; una diferencia no calibra precisión. Ninguna celda expresa
duración, llegada o embarque. La mediana es ordinal por distancia de cadena,
no una afirmación de representatividad estadística de todos los buses.

## 5. Incertidumbres y recomendaciones concretas

- **Observado:** hay posiciones que avanzan sobre trazados publicados, y también
  estancamiento, ramas ambiguas, saltos e incompatibilidades de metadatos.
- **Verificado contra catálogo:** existencia de IDs y, en el subconjunto indicado,
  referencias ruta/viaje/parada/secuencia/servicio y patrón estático asignado.
- **Hipótesis:** shape cercano y progreso positivo como evidencia de recorrido
  candidato, particularmente cuando falta trip_id o contradice la ruta. No es
  prueba de vehículo, instancia o patrón de paradas concreto.
- **No resuelto:** catálogo que usa el productor, semántica real de sus IDs/inicio,
  posibles reasignaciones, variantes que comparten shape y falta de referencia externa.

Siguiente paso propuesto, no implementado: separar resultados por nivel de evidencia;
examinar primero los 12 casos con referencias completas/progreso, y las variantes
ambiguas de la mediana y extremos. Mantener en cuarentena viaje/ruta o parada
incompatibles. Investigar versiones/contratos del productor antes de remapear IDs.
Evaluar resolución de bucles con supuestos explícitos en otra tarea; no elegir
ramas para mejorar cifras ni inferir duraciones. No hace falta nueva adquisición
para profundizar en estas discrepancias del lote ya guardado.

## Evidencia de reproducción y cierre

[Agregados no identificables](../archive/evidence/GPS_GEOMETRY_OFFLINE_20261113.json)
y [comprobaciones](../archive/evidence/GPS_GEOMETRY_OFFLINE_CHECKS_20261113.json).
28 entradas protegidas (incluido SQLite, originales y diagnósticos previos) conservan
hashes. Dos ejecuciones conservaron las mismas proyecciones/categorías en los 43
casos; la segunda añadió contraste de paradas/servicios sin alterar la primera salida.
No se repitieron suites de aplicación: no se modificó código funcional.

Receta local aislada:
`data/pilots/first-real-20261113-223641-1613d2b6/geometry_offline_20261113.py`,
SHA-256 `915abbbe5d82c6e5a21c7ad8958d0c25f9977a2a42b940cade5b021fd1193033`.
Resultados privados v1/v2 y `geometry-private-map-v2-20261113.json` están en ese
directorio excluido de Git; el mapa contiene los IDs estáticos para revisión del
propietario, no se comparte. Para reproducir hace falta el lote privado; usar
destinos nuevos, pues los archivos se crean exclusivamente y no se sobrescriben.
La receta bloquea sockets/HTTP y solo abre el catálogo en lectura.

Diagnóstico completado. **Ninguna trayectoria operativa verificada**, ninguna
duración aceptada, captura nueva, dependencia, commit o push. Toda mejora de
analizador o adquisición posterior requiere otro encargo autorizado.
