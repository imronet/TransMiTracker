# Piloto GPS local — preparación 3B-P2

Herramienta manual aislada en `transmitracker.research.local_pilot`. Se completó
una [primera sesión real autorizada](../archive/phases/PHASE3B_FIRST_REAL_REPORT.md).
Su permiso quedó consumido. **No hay autorización para una segunda sesión.**
Por defecto no hay red; toda nueva captura requiere otra decisión y permiso.

Desde la raíz del proyecto en PowerShell, con el entorno ya instalado:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
# Sin argumentos: muestra el plan, sin red ni creación de sesión.
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot
# Ejemplo totalmente sintético. Use un nombre nuevo en cada ejecución.
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot fixture --directory data/pilots/ejemplo-NUEVO
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot analyze data/pilots/ejemplo-NUEVO --output data/pilots/diagnostico-NUEVO.json
```

`fixture` crea cuatro Protobuf y sus registros JSON con origen synthetic_fixture,
IDs DEMO y reloj fijo en 2027: no representa la fecha actual ni buses observados.
Los archivos/directorios nuevos se abren exclusivamente; no se sobrescriben sesiones
o diagnósticos. `data/` está excluido de Git. No publique payloads reales ni placas.

## Analizar una captura guardada

El analizador solo lee archivos locales y comprueba SHA-256 antes de decodificar
otra vez el PB. No confía en la lista de vehículos almacenada en el JSON. No necesita
catálogo ni modifica SQLite. `--route ID` puede repetirse hasta dos veces: compara
route_id **publicado exactamente**, no número comercial ni sufijo de trip_id.
Sin correspondencia fiable con GTFS, no la inventa; lo indica en route_scope.

```powershell
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot analyze data/pilots/ejemplo-NUEVO --route DEMO_ROUTE --recent 120 --delayed 300 --output data/pilots/filtrado-NUEVO.json
```

Reciente: edad GPS frente a recepción <120 s; retrasado: 120–300 inclusive;
antiguo: >300; futuro o ausente se informa aparte. Son categorías exploratorias,
no garantías. La recepción UTC no reemplaza el tiempo del vehículo ni el del feed.

Incluye presencia/ausencia de campos, edades individuales, timestamps repetidos,
novedades por snapshot, candidatos que reaparecen, tres instantes GPS distintos,
intervalos, distancia/velocidad media y motivos de discontinuidad. Protobuf no
tiene null explícito: los ausentes se mantienen como null al serializar y se
cuentan como ausencia, no como valor publicado. No se asume estado enum por defecto.

Las coordenadas inválidas causan rechazo conservador del snapshot por el lector
existente, preservando el original. El diagnóstico informa no determinable y no
intenta reparar coordenadas. Una velocidad >35 m/s, retroceso de reloj, cambio de
descriptor o hueco >300 s impide calificar ese par como desplazamiento plausible.
El umbral de velocidad es exploratorio, no una regla calibrada para Bogotá.
Tres timestamps de un ID tampoco demuestran identidad operativa.

## Una sesión real futura, todavía bloqueada

El bloqueo global de código de P0 se sustituyó por permiso local de un solo uso.
La revisión [LOCAL_PILOT_CONDITIONS.json](../research/LOCAL_PILOT_CONDITIONS.json)
dice consumed_single_session: el comando de emisión falla sin hacer red. La primera
decisión experimental del propietario aceptó expresamente la incertidumbre de
licencia; no se afirmó una autorización individual de TMSA. No cambie esa decisión
para repetir la sesión sin nueva autorización del propietario.
No se exige automáticamente un convenio; consulte el [informe P2](../archive/phases/PHASE3B_P2_REPORT.md).

Solo con nueva revisión/decisión y autorización expresa del propietario, los
comandos de referencia para otra sesión serían (no ejecutarlos para repetir):

```powershell
# Emisión offline, confirmación del operador y sesión nueva exacta.
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot permit --review docs/research/LOCAL_PILOT_CONDITIONS.json --directory data/pilots/real-SESION-001 --output data/pilots/permiso-SESION-001.json --confirm-one-session
# Iniciar dentro de 15 minutos; sigue necesitando confirmación explícita.
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot capture --permit data/pilots/permiso-SESION-001.json --confirm-real-capture --count 12 --interval 60 --directory data/pilots/real-SESION-001
# Después, offline, con salida nueva y privada:
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot analyze data/pilots/real-SESION-001 --output data/pilots/diagnostico-SESION-001.json
```

El permiso vincula endpoint, revisión y directorio nuevo, vence para iniciar a los
15 minutos y se consume mediante archivo exclusivo .json.used antes de red. La
revisión debe tener menos de siete días, evidencia/justificación, ámbito exacto y
decisión allowed_private_temporary. Es constancia local del operador, no licencia
remota ni prueba jurídica por sí misma. No hay activación global/permanente.

Ctrl+C detiene y registra operator_interrupted; no recupera el permiso ni permite
reanudar. Tras error o cancelación, revisar archivos completos offline. Nunca borrar
el marcador para repetir; otra sesión necesitaría nueva autorización y directorio.
Revisar dentro de siete días; eliminar originales/derivados identificables solo
tras revisión del propietario, sin borrado automático. Proteger el directorio de
acceso público: estar excluido de Git no implica cifrado ni permisos privados.

Una sesión por proceso, secuencial: primero un GET del manifiesto oficial, luego
hasta 12 GET de posiciones, separados al menos 60 s entre inicios. Una consulta
de manifiesto es menor que el máximo solicitado de dos. Si no anuncia exactamente
el endpoint revisado, o indica indisponibilidad, se detiene. No cambia a otro host.
Sin reintentos, redirects, credenciales, Croma, scheduler ni sondeo permanente.
Detiene cualquier fallo HTTP/transporte/decodificación (más estricto que esperar
errores persistentes), el máximo o tres snapshots consecutivos sin GPS relevante
nuevo. El filtro de rutas solo afecta novedad/análisis; se descarga el feed completo.

Los límites de descarga son 64 KiB para manifiesto y 8 MiB para posiciones; se
reutiliza el timeout HTTP existente (lectura 20 s, conexión 10 s), presupuesto
entre chunks 15 s. No es un deadline duro de 15 s: una lectura en curso puede
consumir además su timeout. No se intenta eludir mantenimiento, 403 o 429.

Detalles de validación y condiciones: [informe 3B-P0](../archive/phases/PHASE3B_P0_REPORT.md).
Los informes completos de `analyze --output` solo pueden escribirse dentro de
data/pilots, también cuando los datos son sintéticos. No dirigirlos a docs/.
