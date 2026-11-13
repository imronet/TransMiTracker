"""Static real-catalog QA, without a fictional departure or any network request."""

import json
from dataclasses import replace
from datetime import time
from pathlib import Path

from transmitracker.catalog.common import file_hash
from transmitracker.gui.controller import DesktopController
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import Leg, Profile, ProfileKind, Transfer
from transmitracker.version import app_version

ROOT = Path(__file__).resolve().parents[1]


def main():
    controller = DesktopController(ROOT, "data/phase2_1/demo")
    snapshot = controller.bootstrap()
    if not snapshot["info"]:
        raise ValueError("Se requiere el catálogo real de Fase 1A")
    catalog = controller.config.local(snapshot["settings"]["catalog_path"])
    digest = file_hash(catalog)
    stations = controller.search("Portal Norte")
    origins = controller.search("74389")
    origin = next(v for v in origins.data if v.stop_id == "74389")
    routes = controller.query(origin.stop_id)
    route = next(r for r in routes.data if r.route_id == "13766")
    patterns = controller.query(origin.stop_id, route_id=route.route_id)
    pattern = next(p for p, end in patterns.data if p.origin_sequence == 2)
    eligible = controller.pattern_origins(pattern.pattern_id)
    legs = []
    for index in range(3):
        destinations = controller.query(pattern.origin_platform_id, pattern=pattern)
        destination = next(
            d
            for d in destinations.data
            if index == 2
            or any(o.stop_id == d.stop_id and o.sequence == d.sequence for o in eligible.data)
        )
        legs.append(
            Leg(
                pattern.origin_platform_id,
                route.route_id,
                pattern.pattern_id,
                pattern.direction_id,
                pattern.origin_sequence,
                destination.stop_id,
                destination.sequence,
            )
        )
        pattern = replace(
            pattern, origin_platform_id=destination.stop_id, origin_sequence=destination.sequence
        )
    profile = Profile(
        "qa-technical-work",
        ProfileKind.TO_WORK,
        snapshot["info"]["sha256"],
        tuple(legs),
        (Transfer(7, 2), Transfer(4, 1)),
        2,
        5,
        time(9),
        time(7, 30),
        tuple(range(5)),
        3,
    )
    profiles = [
        profile,
        replace(
            profile,
            profile_id="qa-technical-home",
            kind=ProfileKind.TO_HOME,
            legs=(legs[0],),
            transfers=(),
            arrival_deadline=None,
            usual_departure=time(17, 30),
        ),
    ]
    saved = []
    for example in profiles:
        previous = controller.load(example.profile_id)
        revision = previous.data.revision if previous.ok else 0
        result = controller.save_configuration(primitive(example), revision)
        assert result.ok, result.to_dict()
        saved.append(result.to_dict())
    reopened = DesktopController(ROOT, "data/phase2_1/demo")
    assert all(reopened.load(p.profile_id).data.profile == p for p in profiles)
    assert not reopened.config.read()["example_departures"]
    assert file_hash(catalog) == digest
    report = {
        "version": app_version(),
        "origin": "offline_real_static_catalog_no_personal_commute_claimed",
        "network_requests": 0,
        "requires_date_or_departure": False,
        "programmed_examples_run": False,
        "catalog_unchanged": True,
        "reopened_profiles_match": True,
        "portal_norte_station_found": any(s.stop_id == "2000" for s in stations.data),
        "profiles": saved,
        "workspace": "data/phase2_1/demo",
    }
    (ROOT / "docs/PHASE2_1_REAL_CATALOG_QA.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        "QA estático real: perfiles de 3 y 1 tramos guardados y recuperados, sin fecha/salida. HTTP: 0. Catálogo sin cambios."
    )


if __name__ == "__main__":
    main()
