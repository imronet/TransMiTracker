# Piloto GPS local — preparación 3B-P0

Herramienta manual aislada en `transmitracker.research.local_pilot`. El propietario
autorizó implementación y pruebas offline, **no capturas reales**. La captura
permanece bloqueada por revisión de condiciones; no hay opción CLI para saltarla.

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

Después de resolver la revisión pública de sondeo/retención y de una autorización
posterior para ejecutar, deberá actualizarse el gate NETWORK_ALLOWED con evidencia
documentada en una tarea explícita. La confirmación por sí sola no lo activa.
No se requiere certificar duraciones o resolver identidad operacional para preparar
este diagnóstico doméstico: precisamente se investigarán esas limitaciones.

El comando preparado para esa futura revisión es:

```powershell
# NO ejecutado en 3B-P0. Actualmente falla antes de crear cliente o hacer red.
.\.venv\Scripts\python.exe -m transmitracker.research.local_pilot capture --confirm-real-capture --count 12 --interval 60 --directory data/pilots/real-NUEVA-SESION
```

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
