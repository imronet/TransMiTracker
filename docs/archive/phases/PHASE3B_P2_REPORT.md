# 3B-P2 — Primera sesión doméstica: preparación temporal

**2026-11-13, America/Bogota; producto de referencia 0.2.0.** Alcance autorizado:
preparación y pruebas offline. **Ninguna descarga de posiciones reales ni permiso
operativo emitido.** Recomendación de ejecución: **CONDICIONAL**, bloqueada hoy.

## Resultado y cambios

El bloqueo global NETWORK_ALLOWED=False inspeccionado en P0/P1 se sustituyó por
permiso local explícito, temporal y ligado a una sesión. No se habilita una opción
global en código ni se cambia una variable de entorno para activar la red.
Se mantienen los límites, el downloader y el analizador P0. No se modifica 3A,
GUI, perfiles, catálogo, bases ni dependencias. No se publica una nueva release.

| Archivo | Cambio |
| --- | --- |
| src/transmitracker/research/local_pilot.py | Emisión offline, validación y consumo exclusivo de permiso; parada Ctrl+C registrada |
| tests/test_local_pilot.py | Adaptación de los 22 casos P0 al permiso, nueve casos nuevos |
| docs/research/LOCAL_PILOT_CONDITIONS.json | Revisión pública pendiente, pregunta precisa y retención propuesta; no autoriza ejecución |
| docs/getting-started/LOCAL_GPS_PILOT.md | Procedimiento vigente de permiso/captura y recuperación |
| README, INDEX, IMPLEMENTATION_PLAN | Estado P2 y enlaces, sin reescribir informes históricos |
| Este informe y evidencia P2 | Decisión, resultados y límites de verificación |

## Mecanismo de una sola sesión

1. Por defecto, solo plan offline; capture sin permiso o sin confirmación falla
   antes de crear cliente o directorio. No hay adquisición al abrir perfiles.
2. `permit` es un comando offline. Exige --confirm-one-session y revisión con
   decisión allowed_private_temporary, ámbito exacto, evidencia, justificación y
   fecha consciente de zona de no más de siete días. La revisión distribuida
   dice unresolved: falla y no crea un permiso.
3. Cuando exista una decisión fundamentada y autorización posterior del propietario,
   el permiso se escribe en archivo nuevo bajo data/pilots, fuera del directorio
   de captura. Lleva endpoint/manifiesto fijos, directorio nuevo exacto, ID,
   revisión y ventana de **15 minutos para iniciar**; no se renueva automáticamente.
4. `capture --permit ... --confirm-real-capture` vuelve a validar revisión,
   plazo y ámbito. Crea exclusivamente `.json.used` antes de hacer red. El marcador
   conserva ID, hora y hash del permiso; evita reutilizarlo entre procesos.
   La creación exclusiva del directorio de sesión impide capturas concurrentes
   usando copias del permiso ligadas a ese mismo directorio.
5. No se borra ni restaura el marcador tras fallo o cancelación. Otra sesión
   requiere decisión explícita nueva, otro permiso y directorio. No existe resume.

El permiso es una **declaración local del operador**, no una licencia del proveedor,
firma jurídica ni defensa contra alguien que edite los archivos/código a propósito.
No convierte una frase en el JSON en prueba de licitud. La revisión actual no se
marcó resuelta y no se emitió un permiso real en esta tarea. Los permisos de tests
solo viven en temporales con evidencia example.invalid y HTTP simulado.

Se conserva el límite de 12 posiciones, intervalo mínimo de 60 s entre inicios,
una consulta al manifiesto y sin reintentos, redirects o paralelismo. Antes de
posiciones, el manifiesto debe anunciar exactamente el endpoint oficial revisado
y disponibilidad. Error, mantenimiento declarado, 401/403/429, decode error o
tres snapshots sin GPS relevante nuevo detienen la sesión; no se eluden bloqueos.

## Condiciones: evaluación concreta

Fuentes consultadas públicamente el **2026-11-13**:

