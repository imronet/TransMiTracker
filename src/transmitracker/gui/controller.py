"""Widget-independent orchestration over catalog/profile contracts; no SQL or HTTP."""

from dataclasses import replace
from datetime import datetime, time, timedelta
from pathlib import Path

from transmitracker.catalog.common import BOGOTA
from transmitracker.catalog.queries import Catalog
from transmitracker.gui.config import LocalConfig
from transmitracker.profiles.contracts import Issue, Result, failure
from transmitracker.profiles.models import Leg, ProfileKind, profile_from_dict
from transmitracker.profiles.services import CatalogService
from transmitracker.profiles.store import ProfileStore


def parse_departure(day: str, clock: str):
    return datetime.combine(
        datetime.strptime(day, "%Y-%m-%d").date(), datetime.strptime(clock, "%H:%M").time(), BOGOTA
    )


def decode_form(payload: dict):
    """Convert form text; semantic rules remain exclusively in the profile service."""
    try:
        data = dict(payload)
        for name in (
            "initial_walk_minutes",
            "final_walk_minutes",
            "safety_margin_minutes",
            "arrival_day_offset",
            "departure_window_minutes",
        ):
            data[name] = int(data[name])
        data["transfers"] = [
            {k: int(v) for k, v in transfer.items()} for transfer in data["transfers"]
        ]
        return profile_from_dict(data)
    except (ValueError, TypeError, KeyError):
        return failure("INVALID_FORM", "profile", "Revise los minutos y campos obligatorios.")


