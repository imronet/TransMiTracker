"""Small saved-profile planning panel; all SQLite work goes through UiWorker."""

import tkinter as tk
from datetime import datetime
from uuid import uuid4

import customtkinter as ctk

from transmitracker.catalog.common import BOGOTA
from transmitracker.gui.editor import entry
from transmitracker.gui.messages import result_text
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


class PlanningPanel(ctk.CTkFrame):
    def __init__(self, host, parent, stored):
        super().__init__(parent, fg_color="transparent")
        self.host, self.stored = host, stored
        self.view = host.view_token
        self.key = "static-planning-" + uuid4().hex
        self.generation = 0
        self.last_result = None
        host.label(self, DISCLAIMER, size=20)
        host.label(
            self, f"Perfil guardado · revisión {stored.revision}. Esta consulta no guarda cambios."
        )
        fields = ctk.CTkFrame(self)
        fields.pack(fill="x", padx=12, pady=8)
        self.day = entry(
            fields, "Fecha civil de salida · AAAA-MM-DD", datetime.now(BOGOTA).date().isoformat(), 0
        )
        self.day_var = tk.StringVar(value=self.day.get())
        self.day.configure(textvariable=self.day_var)
        self.clock = None
        if stored.profile.kind == ProfileKind.TO_HOME:
            usual = stored.profile.usual_departure
            self.clock = entry(
                fields, "Salida del trabajo · HH:MM", usual.strftime("%H:%M") if usual else "", 0, 1
            )
            self.clock_var = tk.StringVar(value=self.clock.get())
            self.clock.configure(textvariable=self.clock_var)
            self.clock_var.trace_add("write", self.changed)
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
        self.output = host.label(self, "Seleccione fecha y consulte. No se necesitan datos GPS.")

    def changed(self, *args):
        self.generation += 1
        self.last_result = None
        self.host.worker.invalidate(self.key)
        if hasattr(self, "output"):
            self.output.configure(text="Fecha u hora modificada; vuelva a consultar.")

    def request(self):
        self.generation += 1
        self.last_result = None
        generation = self.generation
        day = self.day.get()
        clock = self.clock.get() if self.clock else None
        self.output.configure(text="Consultando exclusivamente el catálogo local…")
        controller = self.host.controller

        def done(value, error):
            if (
                self.host.closed
                or self.view != self.host.view_token
                or generation != self.generation
            ):
                return
            self.last_result = value
            self.output.configure(text=error or render_plan(value))
            self.host.fit_text()

        self.host.worker.submit(
            self.key,
            lambda: controller.plan_static(
                self.stored.profile.profile_id, day, clock, expected_revision=self.stored.revision
            ),
            done,
        )

    def destroy(self):
        self.host.worker.invalidate(self.key)
        super().destroy()
