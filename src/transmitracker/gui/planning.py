"""Small saved-profile planning panel; all SQLite work goes through UiWorker."""

import tkinter as tk
from datetime import datetime
from uuid import uuid4

import customtkinter as ctk

from transmitracker.catalog.common import BOGOTA
from transmitracker.gui.editor import entry
from transmitracker.gui.messages import field_label, result_text, technical_text, window_help
from transmitracker.profiles.models import ProfileKind
from transmitracker.profiles.planning import DISCLAIMER


def render_plan(result):
    if not result.ok:
        return "Sin alternativa verificable.\n" + result_text(result)
    plan = result.data
    lines = [
        DISCLAIMER,
        f"Salida orientativa: {plan.departure_at}",
        f"Caminata inicial: {plan.initial_walk_minutes} min",
    ]
    for step in plan.steps:
        if step.leg_index:
            lines.append(
                f"Transbordo: caminata {step.transfer_walk_minutes} min + buffer {step.transfer_buffer_minutes} min (conexión peatonal no verificada)"
            )
        lines.extend(
            [
                f"Tramo {step.leg_index + 1} · {step.route_name}: {step.origin_name} → {step.destination_name}",
                f"Abordaje publicado: {step.boarding_at} · llegada programada: {step.arrival_at}",
                f"Fecha de servicio GTFS: {step.service_date} · base: {step.time_basis}",
                f"Espera implícita programada: {step.scheduled_wait_seconds:g} s (no observada)",
            ]
        )
    lines.extend(
        [
            f"Caminata final: {plan.final_walk_minutes} min · margen configurado: {plan.safety_margin_minutes} min",
            f"Llegada con caminata final: {plan.arrival_at}",
            f"Llegada calculada incluyendo margen: {plan.arrival_with_margin_at}",
            f"Límite guardado: {plan.arrival_deadline_at}"
            if plan.arrival_deadline_at
            else "Regreso: sin aplicar límite de llegada de ida.",
            f"Horizonte de abordajes: {plan.search_start} → {plan.boarding_horizon_end} ({plan.window_minutes} min)",
            f"Catálogo importado: {plan.catalog_imported_at}",
            "No garantiza puntualidad, disponibilidad ni alcanzar físicamente el vehículo.",
            result_text(result),
        ]
    )
    return "\n".join(lines)


def stamp(value):
    if not value:
        return "No determinada"
    parsed = datetime.fromisoformat(value)
    return parsed.strftime("%d/%m/%Y %H:%M:%S") + (
        f".{parsed.microsecond:06}" if parsed.microsecond else ""
    )


def diagnostic_text(diagnostic):
    if diagnostic is None:
        return "No se dispone de una alternativa completa justificable para esta consulta. Revisa el dato señalado."
    lines = [
        f"Fecha consultada: {diagnostic.planning_date} · {diagnostic.leg_count} tramo(s)",
        f"Hora límite: {stamp(diagnostic.deadline)}",
        f"Ventana realmente examinada: {stamp(diagnostic.search_start)} → {stamp(diagnostic.boarding_horizon_end)}",
        f"Disponibilidad inicial tras caminar: {stamp(diagnostic.first_ready_at)}",
        f"Caminata inicial: {diagnostic.initial_walk_minutes} min · final: {diagnostic.final_walk_minutes} min · margen: {diagnostic.safety_margin_minutes} min",
    ]
    for i, (walk, buffer) in enumerate(diagnostic.transfer_minutes, 1):
        lines.append(
            f"Transbordo {i}: caminata {walk} min + tolerancia {buffer} min. Recorrido a pie no verificado."
        )
    if diagnostic.incomplete_field:
        lines.append("Restricción identificada: " + field_label(diagnostic.incomplete_field))
    if diagnostic.explicit_options_per_leg:
        lines.append(
            "Alternativas explícitas examinadas por tramo: "
            + ", ".join(
                f"tramo {i + 1}: {count}"
                for i, count in enumerate(diagnostic.explicit_options_per_leg)
            )
        )
    if diagnostic.catalog_imported_at:
        lines.append("Catálogo importado: " + stamp(diagnostic.catalog_imported_at))
    if (
        diagnostic.first_ready_at
        and diagnostic.boarding_horizon_end
        and datetime.fromisoformat(diagnostic.first_ready_at)
        > datetime.fromisoformat(diagnostic.boarding_horizon_end)
    ):
        lines.append(
            "La caminata inicial termina después del final de la ventana. Con estos ajustes no queda intervalo para buscar un abordaje; revisa la ventana en el editor. Esto no demuestra ausencia de servicio."
        )
    if diagnostic.discarded:
        lines.append(
            f"Llegada incluyendo caminata y margen: {stamp(diagnostic.discarded.arrival_with_margin_at)}. Supera el límite en {diagnostic.lateness_seconds / 60:g} min."
        )
    else:
        lines.append(
            "No se ha demostrado un itinerario completo descartado. Una llegada de un tramo aislado no es la llegada final de tu recorrido. No se amplió el horizonte."
        )
    return "\n".join(lines)


