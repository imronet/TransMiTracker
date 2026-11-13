# Integración futura de proveedores y créditos — especificación, no cliente

Fase 3A entrega `SnapshotSource`, `OperationalIdentityVerifier` y
`CreditBudgetManager` como protocolos en `reconstruction/providers.py`.
**No hay cliente HTTP, facturación, scheduler ni llamadas Croma.** La Fase 3B
requiere autorización adicional.

## Adaptadores de datos

Un adaptador futuro debe producir `ProviderSnapshot` conservando fuente, endpoint,
hash de payload, catálogo fijado y tiempos de feed/GPS/recepción por separado.
Los valores ausentes permanecen ausentes. Debe indicar si el snapshot es completo;
solo la ausencia en snapshots completos puede ser evidencia de desaparición.
El lector Protobuf guardado de 3A acepta únicamente feeds completos.

Los campos animados/extrapolados son visuales. No entran como GPS observado;
`position_kind` permite rechazarlos explícitamente. El motor no obtiene posiciones
actuales ni crea posiciones animadas. El normalizador de una futura respuesta
Croma deberá verificar su semántica antes de convertirla, incluyendo unidades,
zonas horarias, identificadores y si se trata de posición observada o derivada.

El verificador de identidad requerirá evidencia independiente de instancia,
servicio, vehículo y patrón. La coincidencia de trip/ruta, un sufijo de ID,
proximidad o `start_time` aparentemente estable no bastan. 3A no implementa
atestación operativa real: los datos reales permanecen candidatos y sus
mediciones no se aceptan como históricas verificadas.

El consumidor futuro debe compartir adquisición/caché entre perfiles y vehículos,
manteniendo un único origen de snapshots por proveedor. Los perfiles estructurales
y sus ocurrencias se usan como filtros; abrir un perfil no inicia adquisición.
La agrupación visual por `parent_station` con andenes específicos queda como
mejora posterior, sin modificar el catálogo en 3A.

## Política de créditos

Valores de planificación **proporcionados por el usuario**, no verificados durante
3A: Free 1.500 créditos/mes; 10 por operación live y 1 por dataset. Son configurables
en `CreditPolicy`. Su reserva de seguridad se configura aparte y tiene valor
inicial 0, sin afirmar que esa sea una política apropiada de producción.

La clasificación de endpoints permanece **sin verificar**. No se deduce por su
URL, nombre o verbo HTTP. Antes de implementar 3B se comprobarán documentación,
plan y condiciones aplicables, cuotas, coste de fallos/reintentos y periodo de
renovación del proveedor. Ninguna cadencia se considera autorizada por el coste.

Flujo exigido para una implementación del gestor:

1. Clasificar la operación mediante una tabla de costes verificada y versionada.
   Clase desconocida o coste no acotado: bloquear antes de la solicitud.
2. Calcular fingerprint de proveedor, operación, parámetros y ventana de frescura,
   excluyendo credenciales. Consultar caché y solicitudes idénticas en curso.
3. Una respuesta reutilizable de caché no genera petición ni consumo nuevo. Su
   antigüedad debe seguir visible; caché no significa dato actual.
4. Bajo transacción/lock compartido, comprobar:
   `confirmado + reservas pendientes + máximo coste nuevo <= presupuesto mensual - reserva de seguridad`.
   Crear una sola reserva por fingerprint y compartir el resultado entre consumidores.
5. Solo tras autorización y reserva ejecutar el adaptador. No activar reintentos
   que el presupuesto o las condiciones del proveedor no permitan.
6. Registrar consumo estimado y confirmado separados, con periodo, clase y evidencia
   de cargo. Un fallo HTTP no demuestra que no se cobró: mantener pendiente hasta
   reconciliarlo. Liberar reservas solo cuando haya evidencia suficiente.
7. `dry-run` calcula la decisión sin HTTP, cargo confirmado ni reserva real.
   No puede activarse adquisición por un efecto lateral del diagnóstico.

La suma incluye solicitudes concurrentes; no basta comprobar un contador antes
de lanzar cada hilo. Persistir reservas y reconciliación permite recuperarse de
un cierre sin gastar dos veces. El rollover mensual debe seguir el periodo del
proveedor, sin asumir que usa America/Bogota. Las credenciales quedan fuera de
esa base, en el mecanismo local autorizado de configuración.

Pruebas necesarias en 3B: caché/duplicados sin cargos adicionales, carreras entre
reservas, límite mensual y reserva de seguridad, confirmación mayor/menor que
estimación, fallo con cargo desconocido, recuperación tras cierre, rollover,
clase desconocida bloqueada y dry-run sin red. Verificar también que no se
declaren verificadas identidades sin evidencia y que no se mezclen snapshots
parciales, datos visuales o catálogos distintos.

## Condiciones previas a Fase 3B

- Autorización explícita del usuario y revisión de las condiciones aplicables.
- Costes/clases y presupuesto confirmados para el plan real; acceso mínimo a claves.
- Serie real acotada permitida para estudiar IDs, `start_time`, frescura y geometría.
- Verdad de referencia independiente para validar eventos, errores e intervalos.
- Calibración de umbrales y política de identidad; datos ambiguos en cuarentena.
- Retención, volumen y concurrencia medidos, con adquisición compartida y deduplicación.

La aceptación sintética de 3A no satisface por sí sola estas condiciones.
