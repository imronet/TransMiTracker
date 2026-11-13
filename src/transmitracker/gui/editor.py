"""Profile widgets, dependent selectors and nonblocking autocomplete."""

from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import customtkinter as ctk

from transmitracker.catalog.common import BOGOTA
from transmitracker.gui.controller import PROFILE_TITLES, parse_departure
from transmitracker.gui.help import Tooltip
from transmitracker.gui.messages import result_text
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import PatternChoice, ProfileKind


def entry(parent, label, value, row, column=0, width=160):
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.grid(row=row, column=column, sticky="ew", padx=8, pady=6)
    ctk.CTkLabel(frame, text=label, anchor="w").pack(fill="x")
    widget = ctk.CTkEntry(frame, width=width, height=34)
    widget.insert(0, str(value))
    widget.pack(fill="x", pady=(3, 0))
    return widget


class LegEditor(ctk.CTkFrame):
    def __init__(self, editor, index, saved=None, labels=None, ui_state=None):
        super().__init__(editor.legs_area, corner_radius=12)
        self.editor, self.index = editor, index
        self.token = (ui_state or {}).get("uid", uuid4().hex)
        self.mode = (ui_state or {}).get("mode", "Origen primero")
        self.pending_origin = (ui_state or {}).get("pending_origin", "0") == "1"
        self.origin = self.route = self.pattern = self.destination = None
        self.routes, self.patterns, self.destinations = {}, {}, {}
        self.origins = {}
        self.timer = None
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text=f"TRAMO {index + 1}", font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        self.mode_menu = ctk.CTkOptionMenu(
            self, values=["Origen primero", "Ruta primero"], width=160, command=self.switch_mode
        )
        self.mode_menu.set(self.mode)
        self.mode_menu.grid(row=0, column=0, sticky="e", padx=18, pady=(14, 4))
        self.origin_title = ctk.CTkLabel(
            self, text="Origen · nombre, código o ID; puede elegir una plataforma", anchor="w"
        )
        self.origin_title.grid(row=1, column=0, sticky="ew", padx=18)
        self.search = ctk.CTkEntry(self, placeholder_text="Buscar estación o paradero…", height=36)
        self.search.grid(row=2, column=0, sticky="ew", padx=18, pady=6)
        self.search.bind("<KeyRelease>", self.search_changed)
        self.route_search = ctk.CTkEntry(
            self, placeholder_text="Buscar ruta por número o nombre…", height=36
        )
        self.route_search.bind("<KeyRelease>", self.route_search_changed)
        self.matches = ctk.CTkFrame(self, fg_color="transparent", height=1)
        self.matches.grid(row=3, column=0, sticky="ew", padx=18)
        self.origin_label = ctk.CTkLabel(
            self,
            text="Seleccione un resultado de búsqueda",
            anchor="w",
            wraplength=650,
            text_color=("#526174", "#9eafc4"),
        )
        self.origin_label.grid(row=4, column=0, sticky="ew", padx=18, pady=4)
        self.route_menu = self.menu("Ruta disponible", 5, self.choose_route)
        self.pattern_menu = self.menu("Patrón · destino y secuencia", 7, self.choose_pattern)
        self.destination_menu = self.menu("Destino posterior al origen", 9, self.choose_destination)
        self.origin_menu = self.menu(
            "Origen habilitado en este patrón", 13, self.select_pattern_origin
        )
        actions = self.actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=11, column=0, sticky="ew", padx=18, pady=(10, 16))
        ctk.CTkButton(
            actions, text="Consultar opciones del catálogo", command=self.fetch_routes, width=220
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Eliminar tramo",
            command=lambda: editor.remove_leg(index),
            width=130,
            fg_color=("#b7c7d9", "#34445b"),
            text_color=("#17283c", "#edf3fc"),
        ).pack(side="right")
        if saved:
            self.origin = saved["origin_stop_id"] or None
            self.route = saved["route_id"] or None
            self.pattern = (
                PatternChoice(
                    saved["route_id"],
                    saved["direction_id"],
                    saved["pattern_id"],
                    saved["origin_stop_id"],
                    saved["origin_sequence"],
                    (),
                    None,
                    "saved",
                )
                if saved["pattern_id"]
                else None
            )
            self.destination = saved if saved["destination_stop_id"] else None
            self.origin_label.configure(
                text=f"{labels['origin'] if labels else self.origin} · ID {self.origin}"
            )
            self.search.insert(0, labels["origin"] if labels else self.origin or "")
            self.route_menu.set(
                labels["route"] if labels else f"Ruta {self.route} · selección guardada"
            )
            direction = (
                "sentido no publicado"
                if not self.pattern or self.pattern.direction_id is None
                else f"sentido {self.pattern.direction_id}"
            )
            self.pattern_menu.set(
                f"Patrón {saved['pattern_id'][:12]} · {direction} · origen sec. {saved['origin_sequence']}"
            )
            self.destination_menu.set(
                f"{labels['destination'] if labels else saved['destination_stop_id']} · sec. {saved['destination_sequence']}"
            )
        if ui_state:
            self.search.delete(0, "end")
            self.search.insert(0, ui_state["search_text"])
            self.route_search.insert(0, ui_state["route_search"])
            self.origin_label.configure(text=ui_state["origin_label"])
            self.origin_menu.set(ui_state["origin_choice_label"])
            for key in ("route", "pattern", "destination"):
                getattr(self, key + "_menu").set(ui_state[key + "_label"])
        self.layout_mode()

    def menu(self, title, row, callback):
        caption = ctk.CTkLabel(self, text=title, anchor="w")
        caption.grid(row=row, column=0, sticky="ew", padx=18)
        menu = ctk.CTkOptionMenu(
            self,
            values=["Seleccione…"],
            command=callback,
            state="disabled",
            height=34,
            dynamic_resizing=False,
        )
        menu.grid(row=row + 1, column=0, sticky="ew", padx=18, pady=(3, 9))
        menu.caption = caption
        return menu

    def layout_mode(self):
        for widget in (
            self.origin_title,
            self.search,
            self.matches,
            self.origin_label,
            self.route_search,
            self.origin_menu,
            self.origin_menu.caption,
        ):
            widget.grid_remove()
        if self.mode == "Origen primero":
            ordered = [
                self.origin_title,
                self.search,
                self.matches,
                self.origin_label,
                self.route_menu.caption,
                self.route_menu,
                self.pattern_menu.caption,
                self.pattern_menu,
                self.destination_menu.caption,
                self.destination_menu,
                self.actions,
            ]
        else:
            ordered = [
                self.route_search,
                self.route_menu.caption,
                self.route_menu,
                self.pattern_menu.caption,
                self.pattern_menu,
                self.origin_menu.caption,
                self.origin_menu,
                self.origin_label,
                self.destination_menu.caption,
                self.destination_menu,
                self.actions,
            ]
        for row, widget in enumerate(ordered, 1):
            widget.grid(row=row, column=0, sticky="ew", padx=18, pady=4)

    def switch_mode(self, value):
        self.mode = value
        if (
            value == "Origen primero"
            and self.origin
            and not self.pending_origin
            and not self.search.get()
        ):
            self.search.insert(0, self.origin_label.cget("text").split(" · ")[0])
        for key in ("search", "routes", "patterns", "destinations", "origins"):
            self.editor.app.worker.invalidate(self.editor.token + f"-{self.token}-{key}")
        self.layout_mode()
        self.editor.mark_dirty()
        if value == "Ruta primero" and self.pattern:
            self.load_pattern_origins()

    def route_search_changed(self, _event=None):
        self.editor.mark_dirty()
        if self.timer:
            self.after_cancel(self.timer)
        self.editor.app.worker.invalidate(self.editor.token + f"-{self.token}-routes")
        text = self.route_search.get().strip()
        self.timer = self.after(300, lambda: self.find_routes(text))

    def find_routes(self, query):
        self.timer = None
        sha = self.editor.sha
        controller = self.editor.app.controller
        self.editor.run(
            f"{self.token}-routes",
            lambda: controller.search_routes(query, sha),
            self.show_routes,
        )

    def load_pattern_origins(self):
        pattern_id, sha = self.pattern.pattern_id, self.editor.sha
        controller = self.editor.app.controller

        def done(result):
            self.origins = {
                f"{s.name} · sec. {s.sequence} · ID {s.stop_id}": s for s in result.data
            }
            self.fill(self.origin_menu, self.origins, "Sin orígenes habilitados")
            selected = next(
                (
                    label
                    for label, s in self.origins.items()
                    if s.stop_id == self.origin and s.sequence == self.pattern.origin_sequence
                ),
                None,
            )
            if selected:
                self.origin_menu.set(selected)

        self.editor.run(
            f"{self.token}-origins",
            lambda: controller.pattern_origins(pattern_id, sha),
            done,
        )

    def select_pattern_origin(self, label):
        if label not in self.origins:
            return
        stop = self.origins[label]
        self.origin = stop.stop_id
        self.pending_origin = False
        self.pattern = replace(
            self.pattern, origin_platform_id=stop.stop_id, origin_sequence=stop.sequence
        )
        self.origin_label.configure(text=f"{stop.name} · ID {stop.stop_id} · sec. {stop.sequence}")
        if self.destination and self.destination["destination_sequence"] <= stop.sequence:
            self.reset("destination")
        self.editor.changed(self.index)
        self.query("destinations", self.show_destinations, pattern=self.pattern)

    def presentation(self):
        return {
            "uid": self.token,
            "mode": self.mode,
            "search_text": self.search.get(),
            "route_search": self.route_search.get(),
            "pending_origin": "1" if self.pending_origin else "0",
            "origin_choice_label": self.origin_menu.get(),
            "origin_label": self.origin_label.cget("text"),
            "route_label": self.route_menu.get(),
            "pattern_label": self.pattern_menu.get(),
            "destination_label": self.destination_menu.get(),
        }

    def snapshot(self):
        return {
            "values": self.values(),
            "ui": self.presentation(),
            "routes": dict(self.routes),
            "patterns": dict(self.patterns),
            "destinations": dict(self.destinations),
            "origins": dict(self.origins),
        }

    def restore_options(self, snapshot):
        for key in ("routes", "patterns", "destinations", "origins"):
            setattr(self, key, snapshot[key])
        for name, values in (
            ("route", self.routes),
            ("pattern", self.patterns),
            ("destination", self.destinations),
            ("origin", self.origins),
        ):
            if values:
                getattr(self, name + "_menu").configure(values=list(values), state="normal")

    def reset(self, stage="route"):
        order = ("route", "pattern", "destination")
        for name in order[order.index(stage) :]:
            setattr(self, name, None)
            getattr(self, name + "_menu").configure(values=["Seleccione…"], state="disabled")
            getattr(self, name + "_menu").set("Seleccione…")
        for key in ("routes", "patterns", "destinations", "origins"):
            self.editor.app.worker.invalidate(self.editor.token + f"-{self.token}-{key}")

    def search_changed(self, _event=None):
        self.pending_origin = True
        self.editor.changed(self.index)
        self.origin_label.configure(text="Seleccione un resultado; escribir no confirma el origen")
        if self.timer:
            self.after_cancel(self.timer)
        self.editor.app.worker.invalidate(self.editor.token + f"-{self.token}-search")
        for child in self.matches.winfo_children():
            child.destroy()
        self.matches.configure(height=1)
        query = self.search.get().strip()
        if len(query) >= 2:
            self.timer = self.after(300, lambda: self.find(query))

    def find(self, query):
        self.timer = None
        controller, sha = self.editor.app.controller, self.editor.sha
        self.editor.run(
            f"{self.token}-search",
            lambda: controller.search(query, sha),
            self.show_matches,
        )

    def show_matches(self, result):
        for child in self.matches.winfo_children():
            child.destroy()
        self.matches.configure(height=1)
        for stop in result.data[:8]:
            detail = f"{stop.name} · ID {stop.stop_id}"
            if stop.platform_code:
                detail += f" · plataforma {stop.platform_code}"
            if stop.parent_station:
                detail += f" · estación {stop.parent_station}"
            ctk.CTkButton(
                self.matches,
                text=detail,
                anchor="w",
                fg_color=("#dce7f2", "#203750"),
                text_color=("#17283c", "#edf3fc"),
                command=lambda s=stop: self.select_origin(s),
            ).pack(fill="x", pady=2)
        if not result.data:
            ctk.CTkLabel(
                self.matches, text="Sin resultados. Pruebe otro nombre, código o ID."
            ).pack()
        elif len(result.data) > 8:
            ctk.CTkLabel(
                self.matches, text="Se muestran 8 resultados. Afine por nombre, código o ID."
            ).pack()

    def select_origin(self, stop):
        previous = self.origin
        self.origin = stop.stop_id
        self.pending_origin = False
        self.search.delete(0, "end")
        self.search.insert(0, stop.name)
        self.origin_label.configure(
            text=f"{stop.name} · ID {stop.stop_id} · "
            + (f"plataforma {stop.platform_code}" if stop.platform_code else "nodo publicado")
        )
        for child in self.matches.winfo_children():
            child.destroy()
        self.matches.configure(height=1)
        if previous != stop.stop_id:
            self.reset()
        self.editor.changed(self.index)
        self.fetch_routes()

    def context(self):
        return self.editor.payload(), self.editor.departure()

    def query(self, key, callback, **kwargs):
        if self.mode == "Origen primero" and self.pending_origin:
            self.editor.message(
                "Confirme el origen pulsando un resultado de búsqueda; se conserva la selección anterior."
            )
            return
        if not self.origin and not (self.mode == "Ruta primero" and kwargs.get("route_id")):
            self.editor.message("Seleccione un origen de la lista.")
            return
        origin, sha = (
            self.origin if self.mode == "Origen primero" or key == "destinations" else None,
            self.editor.sha,
        )

        controller = self.editor.app.controller

        def operation():
            return controller.query(origin, sha=sha, **kwargs)

        self.editor.run(f"{self.token}-{key}", operation, callback)

    def fetch_routes(self):
        if self.mode == "Ruta primero":
            self.find_routes(self.route_search.get())
            return
        self.query("routes", self.show_routes)

    def show_routes(self, result):
        self.routes = {
            f"{r.short_name or r.route_id} · {r.long_name} · ID {r.route_id}": r
            for r in result.data
        }
        self.fill(self.route_menu, self.routes, "Sin rutas en esta ventana programada")
        selected = next(
            (label for label, r in self.routes.items() if r.route_id == self.route), None
        )
        if selected:
            self.route_menu.set(selected)

    @staticmethod
    def fill(menu, mapping, empty):
        menu.configure(values=list(mapping) or [empty], state="normal" if mapping else "disabled")
        menu.set("Seleccione…" if mapping else empty)

    def choose_route(self, label):
        if label not in self.routes:
            return
        if self.route != self.routes[label].route_id:
            self.reset("pattern")
            if self.mode == "Ruta primero":
                self.origin = None
        self.route = self.routes[label].route_id
        self.editor.changed(self.index)
        self.query("patterns", self.show_patterns, route_id=self.route)

    def show_patterns(self, result):
        self.patterns = {}
        for item, endpoint in result.data:
            direction = (
                "sentido no publicado"
                if item.direction_id is None
                else f"sentido {item.direction_id}"
            )
            label = f"Hacia {endpoint} · {direction} · plataforma {item.origin_platform_id} · sec. {item.origin_sequence} · {item.pattern_id[:10]}"
            self.patterns[label] = item
        self.fill(self.pattern_menu, self.patterns, "Sin patrones activos")
        if self.pattern:
            selected = next(
                (
                    label
                    for label, p in self.patterns.items()
                    if p.pattern_id == self.pattern.pattern_id
                    and p.origin_sequence == self.pattern.origin_sequence
                ),
                None,
            )
            if selected:
                self.pattern_menu.set(selected)

    def choose_pattern(self, label):
        if label not in self.patterns:
            return
        if (
            not self.pattern
            or self.pattern.pattern_id != self.patterns[label].pattern_id
            or self.pattern.origin_sequence != self.patterns[label].origin_sequence
        ):
            self.reset("destination")
        previous = self.pattern
        self.pattern = self.patterns[label]
        self.editor.changed(self.index)
        if self.mode == "Ruta primero":
            if previous and previous.pattern_id == self.pattern.pattern_id and self.origin:
                self.pattern = replace(
                    self.pattern,
                    origin_platform_id=previous.origin_platform_id,
                    origin_sequence=previous.origin_sequence,
                )
            else:
                self.origin = None
                self.origin_label.configure(text="Seleccione una ocurrencia de origen en el patrón")
            self.load_pattern_origins()
            return
        self.query("destinations", self.show_destinations, pattern=self.pattern)

    def show_destinations(self, result):
        self.destinations = {
            f"{d.name} · sec. {d.sequence} · ID {d.stop_id}": d for d in result.data
        }
        self.fill(self.destination_menu, self.destinations, "Sin destinos posteriores habilitados")
        if self.destination:
            selected = next(
                (
                    label
                    for label, d in self.destinations.items()
                    if d.stop_id == self.destination["destination_stop_id"]
                    and d.sequence == self.destination["destination_sequence"]
                ),
                None,
            )
            if selected:
                self.destination_menu.set(selected)

    def choose_destination(self, label):
        if label in self.destinations:
            item = self.destinations[label]
            self.destination = {
                "destination_stop_id": item.stop_id,
                "destination_sequence": item.sequence,
            }
            self.editor.changed(self.index)

    def values(self):
        return {
            "origin_stop_id": self.origin or "",
            "route_id": self.route or "",
            "pattern_id": self.pattern.pattern_id if self.pattern else "",
            "direction_id": self.pattern.direction_id if self.pattern else None,
            "origin_sequence": self.pattern.origin_sequence if self.pattern else 0,
            "destination_stop_id": self.destination["destination_stop_id"]
            if self.destination
            else "",
            "destination_sequence": self.destination["destination_sequence"]
            if self.destination
            else 0,
        }

    def destroy(self):
        for key in ("search", "routes", "patterns", "destinations", "origins"):
            self.editor.app.worker.invalidate(self.editor.token + f"-{self.token}-{key}")
        if self.timer:
            self.after_cancel(self.timer)
        super().destroy()


