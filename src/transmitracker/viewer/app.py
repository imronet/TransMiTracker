"""Independent local Canvas window. No acquisition, animation or inferred fixes."""

import tkinter as tk
from collections import Counter
from datetime import datetime
from tkinter import filedialog, ttk
from zoneinfo import ZoneInfo

import customtkinter as ctk

from transmitracker.version import app_version
from transmitracker.viewer.data import STATES, Transform, ViewerError, load


def clock(value):
    if value is None:
        return "sin timestamp"
    try:
        return datetime.fromtimestamp(value, ZoneInfo("America/Bogota")).isoformat()
    except (ValueError, OverflowError, OSError):
        return "timestamp fuera de rango"


class Viewer(ctk.CTk):
    def __init__(self, scene=None):
        super().__init__()
        self.title(f"TransMiTracker {app_version()} · Visor GPS offline experimental")
        self.geometry("1250x850")
        self.minsize(950, 700)
        self.scene = None
        self.report_path = self.catalog_path = None
        self.candidate_index = None
        self.cursor = 0
        self.segment_index = None
        self.zoom = 1
        self.pan = (0, 0)
        self.fit_route = True
        self.drag_start = None
        self._syncing = False
        toolbar = ctk.CTkFrame(self)
        toolbar.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkButton(toolbar, text="Abrir reporte privado", command=self.open_report).pack(
            side="left", padx=6, pady=8
        )
        ctk.CTkButton(toolbar, text="Catálogo local…", command=self.open_catalog).pack(
            side="left", padx=6
        )
        self.heading = ctk.CTkLabel(
            toolbar, text="Abra un reporte existente; no hay adquisición de datos."
        )
        self.heading.pack(side="left", padx=10)
        self.notice = ctk.CTkLabel(
            self, text="Solo candidatos · sin llegadas, duraciones verificadas ni ETA", anchor="w"
        )
        self.notice.pack(fill="x", padx=18)
        body = ctk.CTkFrame(self)
        body.pack(fill="both", expand=True, padx=12, pady=6)
        side = ctk.CTkFrame(body, width=300)
        side.pack(side="left", fill="y", padx=(0, 8))
        ctk.CTkLabel(side, text="Vehículos candidatos (ID y fuente privados)").pack(pady=4)
        self.vehicles = ttk.Treeview(
            side, columns=("candidate",), show="headings", height=5, selectmode="browse"
        )
        self.vehicles.heading("candidate", text="Candidato")
        self.vehicles.column("candidate", width=285)
        self.vehicles.pack(fill="x", padx=6)
        self.vehicles.bind("<<TreeviewSelect>>", self._vehicle_event)
        ctk.CTkLabel(side, text="Segmentos del reporte").pack(pady=(10, 4))
        self.segments = ttk.Treeview(
            side, columns=("state", "fixes"), show="headings", height=7, selectmode="browse"
        )
        self.segments.heading("state", text="Estado")
        self.segments.heading("fixes", text="GPS")
        self.segments.column("state", width=225)
        self.segments.column("fixes", width=45)
        self.segments.pack(fill="x", padx=6)
        self.segments.bind("<<TreeviewSelect>>", self._segment_event)
        self.details = ctk.CTkTextbox(side, width=295, wrap="word")
        self.details.pack(fill="both", expand=True, padx=6, pady=8)
        plot = ctk.CTkFrame(body)
        plot.pack(side="left", fill="both", expand=True)
        controls = ctk.CTkFrame(plot)
        controls.pack(fill="x")
        ctk.CTkButton(
            controls, text="Ruta completa", width=115, command=lambda: self.fit(True)
        ).pack(side="left", padx=3, pady=4)
        ctk.CTkButton(
            controls, text="Encuadrar GPS", width=115, command=lambda: self.fit(False)
        ).pack(side="left", padx=3)
        ctk.CTkButton(controls, text="−", width=35, command=lambda: self.magnify(0.8)).pack(
            side="left", padx=3
        )
        ctk.CTkButton(controls, text="+", width=35, command=lambda: self.magnify(1.25)).pack(
            side="left", padx=3
        )
        ctk.CTkLabel(controls, text="Arrastre para desplazar").pack(side="left", padx=6)
        self.canvas = tk.Canvas(plot, background="#101c2c", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<MouseWheel>", lambda e: self.magnify(1.25 if e.delta > 0 else 0.8))
        self.canvas.bind("<ButtonPress-1>", lambda e: setattr(self, "drag_start", (e.x, e.y)))
        self.canvas.bind("<B1-Motion>", self.drag)
        legend = " · ".join(label for label, _ in STATES.values())
        ctk.CTkLabel(plot, text=legend, wraplength=800).pack(fill="x", pady=(3, 0))
        colors = ctk.CTkFrame(plot, fg_color="transparent")
        colors.pack(fill="x")
        for label, color in STATES.values():
            ctk.CTkLabel(colors, text="● " + label, text_color=color, font=("Arial", 11)).pack(
                side="left", padx=4
            )
        ctk.CTkLabel(
            plot,
            text="Puntos = GPS observado · Punteadas = uniones visuales, sin muestras intermedias",
            wraplength=800,
        ).pack(fill="x", pady=3)
        timeline = ctk.CTkFrame(self)
        timeline.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(
            timeline, text="Anterior", width=90, command=lambda: self.set_cursor(self.cursor - 1)
        ).pack(side="left", padx=5, pady=8)
        self.slider = ctk.CTkSlider(
            timeline, from_=0, to=1, number_of_steps=1, command=self.set_cursor, state="disabled"
        )
        self.slider.pack(side="left", fill="x", expand=True, padx=6)
        ctk.CTkButton(
            timeline, text="Siguiente", width=90, command=lambda: self.set_cursor(self.cursor + 1)
        ).pack(side="left", padx=5)
        self.time_label = ctk.CTkLabel(timeline, text="Sin observaciones", width=280)
        self.time_label.pack(side="left", padx=6)
        if scene:
            self.set_scene(scene)

    def set_scene(self, scene):
        self.scene = scene
        self.candidate_index = None
        self.segment_index = None
        self.vehicles.delete(*self.vehicles.get_children())
        self.segments.delete(*self.segments.get_children())
        origin = "SINTÉTICO" if scene.synthetic else "PRIVADO · procedencia en reporte"
        self.heading.configure(text=f"Ruta {scene.route} · {origin}")
        self.notice.configure(text=scene.note)
        for index, candidate in enumerate(scene.candidates):
            self.vehicles.insert(
                "", "end", iid=str(index), values=(f"{candidate.vehicle} · {candidate.source}",)
            )
        if scene.candidates:
            self.select_candidate(0)
        else:
            self.slider.configure(state="disabled")
            self.time_label.configure(text="Sin candidatos")
            self._details("El reporte no contiene vehículos candidatos para esta ruta.")
            self.draw()

    def load_file(self, report_path, catalog_path=None):
        scene = load(report_path, catalog_path)
        self.report_path, self.catalog_path = report_path, catalog_path
        self.set_scene(scene)

    def open_report(self):
        path = filedialog.askopenfilename(
            title="Reporte privado del rastreador", filetypes=[("JSON", "*.json")]
        )
        if path:
            try:
                self.load_file(path, self.catalog_path)
            except ViewerError as error:
                self.notice.configure(text=str(error) + " Vista anterior conservada.")

    def open_catalog(self):
        path = filedialog.askopenfilename(
            title="Catálogo SQLite local",
            filetypes=[("SQLite", "*.sqlite3 *.sqlite *.db"), ("Todos", "*.*")],
        )
        if path:
            if self.report_path:
                try:
                    self.load_file(self.report_path, path)
                except ViewerError as error:
                    self.notice.configure(text=str(error) + " Vista anterior conservada.")
            else:
                self.catalog_path = path
                self.notice.configure(
                    text="Catálogo seleccionado; abra un reporte para comprobar su versión."
                )

    def _vehicle_event(self, event=None):
        selection = self.vehicles.selection()
        if selection and int(selection[0]) != self.candidate_index:
            self.select_candidate(int(selection[0]))

    def select_candidate(self, index):
        candidate = self.scene.candidate(index)
        self.candidate_index = index
        self.segment_index = None
        self.zoom, self.pan = 1, (0, 0)
        self.vehicles.selection_set(str(index))
        self.segments.delete(*self.segments.get_children())
        for segment in candidate.segments:
            self.segments.insert(
                "",
                "end",
                iid=str(segment.index),
                values=(f"{segment.index + 1} · {STATES[segment.state][0]}", len(segment.fixes)),
            )
        count = len(candidate.fixes)
        self.slider.configure(
            to=max(1, count - 1),
            number_of_steps=max(1, count - 1),
            state="normal" if count > 1 else "disabled",
        )
        self.set_cursor(0)

    def _segment_event(self, event=None):
        if self._syncing or self.candidate_index is None:
            return
        selection = self.segments.selection()
        if selection:
            if int(selection[0]) == self.segment_index:
                return
            candidate = self.scene.candidate(self.candidate_index)
            segment = next(s for s in candidate.segments if s.index == int(selection[0]))
            self.set_cursor(
                next(i for i, f in enumerate(candidate.fixes) if f.key == segment.fixes[0].key)
            )

    def set_cursor(self, value):
        if self.candidate_index is None:
            return
        candidate = self.scene.candidate(self.candidate_index)
        if not candidate.fixes:
            self.time_label.configure(text="Sin observaciones de la ruta")
            self._details("Sin observaciones para recorrer.")
            self.draw()
            return
        self.cursor = max(0, min(len(candidate.fixes) - 1, round(float(value))))
        self.slider.set(self.cursor)
        fix = candidate.fixes[self.cursor]
        segment = candidate.segment_at(fix)
        self.segment_index = segment.index if segment else None
        self._syncing = True
        if segment:
            self.segments.selection_set(str(segment.index))
            self.segments.see(str(segment.index))
        else:
            self.segments.selection_remove(*self.segments.selection())
        self._syncing = False
        self.time_label.configure(
            text=f"{self.cursor + 1}/{len(candidate.fixes)} · {clock(fix.timestamp)}"
        )
        text = f"Candidato: {candidate.vehicle}\nFuente: {candidate.source}\n\nGPS: {clock(fix.timestamp)}\nRecepción: {clock(fix.received_at)}\nFeed: {clock(fix.feed_as_of)}\nCaptura: {fix.key[0] + 1}\nTipo: {fix.position_kind}\n"
        if not fix.point:
            text += "Sin coordenadas observadas utilizables; no se dibuja un GPS supuesto.\n"
        if segment:
            text += f"\nSegmento {segment.index + 1}: {STATES[segment.state][0]}\nActividad candidata: {segment.activity}\nGPS inicial: {clock(segment.fixes[0].timestamp)}\nGPS final: {clock(segment.fixes[-1].timestamp)}\nCambios: {segment.changes}\nDistancia muestreada: {segment.distance:.1f} m\nProgreso neto: "
            text += (
                "no determinado\n" if segment.progress is None else f"{segment.progress:.1f} m\n"
            )
            text += f"Inicio: {segment.start}\nFinal: {segment.end}\nPatrón ambiguo: {'sí' if segment.pattern_ambiguous else 'no indicado'}\nShapes: {', '.join(segment.shapes) or 'sin selección'}\nPatrones: {', '.join(segment.patterns) or 'sin selección'}\n"
            text += (
                "Alternativas de proyección:\n"
                + ("\n".join(segment.alternatives) or "sin proyección registrada")
                + "\n"
            )
        else:
            text += "\nSin segmento: repetición o incidente; no crea un enlace nuevo.\n"
        text += "\nIncidentes del candidato:\n" + (
            "\n".join(f"{k}: {n}" for k, n in Counter(candidate.incidents).items())
            or "ninguno registrado"
        )
        self._details(text)
        self.draw()

    def _details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def fit(self, route):
        self.fit_route, self.zoom, self.pan = route, 1, (0, 0)
        self.draw()

    def magnify(self, factor):
        self.zoom = max(0.2, min(30, self.zoom * factor))
        self.draw()

    def drag(self, event):
        if self.drag_start:
            self.pan = (
                self.pan[0] + event.x - self.drag_start[0],
                self.pan[1] + event.y - self.drag_start[1],
            )
            self.drag_start = (event.x, event.y)
            self.draw()

    def draw(self):
        self.canvas.delete("all")
        if self.scene is None:
            return
        candidate = (
            self.scene.candidate(self.candidate_index) if self.candidate_index is not None else None
        )
        route_points = [p for s in self.scene.shapes for p in s.points]
        gps_points = [f.point for f in candidate.fixes if f.point] if candidate else []
        points = (route_points + gps_points) if self.fit_route else (gps_points or route_points)
        transform = Transform.fit(points, self.canvas.winfo_width(), self.canvas.winfo_height())

        def project(point):
            return transform.point(point, self.zoom, self.pan)

        for shape in self.scene.shapes:
            coordinates = [v for p in shape.points for v in project(p)]
            self.canvas.create_line(*coordinates, fill="#718198", width=2, tags=("geometry",))
        if not candidate:
            return
        visible = {f.key for f in candidate.fixes[: self.cursor + 1]}
        for segment in candidate.segments:
            color = STATES[segment.state][1]
            for a, b in zip(segment.fixes, segment.fixes[1:], strict=False):
                if a.key in visible and b.key in visible and a.point and b.point:
                    self.canvas.create_line(
                        *project(a.point),
                        *project(b.point),
                        fill=color,
                        width=3,
                        dash=(4, 4),
                        tags=("visual_link",),
                    )
        for fix in candidate.fixes[: self.cursor + 1]:
            if not fix.point:
                continue
            segment = candidate.segment_at(fix)
            color = STATES[segment.state][1] if segment else "#94a3b8"
            x, y = project(fix.point)
            self.canvas.create_oval(
                x - 4, y - 4, x + 4, y + 4, fill=color, outline="#101c2c", tags=("observed",)
            )
        if candidate.fixes:
            current = candidate.fixes[self.cursor]
            if current.point:
                x, y = project(current.point)
                self.canvas.create_oval(
                    x - 9, y - 9, x + 9, y + 9, outline="#ffffff", width=2, tags=("current",)
                )
                self.canvas.create_text(
                    x + 13,
                    y - 13,
                    text=str(self.cursor + 1),
                    fill="#ffffff",
                    anchor="w",
                    tags=("current",),
                )
        self.canvas.create_text(
            12,
            15,
            text=f"{len(self.scene.shapes)} geometrías candidatas · todas conservadas",
            fill="#cbd5e1",
            anchor="w",
        )
