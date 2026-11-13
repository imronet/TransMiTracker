# Configurar recorridos habituales

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

Casa → Trabajo solicita el límite de llegada y días activos; el predictor futuro
calculará una recomendación de salida. Trabajo → Casa permite una salida habitual
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

## Catálogo, configuración y privacidad

GTFS estático es un catálogo de rutas, paraderos, patrones, calendarios y horarios
publicados. No indica la posición actual de un vehículo. La fecha de importación
no garantiza servicio en todos los días. Los datos Realtime y las predicciones
no están activos; tampoco existen estadísticas históricas útiles en la GUI.

La base de catálogo se abre en modo de lectura. Configurar otro SQLite registra
y activa explícitamente su versión, pero conserva los perfiles antiguos y muestra
el aviso de migración. El cambio no remapea IDs. El asistente gráfico de migración
no está implementado; los servicios explícitos de Fase 1B siguen disponibles.

Los perfiles, revisiones, borradores y resultados de consultas se guardan en
`data/gui/profiles.sqlite3`; tema y preferencias en `data/gui/settings.json`.
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
