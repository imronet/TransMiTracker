# Fase 2 — GUI de escritorio

Entrega del 13 de noviembre de 2026, America/Bogota. Se implementa exclusivamente
la interfaz y su integración local. El usuario aprobó el cierre de Fase 1B.
**No se inició Fase 3.**

## Resultado y apertura

Aplicación CustomTkinter ejecutable desde la raíz del proyecto:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.gui
```

Requiere el entorno de `requirements-lock.txt` y una sesión gráfica de Windows.
Se comprobó Python 3.13.14 / Tk 8.6 con CustomTkinter 6.0.0. Se instaló únicamente
CustomTkinter y su dependencia necesaria `darkdetect` 0.8.0; `packaging` ya estaba.
No se instaló un empaquetador ni se crearon ejecutables PyInstaller.

La ventana tiene navegación lateral, dashboard, dos perfiles, configuración y
diagnóstico. Usa tema oscuro predeterminado y permite claro, panel desplazable,
adaptación del tamaño inicial a pantalla/DPI y ajuste del ancho de textos.
Las pruebas incluyen redimensionamiento a 900 × 650 y escalado de widgets/ventana
al 125 %. Esto no sustituye una validación física en todos los monitores/DPI.

## Uso del editor

1. Abrir Casa → Trabajo o Trabajo → Casa e indicar fecha y hora de salida de
   **ejemplo programado** en America/Bogota.
2. Escribir al menos dos caracteres del nombre, código o ID de origen. La búsqueda
   tiene debounce de 300 ms, consulta FTS y un máximo de 25 resultados; muestra
   ocho sugerencias y pide afinar si hay más. Hacer clic confirma la selección.
3. Seleccionar ruta por nombre, patrón/variante y destino posterior. Se muestran
   nombres, IDs, plataforma y ocurrencia/secuencia cuando corresponda.
4. Configurar de uno a tres tramos y sus caminatas/tolerancias, margen, días,
   ventana, aviso y hora límite. La llegada al día siguiente es explícita.
5. Validar el ejemplo y guardar. Se muestra confirmación con revisión o errores
   por campo/código en español. Cerrar y reabrir recupera los valores.

Un cambio en origen, horario o tramo anterior invalida rutas/patrones/destinos
dependientes. Los siguientes tramos consultan desde la llegada programada anterior
más la caminata y tolerancia declaradas. No se presupone que el destino anterior
conecte físicamente con el origen siguiente, ni se sustituyen caminatas por cero.
Cada transbordo advierte que su conexión espacial no está verificada.

Cuando falta `direction_id`, se mantiene `None` y se muestra sentido no publicado.
Los patrones se distinguen por destino habilitado, plataforma, secuencia y hash,
sin inventar sentidos oficiales. Las estaciones se expanden mediante las reglas
existentes del catálogo; también pueden elegirse plataformas individuales.

## Arquitectura y contratos

`gui/` no contiene SQL ni reglas duplicadas de calendario o recorrido:

| Componente | Responsabilidad |
| --- | --- |
| `app.py` | Ventana, navegación, dashboard, configuración y diagnóstico |
| `editor.py` | Controles y estado de selección dependiente |
| `controller.py` | Orquestar `CatalogService` y `ProfileStore`; convertir texto de formulario |
| `worker.py` | Un trabajador, cancelación pendiente y entrega de resultados en hilo principal |
| `messages.py` | Presentación española de códigos de contrato, sin mensajes brutos sensibles |
| `config.py` | Preferencias JSON y credenciales `.env`, dentro del proyecto |
| `__main__.py` | Punto de entrada independiente de las CLI anteriores |

Cada operación abre/cierra sus propias conexiones SQLite dentro del trabajador.
Ningún trabajador lee widgets ni llama a Tk: los datos se capturan previamente
en el hilo principal y la cola se procesa con `after`. Las respuestas de consultas
reemplazadas se descartan mediante generaciones y tokens de vista. Al cerrar se
cancelan tareas pendientes; una operación local ya en ejecución puede terminar
antes de que salga el proceso. No hay un scheduler de adquisición.

Se conservan los contratos `Result`, `Profile`, `Leg`, `Transfer` y las validaciones
de Fase 1B. Los errores de dominio muestran campo, código y explicación española.
Los errores inesperados no muestran `repr`, traceback ni valores de credenciales.
No se adjuntan secretos a errores, diagnósticos, perfiles ni preferencias JSON.

Dos métodos públicos aditivos de `ProfileStore`, `list_profiles` y `catalog_path`,
evitan que la GUI consulte directamente sus tablas. En el catálogo, la búsqueda
combina el índice FTS con una búsqueda exacta por clave primaria: `stop_id` estaba
marcado `UNINDEXED` en FTS y una búsqueda por ID no podía depender de coincidencias
casuales con nombre/código. No se modifica el esquema ni el SQLite real existente.

## Persistencia, revisión y catálogo

| Archivo local | Contenido |
| --- | --- |
| `data/gui/profiles.sqlite3` | Perfiles, revisiones y registro de versiones; esquema de Fase 1B |
| `data/gui/settings.json` | Tema, catálogo, fecha de ejemplo por perfil, intervalo/avisos futuros |
| `.env` | Solo credenciales configuradas: Croma, token y Chat ID de Telegram |
| `data/phase2/demo/` | Espacio separado para el ejemplo técnico |

Los archivos locales están excluidos de Git. Los tres campos de credenciales
están enmascarados. `.env` **no proporciona cifrado** ni un almacén del sistema.
La escritura conserva líneas de otras variables y no ejecuta expansión de valores.
Las escrituras JSON/`.env` usan un temporal del proyecto y reemplazo por archivo;
no constituyen una transacción única entre todos los archivos y SQLite. Si falla
el guardado de preferencias tras guardar el perfil, el contrato confirma la
revisión guardada y avisa que la fecha de ejemplo no quedó persistida.

Cada edición conserva su `expected_revision`. Una revisión obsoleta produce
`PROFILE_REVISION_CONFLICT`; la GUI pide recargar y no reemplaza el perfil.
Hay confirmación al salir del editor con cambios sin guardar. Si el usuario
modifica campos mientras termina un guardado, se avisa que quedan cambios posteriores.

En Configuración se registra y activa explícitamente otro catálogo local.
Los perfiles antiguos conservan su hash y ruta registrada, y se muestran pendientes
de migración. No se reinterpretan sus IDs. Pueden editarse con su versión anterior
si sigue disponible. **No se implementó un asistente gráfico de migración**:
`preview_migration` y `apply_migration` siguen disponibles en los servicios de Fase
1B. Ningún cambio de catálogo los ejecuta automáticamente.

Con catálogo ausente la ventana sigue navegable y permite indicar una ruta válida.
No crea un SQLite vacío en lugar de un catálogo faltante. Una configuración JSON
corrupta se informa sin sobrescribirla; su reparación manual sigue siendo necesaria.
Las rutas configuradas se restringen al proyecto, incluyendo resolución de enlaces.

## Dashboard y límites funcionales

El dashboard presenta versión/hash, fecha de importación, procedencia y recuentos
del catálogo, perfiles y recorridos guardados, revisiones y ejemplos de horarios
**programados**. La fecha de importación no equivale a cobertura del servicio.
El diagnóstico distingue catálogo disponible, errores de perfil para la fecha
de ejemplo y perfiles pendientes de migración.

Realtime permanece **pendiente de validación de identidad operativa**. Abrir,
navegar, buscar, validar o guardar no consulta los feeds. Configurar credenciales,
intervalos o preferencias de aviso no inicia ninguna integración.

No se implementaron tracking continuo, reconstrucción operativa, predictor,
scheduler de producción, Telegram real, Croma de pago ni PyInstaller. No hay
recomendaciones de salida basadas en GPS ni indicador de seguimiento activo.

Persisten las limitaciones de Fase 1B: se valida un itinerario programado de
ejemplo, no todas las combinaciones óptimas. Una frecuencia sin hora exacta no
demuestra una conexión puntual y no permite guardar como temporalmente válido.
No hay guardado de borradores inválidos ni un motor de rutas peatonales.

## Ejemplo con catálogo oficial y evidencia

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/demo_phase2.py
.\.venv\Scripts\python.exe -m transmitracker.gui --demo
```