class PlanningPanel(ctk.CTkFrame):
    def __init__(self, host, parent, stored):
        super().__init__(parent, fg_color="transparent")
        self.host, self.stored = host, stored
        self.view = host.view_token
        self.key = "static-planning-" + uuid4().hex
        self.generation = 0
        self.last_result = None
        host.label(self, "Consulta de tu perfil guardado", size=24)
        host.label(self, DISCLAIMER)
        host.label(
            self, f"Perfil guardado · revisión {stored.revision}. Esta consulta no guarda cambios."
        )
        host.label(
            self,
            f"Ventana de búsqueda de buses programados: {stored.profile.departure_window_minutes} minutos.\n"
            + window_help(stored.profile.kind),
        )
        fields = ctk.CTkFrame(self)
        fields.pack(fill="x", padx=12, pady=8)
        self.day = entry(
            fields, "Fecha civil de salida · AAAA-MM-DD", datetime.now(BOGOTA).date().isoformat(), 0
        )
        self.day_var = tk.StringVar(value=self.day.get())
        self.day.configure(textvariable=self.day_var)
        self.clock = None
        self.clock_edited = False
        if stored.profile.kind == ProfileKind.TO_HOME:
            usual = stored.profile.usual_departure
            self.clock = entry(
                fields,
                "Salida del trabajo · HH:MM o HH:MM:SS",
                usual.isoformat() if usual else "",
                0,
                1,
            )
            self.clock_var = tk.StringVar(value=self.clock.get())
            self.clock.configure(textvariable=self.clock_var)
            self.clock_var.trace_add("write", self.clock_changed)
        else:
            deadline = stored.profile.arrival_deadline
            host.label(
                self,
                f"Llegada límite guardada: {deadline.strftime('%H:%M')} · desplazamiento de día: {stored.profile.arrival_day_offset}",
            )
        self.day_var.trace_add("write", self.changed)
        self.button = ctk.CTkButton(
            self, text="Consultar planificación estática", command=self.request
        )
        self.button.pack(anchor="w", padx=18, pady=8)
        self.result_card = ctk.CTkFrame(self)
        self.result_card.pack(fill="x", padx=12, pady=12)
        self.result_title = host.label(self.result_card, "Resultado de la consulta", size=22)
        self.output = host.label(
            self.result_card, "Selecciona fecha y consulta. No se necesitan datos GPS."
        )
        self.detail_area = ctk.CTkFrame(self, fg_color="transparent")
        self.detail_area.pack(fill="x")
        self.technical_button = ctk.CTkButton(
            self,
            text="Ver detalles técnicos",
            command=self.toggle_technical,
            fg_color=("#526174", "#394c64"),
        )
        self.technical_button.pack(anchor="w", padx=18, pady=8)
        self.technical = ctk.CTkLabel(self, text="", justify="left", anchor="w", wraplength=600)

    def clear_details(self):
        for child in self.detail_area.winfo_children():
            child.destroy()
        self.technical.pack_forget()
        self.technical.configure(text="")
        self.technical_button.configure(text="Ver detalles técnicos")

    def toggle_technical(self):
        if self.technical.winfo_ismapped():
            self.technical.pack_forget()
            self.technical_button.configure(text="Ver detalles técnicos")
        else:
            self.technical.pack(fill="x", padx=18, pady=8)
            self.technical_button.configure(text="Ocultar detalles técnicos")

    def itinerary_cards(self, plan, discarded=False):
        host = self.host
        if discarded:
            card = host.card(self.detail_area)
            host.label(
                card,
                "Alternativa programada descartada — no cumple las condiciones",
                size=20,
                color=("#805700", "#ffd18a"),
            )
            host.label(
                card,
                f"No es una salida recomendada. Salida de este itinerario: {stamp(plan.departure_at)}\nLlegada con caminata final: {stamp(plan.arrival_at)}",
            )
        for step in plan.steps:
            card = host.card(self.detail_area)
            host.label(card, f"Tramo {step.leg_index + 1} · {step.route_name}", size=20)
            host.label(
                card,
                f"{step.origin_name} → {step.destination_name}\nAbordaje publicado: {stamp(step.boarding_at)}\nLlegada programada del tramo: {stamp(step.arrival_at)}",
            )
            if step.leg_index:
                host.label(
                    card,
                    f"Transbordo {step.leg_index}: conexión entre el tramo {step.leg_index} y el tramo {step.leg_index + 1}.\nCaminata: {step.transfer_walk_minutes} min + tolerancia: {step.transfer_buffer_minutes} min. No se ha comprobado el recorrido a pie; el aviso no significa que sea imposible.",
                    color=("#805700", "#ffd18a"),
                )
            basis = (
                "Horario publicado"
                if step.time_basis == "scheduled"
                else "Frecuencia con horas exactas"
            )
            host.label(
                card,
                f"Fecha de servicio GTFS: {step.service_date} · {basis}\nEspera implícita programada: {step.scheduled_wait_seconds:g} s (no observada)",
            )
        card = host.card(self.detail_area)
        host.label(card, "Caminatas, margen y procedencia", size=20)
        host.label(
            card,
            f"Caminata inicial: {plan.initial_walk_minutes} min · final: {plan.final_walk_minutes} min · margen configurado: {plan.safety_margin_minutes} min\nLlegada con caminata final: {stamp(plan.arrival_at)}\nLlegada incluyendo margen: {stamp(plan.arrival_with_margin_at)}\nVentana efectiva: {stamp(plan.search_start)} → {stamp(plan.boarding_horizon_end)}\nCatálogo importado: {stamp(plan.catalog_imported_at)}\nNo garantiza puntualidad, disponibilidad ni alcanzar físicamente el vehículo.",
        )

    def show_result(self, result):
        self.clear_details()
        if result.ok:
            plan = result.data
            self.result_title.configure(
                text="Itinerario programado encontrado", text_color=("#007b72", "#36d5ba")
            )
            self.output.configure(
                text=f"Salida orientativa: {stamp(plan.departure_at)}\nLlegada con caminata final: {stamp(plan.arrival_at)}\nLlegada incluyendo margen: {stamp(plan.arrival_with_margin_at)}\n{len(plan.steps)} tramo(s) · rutas: {', '.join(s.route_name for s in plan.steps)}\nEspera implícita programada, no observada; detalles a continuación.\n{DISCLAIMER}"
            )
            self.itinerary_cards(plan)
        else:
            self.result_title.configure(
                text="Sin alternativa verificable", text_color=("#8e361b", "#ffbb98")
            )
            self.output.configure(text=result_text(result, self.stored.profile))
            card = self.host.card(self.detail_area)
            self.host.label(card, "Qué se pudo comprobar", size=20)
            diagnostic = getattr(result, "diagnostic", None)
            self.host.label(card, diagnostic_text(diagnostic))
            if diagnostic and diagnostic.discarded:
                self.itinerary_cards(diagnostic.discarded, discarded=True)
        if result.ok and result.warnings:
            card = self.host.card(self.detail_area)
            self.host.label(
                card, "Advertencias que debes conocer", size=20, color=("#805700", "#ffd18a")
            )
            self.host.label(card, result_text(result, self.stored.profile))
        self.technical.configure(
            text=technical_text(result) or "Consulta local completada sin incidencias técnicas."
        )

    def clock_changed(self, *args):
        self.clock_edited = True
        self.changed()

    def changed(self, *args):
        self.generation += 1
        self.last_result = None
        self.host.worker.invalidate(self.key)
        if hasattr(self, "output"):
            self.clear_details()
            self.output.configure(text="Fecha u hora modificada; vuelva a consultar.")

    def request(self):
        self.generation += 1
        self.last_result = None
        generation = self.generation
        day = self.day.get()
        clock = self.clock.get() if self.clock else None
        if not self.clock_edited and self.stored.profile.usual_departure is not None:
            # Preserve the stored time, including microseconds. Edited text
            # always goes through the controller's strict explicit-clock parser.
            clock = None
        self.clear_details()
        self.output.configure(text="Consultando exclusivamente el catálogo local…")
        controller = self.host.controller
        profile_id, revision = self.stored.profile.profile_id, self.stored.revision

        def done(value, error):
            if (
                self.host.closed
                or self.view != self.host.view_token
                or generation != self.generation
            ):
                return
            self.last_result = value
            if error:
                self.output.configure(text=error)
            else:
                self.show_result(value)
            self.host.fit_text()

        self.host.worker.submit(
            self.key,
            lambda: controller.plan_static(profile_id, day, clock, expected_revision=revision),
            done,
        )

    def destroy(self):
        self.host.worker.invalidate(self.key)
        super().destroy()
