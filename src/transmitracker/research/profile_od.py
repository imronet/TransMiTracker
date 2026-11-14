"""Manual profile/leg adapter to the existing offline OD analyzer. No writes to profiles."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from transmitracker.catalog.queries import Catalog
from transmitracker.diagnostics import project_path
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import ProfileKind
from transmitracker.profiles.reader import ProfileReadError, ReadOnlyProfileStore
from transmitracker.reconstruction.models import canonical, digest
from transmitracker.research import od_analyzer as od
from transmitracker.research.local_pilot import pilot_path, write_json

VERSION = "profile-od-adapter-0.1.0"


class ProfileODInputError(ValueError):
    """Safe fixed codes only."""


def _require(result):
    if not result.ok:
        raise ProfileODInputError(result.errors[0].code)
    return result.data


def list_configured(profiles_path, *, profile_id=None, kind=None):
    with ReadOnlyProfileStore(profiles_path) as store:
        if profile_id is not None or kind is not None:
            configured = (_require(store.select(profile_id=profile_id, kind=kind)),)
        else:
            configured = _require(store.list_profiles())
        # Deliberately no personal IDs, stop names or operational IDs on stdout.
        return [
            {
                "kind": s.profile.kind.value,
                "revision": s.revision,
                "configuration_state": s.configuration_state,
                "leg_indices": list(range(1, len(s.profile.legs) + 1)),
            }
            for s in configured
        ]


def run(profiles_path, report_path, catalog_path, *, leg_index, profile_id=None, kind=None):
    with ReadOnlyProfileStore(profiles_path) as store:
        selected = store.select(profile_id=profile_id, kind=kind)
        stored = _require(selected)
        if type(leg_index) is not int or not 1 <= leg_index <= len(stored.profile.legs):
            raise ProfileODInputError("LEG_INDEX_OUT_OF_RANGE")
        leg = stored.profile.legs[leg_index - 1]
        report_bytes = Path(report_path).read_bytes()
        payload = json.loads(report_bytes)
        with Catalog(catalog_path) as catalog:
            sha = catalog.info()["sha256"]
            if stored.profile.catalog_sha256 != sha:
                raise ProfileODInputError("PROFILE_CATALOG_MISMATCH")
            if (payload.get("catalog") or {}).get("sha256") != sha:
                raise ProfileODInputError("REPORT_CATALOG_MISMATCH_OR_NOT_PINNED")
            # Existing profile checks include direction but can allow parent stations.
            # OD requires exact occurrences, so compare the entire resulting Leg.
            try:
                catalog.validate_leg_structure(leg)
                exact = od.select_leg(
                    catalog,
                    leg.route_id,
                    leg.pattern_id,
                    leg.origin_stop_id,
                    leg.destination_stop_id,
                    leg.origin_sequence,
                    leg.destination_sequence,
                )
                if exact != leg:
                    raise ValueError("selection differs")
            except ValueError:
                raise ProfileODInputError("PROFILE_OD_EXACT_LEG_MISMATCH") from None
            analysis = od.analyze(
                payload,
                catalog,
                leg.route_id,
                leg.pattern_id,
                leg.origin_stop_id,
                leg.destination_stop_id,
                origin_sequence=leg.origin_sequence,
                destination_sequence=leg.destination_sequence,
                report_hash=hashlib.sha256(report_bytes).hexdigest(),
            )
        return {
            "adapter": VERSION,
            "adapter_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "profile_store": str(Path(profiles_path).resolve()),
            "profile_store_read_only": True,
            "profile": {
                "profile_id": stored.profile.profile_id,
                "kind": stored.profile.kind.value,
                "revision": stored.revision,
                "configuration_state": stored.configuration_state,
                "catalog_sha256": stored.profile.catalog_sha256,
                "active_catalog_sha256": stored.active_catalog_sha256,
                "payload_sha256": digest(primitive(stored.profile)),
            },
            "profile_warning_codes": [w.code for w in selected.warnings],
            "leg_index": leg_index,
            "leg": primitive(leg),
            "gps_report_path": str(Path(report_path).resolve()),
            "od_algorithm": analysis["algorithm"],
            "analysis": analysis,
            "operationally_validated": False,
            "network_requests": 0,
        }


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Argumentos inválidos o incompletos; consulte --help.\n")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "analyze"):
        command = commands.add_parser(name)
        command.add_argument("--profiles", required=True, help="Existing profile SQLite, read-only")
        selector = command.add_mutually_exclusive_group(required=name == "analyze")
        selector.add_argument("--profile-id")
        selector.add_argument("--profile-kind", choices=[k.value for k in ProfileKind])
        if name == "analyze":
            command.add_argument(
                "--leg", type=int, required=True, help="Explicit 1-based leg index"
            )
            command.add_argument("--report", required=True)
            command.add_argument("--catalog", required=True)
            command.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            print(
                "Perfiles configurados (solo lectura): "
                + canonical(
                    list_configured(
                        project_path(args.profiles),
                        profile_id=args.profile_id,
                        kind=args.profile_kind,
                    )
                )
            )
            return 0
        output = pilot_path(project_path(args.output))
        if output.exists():
            raise ProfileODInputError("OUTPUT_EXISTS")
        result = run(
            project_path(args.profiles),
            project_path(args.report),
            project_path(args.catalog),
            leg_index=args.leg,
            profile_id=args.profile_id,
            kind=args.profile_kind,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, json.loads(canonical(result)))
        print(
            "Análisis de tramo guardado: "
            + canonical(
                {
                    "profile_kind": result["profile"]["kind"],
                    "leg_index": result["leg_index"],
                    "configuration_state": result["profile"]["configuration_state"],
                    **result["analysis"]["summary"],
                    "operationally_validated": False,
                    "network_requests": 0,
                }
            )
        )
        return 0
    except (ProfileReadError, ProfileODInputError) as error:
        parser.exit(2, f"Entrada rechazada [{error}]; no se modificaron perfiles.\n")
    except (ValueError, OSError, KeyError, TypeError, AttributeError, sqlite3.Error):
        parser.exit(
            2,
            "Entradas incompatibles o salida privada inválida; sin adquisición ni cambios a perfiles.\n",
        )


if __name__ == "__main__":
    raise SystemExit(main())
