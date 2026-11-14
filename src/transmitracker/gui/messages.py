"""Spanish presentation of domain codes; never render raw exception/secret values."""

MESSAGES = {
    "INVALID_PLANNING_DATE": "Revise la fecha local AAAA-MM-DD y la hora HH:MM.",
    "DEPARTURE_TIME_REQUIRED": "Indique una hora de salida del trabajo o configure su salida habitual.",
    "NO_SCHEDULED_SERVICE": "Sin servicio publicado compatible para esta fecha y selección.",
    "TRANSFER_INCOMPATIBLE": "Los servicios publicados no permiten el transbordo con su caminata y buffer.",
    "HORIZON_INSUFFICIENT": "El horizonte configurado no contiene una alternativa justificable. No se amplió automáticamente.",
    "UNRESOLVED_ALTERNATIVES_EXCLUDED": "Se excluyeron alternativas sin hora exacta; la elección solo compara horarios explícitos.",
    "LEG_STRUCTURE_INVALID": "La ruta, el patrón, el sentido o las ocurrencias de origen/destino no coinciden. Se conservaron sus datos.",
    "INVALID_DRAFT": "El borrador contiene campos incompatibles; no se sobrescribió el anterior.",
    "DRAFT_REVISION_CONFLICT": "El borrador cambió en otra ventana. Recárguelo antes de guardar.",
    "DRAFT_STORE_ERROR": "No se pudo guardar el borrador; sus campos permanecen en pantalla.",
    "EXAMPLE_PREFERENCE_NOT_SAVED": "El perfil sí se guardó, pero no se pudo guardar la fecha de ejemplo en preferencias.",
    "INVALID_FORM": "Revise los minutos y los campos obligatorios.",
    "INVALID_PAYLOAD": "Complete los campos y use horas en formato HH:MM.",
    "LEG_COUNT": "El perfil debe tener entre uno y tres tramos.",
    "TRANSFER_COUNT": "Configure una caminata y tolerancia por transbordo.",
    "INVALID_ID": "Seleccione un paradero, una ruta y un patrón válidos.",
    "INVALID_SEQUENCE": "El destino debe estar después del origen en el patrón.",
    "INVALID_MINUTES": "Use minutos enteros entre 0 y 1440; la ventana debe ser mayor que cero.",
    "INVALID_WEEKDAYS": "Seleccione al menos un día de funcionamiento.",
    "INVALID_CLOCK": "Use una hora local válida en formato HH:MM.",
    "INVALID_DAY_OFFSET": "Seleccione llegada el mismo día o al día siguiente.",
    "INVALID_DATETIME": "Indique una fecha y hora de ejemplo válidas.",
    "PROFILE_INACTIVE_DAY": "El perfil no está activo en el día de salida de ejemplo.",
    "LEG_SERVICE_INVALID": "El recorrido no está disponible en esa fecha, hora, sentido o secuencia.",
    "SCHEDULE_TIME_UNRESOLVED": "El GTFS no ofrece horas exactas para demostrar esta conexión.",
    "ARRIVAL_DEADLINE_EXCEEDED": "El ejemplo programado, caminatas y margen superan la hora límite.",
    "TRANSFER_PATH_UNVERIFIED": "Conexión peatonal no verificada: se conserva el tiempo que indicó.",
    "NOTICE_AFTER_DEPARTURE": "La hora de aviso es posterior a la salida de ejemplo; no se enviará nada.",
    "CATALOG_VERSION_MISMATCH": "El perfil pertenece a otra versión. No se migró automáticamente.",
    "PROFILE_CATALOG_NOT_ACTIVE": "Pendiente de migración: se conserva el catálogo original del perfil.",
    "PROFILES_PINNED_TO_OLDER_CATALOG": "Hay perfiles asociados a otra versión; no se modificaron.",
    "CATALOG_UNAVAILABLE": "No se puede leer el catálogo. Revise la ruta y su disponibilidad.",
    "CATALOG_NOT_REGISTERED": "La versión del catálogo no está registrada.",
    "CATALOG_PATH_REUSED": "Una ruta registrada no puede contener otra versión del catálogo.",
    "PROFILE_REVISION_CONFLICT": "El perfil cambió en otra ventana. Recárguelo antes de guardar.",
    "PROFILE_KIND_EXISTS": "Ya existe un perfil para esta dirección. Recárguelo para editarlo.",
    "PROFILE_STORE_UNAVAILABLE": "No se pudo guardar el perfil. Revise el archivo y vuelva a intentar.",
    "INVALID_INTERVAL": "Use al menos 60 segundos. Esta preferencia no autoriza ni inicia sondeos.",
}


def result_text(result):
    issues = result.errors + result.warnings
    return "\n".join(
        f"{item.field} · {MESSAGES.get(item.code, 'Revise este campo o recurso local.')} [{item.code}]"
        for item in issues
    )
