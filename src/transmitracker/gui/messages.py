"""Central user presentation; technical codes remain available separately."""

import re

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
    "SCHEDULE_WINDOW_UNVERIFIED": "Existe servicio activo y estructuralmente compatible, pero faltan horas para confirmar un abordaje dentro de la ventana consultada.",
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


MESSAGES.update(
    {
        "ARRIVAL_DEADLINE_EXCEEDED": "No encontramos una alternativa programada que permita cumplir tu hora límite de llegada. Revisa el límite, las caminatas y la ventana de búsqueda; no cambiamos tus ajustes.",
        "NO_SCHEDULED_SERVICE": "No hay servicio publicado compatible en el ámbito consultado. Revisa fecha, patrón y paradas; esto no significa que todo el sistema carezca de buses.",
        "SCHEDULE_TIME_UNRESOLVED": "Faltan horas publicadas o solo hay frecuencias sin salida exacta. No podemos justificar una hora puntual. Revisa la disponibilidad horaria del catálogo.",
        "HORIZON_INSUFFICIENT": "La ventana de búsqueda no permite demostrar una alternativa compatible. Puedes revisarla en el editor y guardarla si decides cambiarla; no se amplía automáticamente.",
        "TRANSFER_INCOMPATIBLE": "No se pudo encadenar el servicio con la caminata y tolerancia configuradas. Revisa los tramos y tiempos del transbordo.",
        "PROFILE_INACTIVE_DAY": "Tu perfil no está activo en la fecha elegida. Elige otro día o revisa los días activos en el editor.",
        "DEPARTURE_TIME_REQUIRED": "Indica a qué hora sales del trabajo o configura una salida habitual. Sin esa hora no calculamos una llegada absoluta.",
        "TRANSFER_PATH_UNVERIFIED": "No se ha comprobado el recorrido a pie entre estos tramos. El cálculo utiliza tus minutos configurados. Este aviso no significa que el transbordo sea imposible.",
    }
)

FIELD_LABELS = {
    "departure_window_minutes": "Ventana de búsqueda de buses programados",
    "planning_date": "Fecha de salida",
    "departure_clock": "Salida del trabajo",
    "arrival_deadline": "Hora límite de llegada",
    "active_weekdays": "Días activos",
    "initial_walk_minutes": "Caminata inicial",
    "final_walk_minutes": "Caminata final",
    "safety_margin_minutes": "Margen de seguridad",
    "catalog": "Catálogo local",
    "catalog_sha256": "Versión del catálogo",
    "profile": "Perfil guardado",
    "legs": "Tramos del recorrido",
    "transfers": "Transbordos",
    "origin_stop_id": "Origen",
    "destination_stop_id": "Destino",
    "route_id": "Ruta",
    "pattern_id": "Patrón",
    "notification_time": "Hora de aviso",
    "arrival_day_offset": "Día de llegada",
    "schedule": "Horario publicado",
}


def field_label(field):
    match = re.match(r"^(legs|transfers)\.(\d+)(?:\.(.*))?$", field)
    if match:
        group, value, suffix = match.groups()
        index = int(value)
        label = (
            f"{'Primer' if index == 0 else 'Segundo'} transbordo: conexión entre el tramo {index + 1} y el tramo {index + 2}"
            if group == "transfers"
            else f"Tramo {index + 1}"
        )
        return label + (
            " · " + FIELD_LABELS.get(suffix, "Selección del recorrido") if suffix else ""
        )
    return FIELD_LABELS.get(field, "Consulta local")


def result_text(result, profile=None):
    lines = []
    for item in result.errors + result.warnings:
        message = MESSAGES.get(
            item.code,
            "No se pudo completar esta comprobación local. Revisa los datos y el archivo asociado.",
        )
        match = re.fullmatch(r"transfers\.(\d+)", item.field)
        if item.code == "TRANSFER_PATH_UNVERIFIED" and profile and match:
            index = int(match[1])
            if index < len(profile.transfers):
                transfer = profile.transfers[index]
                message += f" Caminata: {transfer.walking_minutes} min; tolerancia: {transfer.buffer_minutes} min."
        lines.append(f"{field_label(item.field)} · {message}")
    return "\n".join(lines)


def technical_text(result):
    return "\n".join(f"{item.field} · {item.code}" for item in result.errors + result.warnings)


def window_help(kind):
    interval = (
        "Intervalo anterior al límite de llegada"
        if getattr(kind, "value", kind) == "home_to_work"
        else "Intervalo posterior a la salida del trabajo"
    )
    return (
        f"{interval} dentro del cual se examinan abordajes publicados, sujeto a las demás restricciones. "
        "No es espera estimada ni duración del viaje, no garantiza buses y no se amplía por cada transbordo. "
        "Una ventana insuficiente puede impedir encontrar una alternativa."
    )