`PHASE2_REAL_CATALOG_DEMO.json` separa expresamente catálogo oficial estático de
datos en vivo. La búsqueda Portal Norte devolvió la estación `2000` y sus nodos;
una consulta medida tardó aproximadamente **2,8 ms** en este equipo, sin prometer
igual latencia en otros equipos. No se cargó la lista completa de paraderos.

El ejemplo técnico seleccionó un nodo publicado de esa estación:

| Dato | Valor comprobado |
| --- | --- |
| Origen | `74389` — Portal Norte Regulación, padre `2000` |
| Ruta | `13766` / 2-1 — Mirandela \|\| Portal Norte |
| Sentido | No publicado; conservado desconocido |
| Destino | `56059` — Br. Tejares del Norte II, secuencia 3 desde origen 2 |
| Fecha | 12-11-2026, ejemplo estático |
| Salida / caminata inicial | 08:00 / 2 minutos |
| Embarque / llegada de bus programados | 08:04:56 / 08:12:21 |
| Final / margen / límite | 5 min / 3 min / 09:00 |
| Fin del ejemplo con caminata y margen | 08:20:21; válido |

El script verificó guardado y recuperación abriendo un controlador nuevo y
SHA-256 del SQLite real antes/después: **sin cambios**. La base del catálogo sigue
conteniendo 1.054 rutas, 8.325 nodos y 1.564 patrones. Cero solicitudes HTTP.
El nombre publicado «Regulación» no acredita una conexión peatonal ni una
recomendación de uso; el ejemplo demuestra relaciones y horarios del GTFS.
**No representa el trayecto personal del usuario.**

