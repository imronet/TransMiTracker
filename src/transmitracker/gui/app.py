"""CustomTkinter desktop shell. All Tk calls occur on the main thread."""

import gc
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from uuid import uuid4

import customtkinter as ctk

from transmitracker.gui.config import SECRET_KEYS
from transmitracker.gui.controller import PROFILE_TITLES, DesktopController
from transmitracker.gui.editor import ProfileEditor, entry
from transmitracker.gui.help import Tooltip, help_link
from transmitracker.gui.messages import result_text
from transmitracker.gui.worker import UiWorker
from transmitracker.profiles.models import ProfileKind
from transmitracker.version import app_version

BG = ("#f0f4f9", "#101927")
PANEL = ("#ffffff", "#19263a")
MUTED = ("#526174", "#9eafc4")
TEAL = ("#007b72", "#36d5ba")


class TransMiTrackerApp(ctk.CTk):
    def __init__(self, root: Path, data_directory="data/gui"):
        # Reclaim destroyed Tk cycles on the owning thread before creating another interpreter.
        gc.collect()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title(f"TransMiTracker {app_version()} · Recorridos habituales")
        scale = self._get_window_scaling()
        width = min(1180, int(self.winfo_screenwidth() / scale) - 80)
        height = min(820, int(self.winfo_screenheight() / scale) - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(min(900, width), min(650, height))
        self.configure(fg_color=BG)
        self.controller = DesktopController(root, data_directory)
        self.worker = UiWorker()
        self.snapshot = None
        self.page = None
        self.closed = False
        self.view_token = uuid4().hex
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=PANEL)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        ctk.CTkLabel(
            self.sidebar, text="TM", font=ctk.CTkFont(size=38, weight="bold"), text_color=TEAL
        ).pack(anchor="w", padx=24, pady=(28, 0))
        ctk.CTkLabel(
            self.sidebar, text="TransMiTracker", font=ctk.CTkFont(size=21, weight="bold")
        ).pack(anchor="w", padx=24)
        ctk.CTkLabel(self.sidebar, text="Tus recorridos, organizados", text_color=MUTED).pack(
            anchor="w", padx=24, pady=(3, 28)
        )
        self.nav = {}
        for title, command in (
            ("Dashboard", self.dashboard),
            ("Casa → Trabajo", lambda: self.open_profile(ProfileKind.TO_WORK)),
            ("Trabajo → Casa", lambda: self.open_profile(ProfileKind.TO_HOME)),
            ("Configuración", self.settings_page),
            ("Diagnóstico del sistema", self.diagnostics),
        ):
            button = ctk.CTkButton(
                self.sidebar,
                text=title,
                anchor="w",
                height=42,
                fg_color="transparent",
                text_color=("#243a52", "#dbe8f8"),
                hover_color=("#dce7f2", "#253c56"),
                command=command,
            )
            button.pack(fill="x", padx=12, pady=4)
            self.nav[title] = button
        ctk.CTkLabel(
            self.sidebar,
            text=f"CATÁLOGO LOCAL\nSin seguimiento en vivo\nv{app_version()} · Fase 2.1",
            justify="left",
            text_color=MUTED,
        ).pack(side="bottom", anchor="w", padx=24, pady=25)
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=24, pady=18)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.last_content_width = None
        self.content.bind("<Configure>", self.resize_content)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.page = self.new_page("Dashboard", check_dirty=False)
        self.label(self.page, "Cargando catálogo y perfiles locales…", size=22)
        self.worker.submit("bootstrap", self.controller.bootstrap, self.booted)
        self.poll_id = self.after(40, self.poll)

    def poll(self):
        if not self.closed:
            self.worker.drain()
            self.poll_id = self.after(40, self.poll)

    def booted(self, value, error):
        if error:
            self.clear_page()
            page = self.new_page("Diagnóstico del sistema", check_dirty=False)
            self.label(page, "No se pudo abrir la configuración local", size=24)
            self.label(
                page,
                error + "\nRevise data/gui/settings.json y el almacén de perfiles; no se borraron.",
            )
            return
        self.snapshot = value
        ctk.set_appearance_mode("light" if value["settings"]["theme"] == "Claro" else "dark")
        self.dashboard()

    def clear_page(self):
        self.view_token = uuid4().hex
        if self.page:
            self.page.destroy()
        self.page = None

    def resize_content(self, event):
        if event.width != self.last_content_width:
            self.last_content_width = event.width
            self.fit_text()

    def fit_text(self):
        if self.closed or not self.page:
            return
        width = max(220, int(self.content.winfo_width() / self.content._get_widget_scaling()) - 80)

        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    child.configure(wraplength=width)
                visit(child)

        visit(self.page)

    def can_leave(self):
        if isinstance(self.page, ProfileEditor) and self.page.dirty:
            return messagebox.askyesno(
                "Cambios sin guardar",
                "Hay cambios sin guardar. ¿Desea descartarlos y continuar?",
                parent=self,
            )
        return True

    def new_page(self, title, check_dirty=True):
        if check_dirty and not self.can_leave():
            return None
        self.clear_page()
        for name, button in self.nav.items():
            button.configure(fg_color=("#dce7f2", "#253c56") if name == title else "transparent")
        self.page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        self.page.grid(row=0, column=0, sticky="nsew")
        self.page.grid_columnconfigure(0, weight=1)
        self.after_idle(self.fit_text)
        return self.page

    @staticmethod
    def label(parent, text, size=14, color=None):
        widget = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=size, weight="bold" if size > 18 else "normal"),
            anchor="w",
            justify="left",
            wraplength=720,
            text_color=color or ("#17283c", "#edf3fc"),
        )
        widget.pack(fill="x", padx=18, pady=8)
        return widget

    @staticmethod
    def card(parent):
        frame = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=12)
        frame.pack(fill="x", padx=4, pady=9)
        return frame

    def dashboard(self):
        if not self.snapshot:
            return
        page = self.new_page("Dashboard")
        if page is None:
            return
        controller = self.controller
        self.label(page, "Tus recorridos habituales", size=30)
        self.label(
            page,
            f"TransMiTracker {app_version()} · Configura hoy; las recomendaciones llegarán en una fase posterior.",
            color=MUTED,
        )
        strip = self.card(page)
        self.label(
            strip,
            "PROGRAMADOS · Catálogo local   |   HISTÓRICOS · Sin estimaciones   |   EN VIVO · Deshabilitado",
            color=TEAL,
        )
        catalog = self.card(page)
        info = self.snapshot["info"]
        self.label(catalog, "Catálogo GTFS local" if info else "Catálogo no disponible", size=21)
        if info:
            counts = info["counts"]
            self.label(
                catalog,
                f"{counts.get('routes', 0):,} rutas · {counts.get('stops', 0):,} nodos · {counts.get('patterns', 0):,} patrones".replace(
                    ",", "."
                ),
                size=18,
            )
            self.label(
                catalog,
                f"Versión SHA-256: {info['sha256'][:20]}…\nImportado: {info.get('imported_at', 'no publicado')}\nProcedencia: {info.get('source_url', 'archivo local')}",
                color=MUTED,
            )
            self.label(
                catalog,
                "La fecha de importación no garantiza vigencia de todos los servicios. La selección se valida para su fecha de ejemplo.",
            )
            if not self.snapshot["catalog_result"].ok:
                self.label(catalog, result_text(self.snapshot["catalog_result"]))
        else:
            self.label(catalog, self.snapshot["catalog_error"])
        catalog.pack_forget()
        profiles = self.snapshot["profiles"]
        if not profiles.ok:
            self.label(page, result_text(profiles))
        for kind in ProfileKind:
            block = self.card(page)
            self.label(block, PROFILE_TITLES[kind], size=21)
            saved = (
                next((v for v in profiles.data if v.profile.kind == kind), None)
                if profiles.ok
                else None
            )
            draft = next((v for v in self.snapshot.get("drafts", ()) if v.kind == kind.value), None)
            states = {
                "configured": "Configurado · sin consulta horaria",
                "schedule_validated": "Horario de ejemplo validado",
                "pending_migration": "Pendiente de migración",
            }
            self.label(
                block,
                "BORRADOR INCOMPLETO · Reanudar edición"
                if draft
                else states.get(saved.configuration_state, "Configurado")
                if saved
                else "SIN CONFIGURAR",
                color=("#805700", "#ffd18a") if draft else TEAL,
                size=16,
            )
            if saved:
                self.label(
                    block,
                    f"Configurado · {len(saved.profile.legs)} tramo(s) · revisión {saved.revision}",
                )
                clock = (
                    saved.profile.arrival_deadline
                    if kind == ProfileKind.TO_WORK
                    else saved.profile.usual_departure
                )
                timing = (
                    f"Llegar al trabajo antes de {clock.strftime('%H:%M')}"
                    if kind == ProfileKind.TO_WORK and clock
                    else f"Salida habitual del trabajo: {clock.strftime('%H:%M')}"
                    if clock
                    else "Salida opcional sin configurar · sin hora absoluta de llegada"
                )
                self.label(
                    block,
                    timing
                    + "\nDías: "
                    + ", ".join(
                        ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")[d]
                        for d in saved.profile.active_weekdays
                    ),
                    color=MUTED,
                )
                summary = self.label(
                    block, "Resolviendo nombres del recorrido guardado…", color=MUTED
                )
                summary_view = self.view_token

                def described(value, error, target=summary, view=summary_view):
                    if view != self.view_token or self.closed:
                        return
                    target.configure(
                        text=error
                        or "\n".join(
                            f"{row['origin']} → {row['destination']}\n{row['route']}"
                            for row in value
                        )
                    )
                    self.fit_text()

                self.worker.submit(
                    "describe-" + kind.value,
                    lambda p=saved.profile: controller.describe(p),
                    described,
                )
                pinned = saved.profile.catalog_sha256 != self.snapshot["active_hash"]
                self.label(
                    block,
                    "Pendiente de migración de catálogo"
                    if pinned
                    else "Integridad estructural configurada. La consulta de un horario es opcional.",
                    color=MUTED,
                )
                when = self.snapshot["settings"]["example_departures"].get(kind.value)
                if when and saved.configuration_state == "schedule_validated":
                    output = self.label(block, "Cargando ejemplo programado…", color=MUTED)
                    token = self.view_token

                    def done(value, error, target=output, view=token):
                        if view != self.view_token or self.closed:
                            return
                        if error:
                            target.configure(text=error)
                        elif value.ok:
                            target.configure(
                                text="Ejemplo programado · "
                                + "\n".join(
                                    f"Tramo {v.leg_index + 1}: {datetime.fromisoformat(v.boarding_at).strftime('%d/%m/%Y %H:%M:%S')} → {datetime.fromisoformat(v.scheduled_arrival_at).strftime('%H:%M:%S')} (programado)"
                                    for v in value.data.legs
                                )
                                + "\n"
                                + result_text(value)
                            )
                        else:
                            target.configure(
                                text="Sin horario validado para esta consulta; el recorrido sigue guardado:\n"
                                + result_text(value)
                            )

                    from transmitracker.profiles.contracts import primitive

                    profile_payload = primitive(saved.profile)
                    self.worker.submit(
                        "dashboard-" + kind.value,
                        lambda p=profile_payload, w=when: controller.validate(
                            p, datetime.fromisoformat(w)
                        ),
                        done,
                    )
            else:
                self.label(
                    block,
                    "Hay un borrador guardado. Puede retomarlo sin perder los campos incompletos."
                    if draft
                    else "Defina de uno a tres tramos, por origen o por ruta. No necesita fecha ni salida ficticia.",
                    color=MUTED,
                )
            ctk.CTkButton(
                block, text="Configurar recorrido", command=lambda k=kind: self.open_profile(k)
            ).pack(anchor="w", padx=18, pady=(2, 18))
        catalog.pack(fill="x", padx=4, pady=9)
        live = self.card(page)
        self.label(live, "Servicios en vivo · pendientes", size=21)
        self.label(
            live,
            "Realtime pendiente de validación de identidad. Sin consultas al abrir la app.\nCroma, Telegram, recolección y predicción no están activados.",
            color=MUTED,
        )

    def open_profile(self, kind, reload=False):
        if not self.snapshot or not self.can_leave():
            return
        page = self.new_page(PROFILE_TITLES[kind], check_dirty=False)
        self.label(page, "Cargando perfil y catálogo de referencia…", size=22)
        token = self.view_token
        controller = self.controller

        def operation():
            state = controller.bootstrap()
            values = state["profiles"]
            stored = (
                next((v for v in values.data if v.profile.kind == kind), None)
                if values.ok
                else None
            )
            try:
                labels = controller.describe(stored.profile) if stored else None
            except Exception:
                labels = None
            draft = next((v for v in state.get("drafts", ()) if v.kind == kind.value), None)
            return state, stored, labels, draft

        def done(value, error):
            if token != self.view_token or self.closed:
                return
            if error:
                self.label(page, error)
                return
            self.snapshot, stored, labels, draft = value
            self.clear_page()
            self.page = ProfileEditor(
                self,
                kind,
                stored,
                labels if not draft else None,
                draft,
                self.snapshot.get("editor_states", {}).get(stored.profile.profile_id)
                if stored
                else None,
            )
            self.page.grid(row=0, column=0, sticky="nsew")
            self.after_idle(self.fit_text)

        self.worker.submit("open-profile", operation, done)

    def settings_page(self):
        if not self.snapshot:
            return
        page = self.new_page("Configuración")
        if page is None:
            return
        self.label(page, "Configuración", size=28)
        self.label(
            page, "Preferencias locales · ninguna integración se inicia al guardar", color=MUTED
        )
        panel = self.card(page)
        settings = self.snapshot["settings"]
        self.label(panel, "Apariencia y catálogo", size=20)
        self.label(
            panel,
            "El catálogo GTFS contiene rutas, paraderos, patrones y horarios publicados. No informa dónde está un bus ni predice llegadas.",
            color=MUTED,
        )
        help_link(
            panel,
            "Ayuda: entender el catálogo GTFS ↗",
            "https://gtfs.org/documentation/schedule/reference/",
        )
        theme = ctk.CTkOptionMenu(
            panel,
            values=["Oscuro", "Claro"],
            command=lambda value: ctk.set_appearance_mode("dark" if value == "Oscuro" else "light"),
        )
        theme.set(settings["theme"])
        theme.pack(anchor="w", padx=18, pady=8)
        fields = ctk.CTkFrame(panel, fg_color="transparent")
        fields.pack(fill="x", padx=8, pady=8)
        fields.grid_columnconfigure(0, weight=1)
        path = entry(
            fields,
            "Catálogo SQLite · ruta dentro del proyecto",
            settings["catalog_path"],
            0,
            width=600,
        )
        interval = entry(
            fields,
            "Intervalo futuro · segundos (solo preferencia, sin sondeo)",
            settings["collection_interval"],
            1,
        )
        interval.configure(state="disabled")
        Tooltip(
            interval,
            "Preferencia heredada para una fase futura. No hay colector ni cadencia autorizada; no se ejecutan consultas.",
        )
        notifications = ctk.CTkCheckBox(
            panel, text="Preferencia futura de avisos · no programa notificaciones"
        )
        notifications.pack(anchor="w", padx=18, pady=12)
        if settings["notifications_enabled"]:
            notifications.select()
        notifications.configure(state="disabled")
        self.label(
            panel,
            "Recolección y avisos automáticos deshabilitados. Los intervalos no son estimaciones de espera ni estadísticas de viaje.",
            color=MUTED,
        )
        secrets_panel = self.card(page)
        self.label(secrets_panel, "Credenciales para fases futuras", size=20)
        self.label(
            secrets_panel,
            "Se guardan solo en .env, excluido de Git. El archivo NO está cifrado.\nCroma y Telegram permanecen inactivos.",
            color=MUTED,
        )
        secret_fields = ctk.CTkFrame(secrets_panel, fg_color="transparent")
        secret_fields.pack(fill="x", padx=8, pady=8)
        secret_fields.grid_columnconfigure(0, weight=1)
        widgets = {}
        for row, (key, title) in enumerate(
            zip(
                SECRET_KEYS,
                ("API key de Croma", "Token de Telegram", "Chat ID de Telegram"),
                strict=True,
            )
        ):
            widgets[key] = entry(secret_fields, title, "", row, width=500)
            widgets[key].configure(show="•")
            explanation = (
                "Clave para autenticar una futura integración con Croma. No se consulta ni se consumen créditos."
                if key == "CROMA_API_KEY"
                else "Token que identifica al bot de Telegram. No se envían mensajes."
                if key == "TELEGRAM_BOT_TOKEN"
                else "Identificador del chat de destino de Telegram. No es el nombre del usuario; no se usa todavía."
            )
            Tooltip(widgets[key], explanation)
        self.label(
            secrets_panel,
            "Croma: la API key autentica una integración futura. Telegram: el token identifica al bot y el Chat ID al chat de destino. Ninguna integración está operativa.",
            color=MUTED,
        )
        help_link(
            secrets_panel,
            "Ayuda: bots y tokens de Telegram ↗",
            "https://core.telegram.org/bots/features#botfather",
        )
        storage = self.card(page)
        self.label(storage, "Sus datos permanecen en este proyecto", size=20)
        self.label(
            storage,
            "Perfiles, revisiones y borradores: profiles.sqlite3 de su espacio local. Tema y preferencias: settings.json. Credenciales: .env en la raíz, sin cifrado. El catálogo se abre en modo de lectura.",
            color=MUTED,
        )
        status = self.label(
            page, "Cargando credenciales locales en campos enmascarados…", color=MUTED
        )
        token = self.view_token
        loaded = {"ok": False}
        controller = self.controller

        def secrets_loaded(value, error):
            if token != self.view_token or self.closed:
                return
            if error:
                status.configure(text=error + " No se sobrescribieron credenciales.")
                return
            for key, widget in widgets.items():
                widget.insert(0, value[key])
            loaded["ok"] = True
            status.configure(
                text="Listo. Activar otro catálogo conservará los perfiles en su versión original."
            )

        self.worker.submit("read-secrets", self.controller.config.read_secrets, secrets_loaded)

        def save():
            if not loaded["ok"]:
                return
            preferences = {
                **settings,
                "theme": theme.get(),
                "catalog_path": path.get().strip(),
                "collection_interval": interval.get(),
                "notifications_enabled": bool(notifications.get()),
            }
            secrets = {key: widget.get() for key, widget in widgets.items()}
            button.configure(state="disabled")

            def operation():
                result = controller.save_settings(preferences, secrets)
                return result, controller.bootstrap() if result.ok else None

            def done(value, error):
                if token != self.view_token or self.closed:
                    return
                button.configure(state="normal")
                if error:
                    status.configure(text=error)
                else:
                    result, state = value
                    if state:
                        self.snapshot = state
                    status.configure(
                        text=(
                            "Configuración guardada. Integraciones inactivas.\n"
                            if result.ok
                            else ""
                        )
                        + result_text(result)
                    )

            self.worker.submit("save-settings", operation, done)

        button = ctk.CTkButton(page, text="Guardar configuración", command=save)
        button.pack(anchor="w", padx=18, pady=12)

    def diagnostics(self):
        if not self.snapshot:
            return
        page = self.new_page("Diagnóstico del sistema")
        if page is None:
            return
        self.label(page, "Diagnóstico del sistema", size=28)
        for title, body in (
            (
                "Catálogo",
                "Cargado en modo de lectura"
                if self.snapshot["info"]
                else self.snapshot["catalog_error"],
            ),
            (
                "Datos",
                "Programación GTFS estática. No son predicciones ni horas reales de llegada.",
            ),
            (
                "Realtime",
                "Seguimiento pendiente de validación. No hay colector ni consultas HTTP al navegar.",
            ),
            (
                "Credenciales",
                "Campos enmascarados; .env local sin cifrado. No se incluyen valores en diagnóstico.",
            ),
            (
                "Perfiles",
                "Guardado estructural sin fecha. Borradores separados y consulta horaria opcional. Cambios de catálogo no migran perfiles automáticamente.",
            ),
        ):
            card = self.card(page)
            self.label(card, title, size=20)
            self.label(card, body, color=MUTED)
        profiles = self.snapshot["profiles"]
        if profiles.ok:
            for saved in profiles.data:
                self.label(
                    page,
                    f"{PROFILE_TITLES[saved.profile.kind]} · revisión {saved.revision} · "
                    + (
                        "pendiente de migración"
                        if saved.profile.catalog_sha256 != self.snapshot["active_hash"]
                        else "catálogo asociado"
                    ),
                )
        self.label(page, result_text(profiles))
        ctk.CTkButton(page, text="Actualizar diagnóstico local", command=self.refresh).pack(
            anchor="w", padx=18, pady=10
        )

    def refresh(self):
        self.worker.submit("bootstrap", self.controller.bootstrap, self.booted)

    def close(self):
        if not self.can_leave():
            return
        self.closed = True
        self.after_cancel(self.poll_id)
        self.worker.close()
        self.destroy()
