"""Offline reproducible example against the real catalog, in a separate GUI workspace."""

import json
from datetime import datetime, time
from pathlib import Path
from time import perf_counter

from transmitracker.catalog.common import file_hash
from transmitracker.gui.controller import DesktopController
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import Leg, Profile, ProfileKind

ROOT = Path(__file__).resolve().parents[1]


def main():
    controller = DesktopController(ROOT, "data/phase2/demo")
    state = controller.bootstrap()
    if not state["info"]:
        raise ValueError("Se requiere el catálogo real importado en Fase 1A")
    catalog = controller.config.local(state["settings"]["catalog_path"])
    previous = file_hash(catalog)
    when = datetime.fromisoformat("2026-11-12T08:00:00-05:00")
    started = perf_counter()
    origins = controller.search("Portal Norte")
    elapsed = perf_counter() - started
    # These exact original IDs are looked up, not inferred from names/suffixes.
    origin = next(v for v in controller.search("74389").data if v.stop_id == "74389")
    routes = controller.query(origin.stop_id, when)
    route = next(v for v in routes.data if v.route_id == "13766")
    choices = controller.query(origin.stop_id, when, route_id=route.route_id)
    pattern = next(p for p, end in choices.data if p.origin_sequence == 2)
    destinations = controller.query(origin.stop_id, when, pattern=pattern)
    destination = next(v for v in destinations.data if v.stop_id == "56059" and v.sequence == 3)
    profile = Profile(
        "phase2-technical-example",
        ProfileKind.TO_WORK,
        state["info"]["sha256"],
        (
            Leg(
                origin.stop_id,
                route.route_id,
                pattern.pattern_id,
                pattern.direction_id,
                pattern.origin_sequence,
                destination.stop_id,
                destination.sequence,
            ),
        ),
        (),
        2,
        5,
        time(9),
        time(7, 30),
        tuple(range(7)),
        3,
    )
    loaded = controller.load(profile.profile_id)
    revision = loaded.data.revision if loaded.ok else 0
    result = controller.save(primitive(profile), when, revision)
    if not result.ok:
        raise ValueError("Falló la validación del ejemplo estático real")
    reopened = DesktopController(ROOT, "data/phase2/demo")
    recovered = reopened.load(profile.profile_id)
    assert recovered.ok and recovered.data.profile == profile
    assert file_hash(catalog) == previous
    report = {
        "mode": "offline_real_static_catalog_not_live_tracking",
        "network_requests": 0,
        "personal_commute_claimed": False,
        "portal_norte_results": primitive(origins.data),
        "portal_norte_search_seconds": elapsed,
        "selected_origin": primitive(origin),
        "selected_route": primitive(route),
        "selected_pattern": primitive(pattern),
        "selected_destination": primitive(destination),
        "saved_revision": result.data.revision,
        "reload_matches": recovered.data.profile == profile,
        "catalog_unchanged": True,
        "programmed_example": reopened.validate(primitive(profile), when).to_dict(),
        "workspace": "data/phase2/demo",
    }
    (ROOT / "docs/PHASE2_REAL_CATALOG_DEMO.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        "Ejemplo técnico guardado en espacio separado. Perfil recuperado y catálogo sin cambios. HTTP: 0."
    )


if __name__ == "__main__":
    main()