class DesktopController:
    def __init__(self, root: Path, data_directory="data/gui"):
        self.config = LocalConfig(root, data_directory)
        self.store_path = self.config.local(self.config.directory / "profiles.sqlite3")

    def bootstrap(self):
        settings = self.config.read()
        with ProfileStore(self.store_path) as store:
            registered = store.register_catalog(self.config.local(settings["catalog_path"]))
            if registered.ok and store.active_hash() is None:
                store.activate_catalog(registered.data, changed_at=datetime.now(BOGOTA))
            profiles = store.list_profiles()
            drafts = store.list_drafts()
            draft_revisions = store.draft_revisions()
            editor_states = store.editor_states()
            active = store.active_hash()
        info, error = None, None
        try:
            with Catalog(self.config.local(settings["catalog_path"])) as catalog:
                info = catalog.info()
        except (OSError, ValueError):
            error = "Catálogo no disponible. Seleccione un SQLite importado en Configuración."
        except Exception:
            error = "No se pudo leer el catálogo SQLite. No se modificaron sus datos."
        return {
            "settings": settings,
            "profiles": profiles,
            "drafts": drafts,
            "draft_revisions": draft_revisions,
            "editor_states": editor_states,
            "info": info,
            "catalog_error": error,
            "active_hash": active,
            "catalog_result": registered,
        }

    def _catalog_path(self, sha=None):
        if sha:
            with ProfileStore(self.store_path) as store:
                result = store.catalog_path(sha)
            if not result.ok:
                raise ValueError("Catálogo guardado no disponible")
            return self.config.local(result.data)
        return self.config.local(self.config.read()["catalog_path"])

    def search(self, query, sha=None):
        with Catalog(self._catalog_path(sha)) as catalog:
            return CatalogService(catalog).search_stops(query, limit=25)

    def query(
        self, origin, when=None, *, sha=None, route_id=None, pattern=None, window_minutes=120
    ):
        with Catalog(self._catalog_path(sha)) as catalog:
            service = CatalogService(catalog)
            if when is None:
                if pattern is not None:
                    return service.structural_stops(pattern.pattern_id, pattern.origin_sequence)
                if route_id is not None:
                    patterns = service.structural_patterns(route_id, origin)
                    if not patterns.ok:
                        return patterns
                    choices = []
                    for item in patterns.data:
                        stops = service.structural_stops(item.pattern_id, item.origin_sequence)
                        if not stops.ok:
                            return stops
                        if stops.data:
                            choices.append((item, stops.data[-1].name))
                    return Result(data=tuple(choices))
                return service.structural_routes(origin)
            if pattern is not None:
                leg = Leg(
                    origin,
                    pattern.route_id,
                    pattern.pattern_id,
                    pattern.direction_id,
                    pattern.origin_sequence,
                    "",
                    pattern.origin_sequence + 1,
                )
                return service.destinations(leg, when, window_minutes=window_minutes)
            if route_id is not None:
                result = service.patterns(origin, when, window_minutes=window_minutes)
                if not result.ok:
                    return result
                choices = []
                for item in result.data:
                    if item.route_id != route_id:
                        continue
                    leg = Leg(
                        origin,
                        item.route_id,
                        item.pattern_id,
                        item.direction_id,
                        item.origin_sequence,
                        "",
                        item.origin_sequence + 1,
                    )
                    destinations = service.destinations(leg, when, window_minutes=window_minutes)
                    if not destinations.ok:
                        return destinations
                    if destinations.data:
                        choices.append((item, destinations.data[-1].name))
                return Result(data=tuple(choices))
            return service.routes(origin, when, window_minutes=window_minutes)

    def ready_at(self, payload, departure, leg_index):
        decoded = decode_form(payload)
        if not decoded.ok:
            return decoded
        profile = decoded.data
        if leg_index == 0:
            return Result(data=departure + timedelta(minutes=profile.initial_walk_minutes))
        prefix = replace(
            profile,
            legs=profile.legs[:leg_index],
            transfers=profile.transfers[: leg_index - 1],
            final_walk_minutes=0,
            safety_margin_minutes=0,
            arrival_deadline=time(23, 59, 59),
            arrival_day_offset=1,
        )
        with ProfileStore(self.store_path) as store:
            checked = store.validate(prefix, departure)
        if not checked.ok:
            return checked
        transfer = profile.transfers[leg_index - 1]
        return Result(
            data=datetime.fromisoformat(checked.data.arrival_with_walk_and_margin)
            + timedelta(minutes=transfer.walking_minutes + transfer.buffer_minutes)
        )

    def validate(self, payload, departure):
        decoded = decode_form(payload)
        if not decoded.ok:
            return decoded
        with ProfileStore(self.store_path) as store:
            return store.validate(decoded.data, departure)

    def search_routes(self, query, sha=None):
        with Catalog(self._catalog_path(sha)) as catalog:
            return CatalogService(catalog).search_routes(query)

    def pattern_origins(self, pattern_id, sha=None):
        with Catalog(self._catalog_path(sha)) as catalog:
            return CatalogService(catalog).structural_stops(pattern_id)

    def save_configuration(self, payload, revision, draft_revision=0, editor_state=None):
        decoded = decode_form(payload)
        if not decoded.ok:
            return decoded
        with ProfileStore(self.store_path) as store:
            saved = store.save_configuration(decoded.data, expected_revision=revision)
            if saved.ok:
                if editor_state is not None:
                    cached = store.save_draft(
                        decoded.data.profile_id,
                        decoded.data.kind.value,
                        editor_state,
                        expected_revision=draft_revision,
                        base_profile_revision=saved.data.revision,
                    )
                    if not cached.ok:
                        return Result(data=saved.data, warnings=saved.warnings + cached.errors)
                    draft_revision = cached.data.revision
                store.archive_draft(decoded.data.profile_id, draft_revision)
            return saved

    def save_draft(self, payload, revision, base_profile_revision):
        with ProfileStore(self.store_path) as store:
            return store.save_draft(
                payload["profile"]["profile_id"],
                payload["profile"]["kind"],
                payload,
                expected_revision=revision,
                base_profile_revision=base_profile_revision,
            )

    def validate_example(self, payload, departure, revision=0):
        result = self.validate(payload, departure)
        decoded = decode_form(payload)
        if result.ok and decoded.ok and revision:
            with ProfileStore(self.store_path) as store:
                recorded = store.record_schedule_check(decoded.data, revision, departure, result)
                if not recorded.ok:
                    return Result(data=result.data, warnings=result.warnings + recorded.errors)
        return result

    def remember_example(self, kind, when):
        settings = self.config.read()
        settings["example_departures"][kind] = when.isoformat()
        self.config.write(settings)

    def save(self, payload, departure, revision):
        decoded = decode_form(payload)
        if not decoded.ok:
            return decoded
        with ProfileStore(self.store_path) as store:
            result = store.save(decoded.data, departure_at=departure, expected_revision=revision)
        if result.ok:
            try:
                settings = self.config.read()
                settings["example_departures"][decoded.data.kind.value] = departure.isoformat()
                self.config.write(settings)
            except (OSError, ValueError):
                return Result(
                    data=result.data,
                    warnings=result.warnings
                    + (
                        Issue(
                            "EXAMPLE_PREFERENCE_NOT_SAVED",
                            "example_departures",
                            "Profile was saved but the example date preference could not be written",
                        ),
                    ),
                )
        return result

    def load(self, profile_id):
        with ProfileStore(self.store_path) as store:
            return store.load(profile_id)

    def describe(self, profile):
        """Resolve display labels through services, preserving exact saved selections."""
        rows = []
        with Catalog(self._catalog_path(profile.catalog_sha256)) as catalog:
            service = CatalogService(catalog)
            for leg in profile.legs:
                labels = []
                for stop_id in (leg.origin_stop_id, leg.destination_stop_id):
                    found = service.search_stops(stop_id, limit=100)
                    match = (
                        next((v for v in found.data if v.stop_id == stop_id), None)
                        if found.ok
                        else None
                    )
                    labels.append(match.name if match else stop_id)
                routes = service.search_routes(leg.route_id)
                route = (
                    next((r for r in routes.data if r.route_id == leg.route_id), None)
                    if routes.ok
                    else None
                )
                route_label = (
                    f"{route.short_name} · {route.long_name} · ID {route.route_id}"
                    if route
                    else f"Ruta {leg.route_id} · selección guardada"
                )
                rows.append({"origin": labels[0], "destination": labels[1], "route": route_label})
        return rows

    def save_settings(self, preferences, secrets):
        interval = int(preferences["collection_interval"])
        if interval < 60:
            return failure(
                "INVALID_INTERVAL",
                "collection_interval",
                "Use al menos 60 segundos; no autoriza sondeo.",
            )
        preferences = {**preferences, "collection_interval": interval}
        path = self.config.local(preferences["catalog_path"])
        with ProfileStore(self.store_path) as store:
            registered = store.register_catalog(path)
            if not registered.ok:
                return registered
            previous = self.config.read()
            self.config.write_secrets(secrets)
            self.config.write(preferences)
            try:
                activated = store.activate_catalog(registered.data, changed_at=datetime.now(BOGOTA))
            except Exception:
                self.config.write(previous)
                raise
            if not activated.ok:
                self.config.write(previous)
        return activated


PROFILE_TITLES = {ProfileKind.TO_WORK: "Casa → Trabajo", ProfileKind.TO_HOME: "Trabajo → Casa"}