class ProfileEditor(ctk.CTkScrollableFrame):
    def __init__(self, app, kind, stored=None, labels=None, draft=None, editor_state=None):
        super().__init__(app.content, fg_color="transparent")
        self.app, self.kind = app, kind
        self.token, self.alive = uuid4().hex, True
        self.profile_id = stored.profile.profile_id if stored else kind.value
        self.revision = stored.revision if stored else 0
        self.draft_revision = (
            draft.revision
            if draft
            else app.snapshot.get("draft_revisions", {}).get(self.profile_id, 0)
        )
        if draft:
            self.profile_id = draft.profile_id
            self.revision = draft.base_profile_revision
        self.sha = (
            stored.profile.catalog_sha256
            if stored
            else (app.snapshot["info"] or {}).get("sha256", "")
        )
        self.saved = primitive(stored.profile) if stored else {}
        if draft:
            self.saved = draft.payload["profile"]
            self.sha = self.saved.get("catalog_sha256", self.sha)
        self.dirty = False
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text=PROFILE_TITLES[kind], font=ctk.CTkFont(size=28, weight="bold"), anchor="w"
        ).grid(row=0, column=0, sticky="ew", pady=(8, 0), padx=10)
        subtitle = (
            f"Revisión {self.revision} · catálogo {self.sha[:12] or 'no disponible'} · recorrido habitual"
            + (" · borrador reanudado" if draft else "")
        )
        ctk.CTkLabel(self, text=subtitle, anchor="w").grid(
            row=1, column=0, sticky="ew", padx=10, pady=(0, 12)
        )
        if stored and stored.profile.catalog_sha256 != app.snapshot["active_hash"]:
            ctk.CTkLabel(
                self,
                text="Pendiente de migración. Se conserva y edita la versión original; no se reemplazarán IDs.",
                text_color=("#845100", "#ffd18a"),
                wraplength=650,
            ).grid(row=2, column=0, sticky="ew", padx=10)
        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=3, column=0, sticky="ew", padx=10, pady=8)
        top.grid_columnconfigure((0, 1), weight=1)
        example = app.snapshot["settings"]["example_departures"].get(kind.value)
        when = (
            datetime.fromisoformat(example)
            if example
            else datetime.now(BOGOTA).replace(hour=8, minute=0, second=0, microsecond=0)
        )
        ctk.CTkLabel(
            top,
            text="Configure su recorrido habitual sin fecha ni salida ficticia.\nLas recomendaciones se implementarán en una fase posterior.",
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=12)
        self.initial = entry(
            top, "Caminata inicial · minutos", self.saved.get("initial_walk_minutes", 0), 1
        )
        self.initial.bind("<KeyRelease>", lambda _e: self.mark_dirty())
        advanced = ctk.CTkFrame(self, corner_radius=12)
        self.window = entry(
            advanced,
            "Horizonte de búsqueda de buses programados · minutos ⓘ",
            self.saved.get("departure_window_minutes", 120),
            0,
        )
        Tooltip(
            self.window,
            "Solo limita la búsqueda opcional de horarios publicados. No es tiempo esperado de espera ni una estadística histórica.",
        )
        ctk.CTkLabel(
            advanced,
            text="La espera histórica aún no está disponible. Este ajuste no estima esperas.",
            wraplength=650,
        ).grid(row=1, column=0, padx=12, pady=8)

        def toggle_advanced():
            if advanced.winfo_ismapped():
                advanced.grid_remove()
            else:
                advanced.grid(row=10, column=0, sticky="ew", padx=10, pady=8)

        ctk.CTkButton(self, text="Opciones avanzadas ⓘ", command=toggle_advanced, width=180).grid(
            row=9, column=0, sticky="w", padx=10, pady=8
        )
        self.legs_area = ctk.CTkFrame(self, fg_color="transparent")
        self.legs_area.grid(row=4, column=0, sticky="ew", padx=10)
        self.legs_area.grid_columnconfigure(0, weight=1)
        self.legs, self.transfer_entries = [], []
        self.build_legs(
            self.saved.get("legs", [None]),
            self.saved.get("transfers", []),
            labels,
            presentations=draft.payload["legs_ui"]
            if draft
            else editor_state["legs_ui"]
            if editor_state
            else None,
        )
        self.add_button = ctk.CTkButton(
            self, text="+ Añadir tramo (máximo 3)", command=self.add_leg
        )
        self.add_button.grid(row=5, column=0, sticky="w", padx=10, pady=10)
        bottom = ctk.CTkFrame(self, corner_radius=12)
        bottom.grid(row=6, column=0, sticky="ew", padx=10, pady=8)
        bottom.grid_columnconfigure((0, 1), weight=1)
        self.final = entry(
            bottom, "Caminata final · minutos", self.saved.get("final_walk_minutes", 0), 0
        )
        self.margin = entry(
            bottom,
            "Margen de seguridad · minutos",
            self.saved.get("safety_margin_minutes", 0),
            0,
            1,
        )
        self.deadline = entry(
            bottom,
            "Hora límite de llegada al trabajo (HH:MM)",
            self.saved.get("arrival_deadline", "09:00") or "",
            1,
        )
        self.usual_departure = entry(
            bottom,
            "Salida habitual del trabajo (HH:MM) · opcional",
            self.saved.get("usual_departure") or "",
            1,
        )
        if kind == ProfileKind.TO_WORK:
            self.usual_departure.master.grid_remove()
        else:
            self.deadline.master.grid_remove()
        self.notice = entry(
            bottom,
            "Hora de aviso (HH:MM) · sin envío",
            self.saved.get("notification_time", "07:00"),
            1,
            1,
        )
        self.next_day = ctk.CTkCheckBox(bottom, text="Llegada al día siguiente")
        self.next_day.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=10)
        if self.saved.get("arrival_day_offset"):
            self.next_day.select()
        if kind == ProfileKind.TO_HOME:
            self.next_day.grid_remove()
        weekdays = ctk.CTkFrame(bottom, fg_color="transparent")
        weekdays.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        self.days = []
        for index, name in enumerate(("L", "M", "X", "J", "V", "S", "D")):
            checkbox = ctk.CTkCheckBox(weekdays, text=name, width=48)
            checkbox.grid(row=0, column=index, padx=3)
            if index in self.saved.get("active_weekdays", list(range(7))):
                checkbox.select()
            self.days.append(checkbox)
            checkbox.configure(command=self.mark_dirty)
        self.next_day.configure(command=self.mark_dirty)
        for widget in (self.final, self.margin, self.deadline, self.notice, self.usual_departure):
            widget.bind("<KeyRelease>", lambda _e: self.mark_dirty())
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=7, column=0, sticky="ew", padx=10, pady=12)
        consultation = ctk.CTkFrame(self, corner_radius=12)

        def toggle_consultation():
            if consultation.winfo_ismapped():
                consultation.grid_remove()
            else:
                consultation.grid(row=12, column=0, sticky="ew", padx=10, pady=8)

        ctk.CTkButton(
            self, text="Consultar horario programado · opcional", command=toggle_consultation
        ).grid(row=11, column=0, sticky="w", padx=10, pady=8)
        ctk.CTkLabel(
            consultation,
            text="Solo esta consulta requiere fecha y salida. No afecta al guardado del recorrido.",
        ).grid(row=0, column=0, columnspan=2, padx=10, pady=10)
        example_data = (
            draft.payload["consultation"]
            if draft
            else editor_state["consultation"]
            if editor_state
            else {}
        )
        self.day = entry(
            consultation,
            "Fecha de consulta (AAAA-MM-DD)",
            example_data.get("day", str(when.date()) if example else ""),
            1,
        )
        self.clock = entry(
            consultation,
            "Salida para esta consulta (HH:MM)",
            example_data.get("clock", when.strftime("%H:%M") if example else ""),
            1,
            1,
        )
        self.validate_button = ctk.CTkButton(
            consultation, text="Consultar ejemplo programado", command=lambda: self.commit(False)
        )
        self.validate_button.grid(row=2, column=0, columnspan=2, padx=10, pady=10)
        self.save_button = ctk.CTkButton(
            actions, text="Guardar perfil", command=lambda: self.commit(True)
        )
        self.save_button.pack(side="left")
        self.draft_button = ctk.CTkButton(actions, text="Guardar borrador", command=self.save_draft)
        self.draft_button.pack(side="left", padx=8)
        ctk.CTkButton(
            actions, text="Recargar", width=90, command=lambda: app.open_profile(kind, reload=True)
        ).pack(side="right")
        self.status = ctk.CTkLabel(
            self,
            text="Configure el recorrido. No hay predicciones ni seguimiento en vivo.",
            justify="left",
            anchor="w",
            wraplength=700,
        )
        self.status.grid(row=8, column=0, sticky="ew", padx=14, pady=(4, 30))

    def message(self, text):
        self.status.configure(text=text)

    def mark_dirty(self):
        self.dirty = True

    def run(self, key, operation, callback):
        self.message("Consultando datos locales…")

        def done(value, error):
            if not self.alive:
                return
            if error:
                self.message(error)
            elif not value.ok:
                self.message(result_text(value))
            else:
                self.message(result_text(value) or "Consulta local completada · datos programados")
                callback(value)

        self.app.worker.submit(self.token + "-" + key, operation, done)

    def build_legs(self, saved, transfers, labels=None, snapshots=None, presentations=None):
        for child in self.legs_area.winfo_children():
            child.destroy()
        self.legs, self.transfer_entries = [], []
        for index, leg in enumerate(saved):
            if index:
                frame = ctk.CTkFrame(self.legs_area, corner_radius=10)
                frame.grid(row=index * 2 - 1, column=0, sticky="ew", pady=8)
                frame.grid_columnconfigure((0, 1), weight=1)
                transfer = transfers[index - 1] if index - 1 < len(transfers) else {}
                walk = entry(
                    frame, "Transbordo · caminata (min)", transfer.get("walking_minutes", 0), 0
                )
                buffer = entry(
                    frame, "Transbordo · tolerancia (min)", transfer.get("buffer_minutes", 0), 0, 1
                )
                for widget in (walk, buffer):
                    widget.bind("<KeyRelease>", lambda _e, i=index: self.temporal_changed(i))
                ctk.CTkLabel(
                    frame,
                    text="Conexión espacial no verificada. La proximidad no prueba conectividad.",
                    text_color=("#845100", "#ffd18a"),
                    wraplength=650,
                ).grid(row=1, column=0, columnspan=2, padx=10, pady=5)
                self.transfer_entries.append((walk, buffer))
            ui = (
                snapshots[index]["ui"]
                if snapshots and index < len(snapshots)
                else presentations[index]
                if presentations
                else None
            )
            widget = LegEditor(self, index, leg, labels[index] if labels else None, ui)
            if snapshots and index < len(snapshots):
                widget.restore_options(snapshots[index])
            widget.grid(row=index * 2, column=0, sticky="ew", pady=8)
            self.legs.append(widget)

    def changed(self, index):
        self.dirty = True

    def temporal_changed(self, first=0):
        self.dirty = True
        self.message(
            "Preferencias modificadas. El recorrido se conserva; puede consultar un horario de forma opcional."
        )

    def transfer_values(self):
        return [
            {"walking_minutes": w.get(), "buffer_minutes": b.get()}
            for w, b in self.transfer_entries
        ]

    def add_leg(self):
        if len(self.legs) < 3:
            snapshots = [v.snapshot() for v in self.legs]
            values = [v.values() for v in self.legs]
            self.build_legs(values + [None], self.transfer_values(), snapshots=snapshots)
            self.dirty = True

    def remove_leg(self, index):
        if len(self.legs) == 1:
            self.message("Debe conservar al menos un tramo.")
            return
        values = [v.values() for i, v in enumerate(self.legs) if i != index]
        snapshots = [v.snapshot() for i, v in enumerate(self.legs) if i != index]
        transfers = self.transfer_values()
        del transfers[max(0, index - 1)]
        # Removing an interior leg changes the preceding connection; reselect downstream.
        self.build_legs(values, transfers, snapshots=snapshots)
        self.dirty = True
        self.message(
            "Tramo eliminado. Se conservaron los restantes; revise la caminata de la nueva conexión."
        )

    def payload(self):
        return {
            "profile_id": self.profile_id,
            "kind": self.kind.value,
            "catalog_sha256": self.sha,
            "legs": [v.values() for v in self.legs],
            "transfers": self.transfer_values(),
            "initial_walk_minutes": self.initial.get(),
            "final_walk_minutes": self.final.get(),
            "safety_margin_minutes": self.margin.get(),
            "arrival_day_offset": self.next_day.get(),
            "departure_window_minutes": self.window.get(),
            "arrival_deadline": self.deadline.get() if self.kind == ProfileKind.TO_WORK else None,
            "usual_departure": self.usual_departure.get()
            if self.kind == ProfileKind.TO_HOME
            else None,
            "notification_time": self.notice.get(),
            "active_weekdays": [i for i, v in enumerate(self.days) if v.get()],
        }

    def departure(self):
        return parse_departure(self.day.get(), self.clock.get())

    def commit(self, save):
        if any(leg.pending_origin for leg in self.legs):
            self.message(
                "Confirme los textos de origen con un resultado antes de guardar o consultar; puede guardar un borrador."
            )
            return
        try:
            payload = self.payload()
            departure = self.departure() if not save else None
        except ValueError:
            self.message("Use fecha AAAA-MM-DD y hora HH:MM válidas.")
            return
        self.save_button.configure(state="disabled")
        self.validate_button.configure(state="disabled")
        revision = self.revision
        draft_revision = self.draft_revision
        consultation = {"day": self.day.get(), "clock": self.clock.get()}
        controller, kind = self.app.controller, self.kind.value
        editor_state = self.draft_payload()

        def operation():
            result = (
                controller.save_configuration(payload, revision, draft_revision, editor_state)
                if save
                else controller.validate_example(payload, departure, revision)
            )
            if result.ok and consultation["day"] and consultation["clock"]:
                try:
                    when = parse_departure(consultation["day"], consultation["clock"])
                    controller.remember_example(kind, when)
                except (ValueError, OSError):
                    pass
            state = controller.bootstrap() if save and result.ok else None
            return result, state

        def done(value, error):
            if not self.alive:
                return
            self.save_button.configure(state="normal")
            self.validate_button.configure(state="normal")
            if error:
                self.message(error)
                return
            result, state = value
            if state:
                self.app.snapshot = state
                self.revision = result.data.revision
                self.draft_revision = state["draft_revisions"].get(
                    self.profile_id, self.draft_revision
                )
                try:
                    self.dirty = self.payload() != payload
                except ValueError:
                    self.dirty = True
            if result.ok:
                if save:
                    text = f"Perfil guardado · revisión {self.revision}. Se recuperará al abrir la aplicación."
                    if self.dirty:
                        text += " Hay cambios posteriores que aún no se guardaron."
                else:
                    checks = result.data
                    text = "Perfil válido para el ejemplo programado.\n" + "\n".join(
                        f"Tramo {v.leg_index + 1}: embarque programado {v.boarding_at} · llegada programada {v.scheduled_arrival_at}"
                        for v in checks.legs
                    )
                    text += f"\nCon caminata final y margen: {checks.arrival_with_walk_and_margin}"
                self.message(text + ("\n" + result_text(result) if result.warnings else ""))
            else:
                self.message(result_text(result))

        self.message(
            "Validando y guardando localmente…" if save else "Validando horario programado…"
        )
        self.app.worker.submit(self.token + "-commit", operation, done)

    def draft_payload(self):
        return {
            "profile": self.payload(),
            "legs_ui": [v.presentation() for v in self.legs],
            "consultation": {"day": self.day.get(), "clock": self.clock.get()},
        }

    def save_draft(self):
        payload, revision, base = self.draft_payload(), self.draft_revision, self.revision
        self.draft_button.configure(state="disabled")
        controller = self.app.controller

        def done(result, error):
            if not self.alive:
                return
            self.draft_button.configure(state="normal")
            if error:
                self.message(error)
            elif not result.ok:
                self.message(result_text(result))
            else:
                self.draft_revision = result.data.revision
                self.dirty = self.draft_payload() != payload
                self.message(
                    "Borrador guardado. Puede retomarlo al volver a abrir; aún no acredita un recorrido válido."
                )

        self.app.worker.submit(
            self.token + "-draft",
            lambda: controller.save_draft(payload, revision, base),
            done,
        )

    def destroy(self):
        self.alive = False
        super().destroy()