Capturas de una ventana real de la demo, con datos estáticos:

- [Dashboard oscuro](screenshots/phase2-dashboard-dark.png).
- [Editor de perfil oscuro](screenshots/phase2-profile-dark.png).
- [Configuración clara](screenshots/phase2-settings-light.png).

## Pruebas y archivos

**160 pruebas aprobadas: 138 anteriores + 22 nuevas**. Las nuevas cubren:

- Controladores sin Tk: búsqueda, plataformas, sentido desconocido, selección
  dependiente, transferencia horaria, contratos y errores de formulario.
- Guardado/recuperación de las dos clases, revisión concurrente, cambio de catálogo
  sin migración automática y recuperación ante catálogo no disponible.
- Secretos solo en `.env`, enmascarado, límites de rutas, redacción de errores,
  conservación de configuración corrupta y fallos de escritura.
- Trabajador: callbacks en el hilo principal, respuestas obsoletas, errores y cierre.
- Cuatro pruebas separadas con ventanas Tk reales: apertura/cierre y navegación,
  búsqueda → ruta → patrón → destino → guardado → cierre → reapertura, uno a tres
  tramos e invalidación, y catálogo ausente. Incluyen tema claro y escalado al 125 %.

La suite bloquea conexiones de sockets y transporte HTTP real. Ningún resultado
de fixture se presenta como conexión real. Ruff, formato y `pip check` correctos;
evidencia completa en `PHASE2_VALIDATION_RESULTS.json`. Las pruebas de ventanas
requieren un escritorio disponible; no se sustituyeron por mocks de Tk.

```powershell
.\.venv\Scripts\python.exe scripts/verify_phase0.py --output docs/PHASE2_VALIDATION_RESULTS.json
.\.venv\Scripts\python.exe -m pytest -m gui -q
.\.venv\Scripts\python.exe -m pytest -m 'not gui' -q
```

Archivos nuevos: los ocho módulos de `src/transmitracker/gui/`,
`scripts/demo_phase2.py`, `tests/test_gui_controller.py`, `tests/test_gui_widgets.py`,
este informe, dos evidencias JSON y las capturas. Modificados:
`catalog/queries.py`, `profiles/store.py`, `scripts/verify_phase0.py`,
`pyproject.toml`, `requirements.txt`, `requirements-lock.txt`, `.env.example`,
`.gitignore`, README y adenda del Implementation Plan. Se conserva la estructura
`src/transmitracker/` y no se sobrescriben informes/evidencias de fases anteriores.

La Fase 3 sigue pendiente de autorización y de la evidencia operativa real
requerida en las fases anteriores.