| Evidencia | Verificado | Límite / consecuencia |
| --- | --- | --- |
| [Anuncio oficial GTFS-RT](https://www.transmilenio.gov.co/comunicaciones/noticias-de-transmilenio/especiales-transmilenio/datos-abiertos-tiempo-real-transmilenio-conecta-operacion-sistema-tecnologia-ciudad) | Invita a explorar/aprovechar recursos y vincula apertura con investigación y reutilización | Respalda finalidad exploratoria; no establece aquí plazo de archivo, cuota o licencia específica |
| [Condiciones generales web](https://www.transmilenio.gov.co/comunicaciones/publicaciones/2025/terminos-y-condiciones-en-el-sitio-web-de-transmilenio) | Acceso gratuito; deber de no afectar el servicio y conservar atribución; restricciones generales de copia/reproducción | Su aplicación a payloads GTFS privados no está aclarada; no afirmar que prohíbe explícitamente este piloto |
| Portal y manifiesto | P1 comprobó HTTP 200 y realtime_available=true a las 22:10 Bogotá; metadatos de posiciones de las 04:19 | Antecedente, no nueva validación del PB. Aviso HTML de mantenimiento oculto no demuestra caída |
| Reglas específicas para 12 GET / 60 s y siete días privados | No encontradas en las páginas inspeccionadas | No afirmar cuota autorizada ni permiso de retención; tampoco prohibición específica demostrada |

La cuestión material es concreta: **¿la apertura anunciada cubre conservar hasta
12 PB originales durante siete días, en privado, para análisis offline sin
redistribución, y ese intervalo respeta las condiciones del servicio?** Se conserva
la pregunta en la [revisión local](../../research/LOCAL_PILOT_CONDITIONS.json).
Puede resolverse con documentación pública aplicable; no se exige automáticamente
convenio comercial, SLA, certificación de identidad ni permiso para producción.
No se contactó a nadie. HTTP accesible no se interpreta como autorización jurídica.
Mientras no se resuelva fundadamente, el comando de emisión con la revisión
actual queda bloqueado. No basta renombrar la decisión sin evidencia.

## Privacidad, parada y recuperación

Capturas, permisos, marcadores y diagnósticos en data/pilots, excluido de Git.
PB originales se conservan sin alterar; recepción UTC, fuente, parámetros, hashes,
estado y manifest/session JSON son el mínimo reproducible reutilizado de P0.
Los registros derivados ya contienen IDs necesarios para diagnóstico; no agregamos
placas ni credenciales a logs, stdout o evidencia pública. Los PB podrían incluir
identificadores/placas: no publicarlos, ni tampoco los JSON derivados con IDs.
El propietario debe controlar permisos del directorio y evitar sincronizarlo con
carpetas públicas; el programa no añade cifrado ni garantiza ACL privadas.

Propuesta de conservación: revisar dentro de siete días tras el diagnóstico;
eliminar originales y derivados identificables solo después de esa revisión.
No hay borrado automático ni se oculta evidencia antes de auditarla. Conservar,
si procede, un resumen sin IDs/placas y trazabilidad suficiente. No es un plazo
otorgado por el proveedor: sigue sujeto a resolver la revisión de condiciones.

Parada manual: **Ctrl+C**; ahora registra operator_interrupted en session.json,
cierra cliente y deja el permiso consumido. Un archivo interrumpido no se trata
como captura exitosa. Revisar session.json y PB/JSON completos con el analizador
offline. Si se corta el proceso a la fuerza puede faltar session.json: conservar
archivos para revisión manual, sin reanudar ni generar timestamps de recepción.
No borrar `.used` para intentar repetir: un fallo conserva el límite de una sesión.

## Ejecución preparada, no realizada

La [guía vigente](../../getting-started/LOCAL_GPS_PILOT.md) contiene comandos
exactos para Windows. Primero resolver la revisión y obtener autorización del
propietario; emitir permiso offline poco antes de la sesión y ejecutarla dentro
de su ventana. No hay permiso real en este repositorio. El analizador P0 sigue
sin inferir identidad operacional, embarque, llegada o duración de viaje.

## Pruebas y cierre

Primera comprobación: **31 tests offline aprobados en 1,46 s**, incluidos los
22 casos previos adaptados y nueve nuevos de vencimiento, vinculación, resolución,
confirmaciones, consumo atómico, interrupción y exclusión de Git. No se llamó
al endpoint real ni se esperaron minutos reales. La regresión HTTP y la revisión
final se registran en la [evidencia P2](../evidence/PHASE3B_P2_VALIDATION_20261113.json):
**64 pruebas aprobadas en 0,93 s**, Ruff correcto, formato de 113 archivos correcto
y pip check sin conflictos. No se repitió la suite completa ni regresiones 3A
que no dependen del mecanismo de permisos. Su código permanece sin modificaciones.

No se ejecutan suites GUI ni completa sin motivo. La siguiente autorización
continúa siendo del propietario. Esta entrega prepara el mecanismo, **no lo
activa para una sesión real**. Riesgos pendientes: conservación aplicable,
frescura/continuidad GPS desconocidas, relojes/IDs candidatos y acceso local privado.
