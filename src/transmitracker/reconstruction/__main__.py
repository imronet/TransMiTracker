"""Explicit offline replay/evaluation. No provider acquisition or background jobs."""

import argparse
import json
import sqlite3
from collections import Counter

from transmitracker.catalog.queries import Catalog
from transmitracker.diagnostics import project_path
from transmitracker.profiles.models import profile_from_dict
from transmitracker.profiles.services import CatalogService
from transmitracker.reconstruction.engine import ReconstructionEngine
from transmitracker.reconstruction.evaluation import evaluate_case
from transmitracker.reconstruction.io import read_saved_capture
from transmitracker.reconstruction.models import Parameters, canonical
from transmitracker.reconstruction.scenarios import build_case, create_catalog, specs
from transmitracker.reconstruction.store import EvidenceStore


def summary(result):
    return {
        "algorithm_version": result.algorithm_version,
        "algorithm_sha256": result.algorithm_sha256,
        "catalog_sha256": result.catalog_sha256,
        "origins": sorted({s.origin for s in result.snapshots}),
        "snapshots": len(result.snapshots),
        "raw_sightings": sum(len(s.observations) for s in result.snapshots),
        "normalized": len(result.normalized),
        "segments": len(result.segments),
        "projected_observations": len(result.projections),
        "events_by_kind": dict(Counter(e.kind.value for e in result.events)),
        "accepted_crossing_events": sum(
            e.accepted and e.kind.value == "estimated_crossing" for e in result.events
        ),
        "measurements": len(result.measurements),
        "accepted_measurements": sum(m.accepted for m in result.measurements),
        "measurement_rejection_reasons": dict(
            Counter(reason for m in result.measurements if not m.accepted for reason in m.reasons)
        ),
        "rejection_reasons": dict(Counter(r.reason for r in result.rejections)),
        "unverified_receipts": sum(s.received_at is None for s in result.snapshots),
        "real_operational_validation": False,
        "network_requests": 0,
    }


def profile_legs(args, catalog):
    if args.profile_json:
        payload = json.loads(project_path(args.profile_json).read_text(encoding="utf-8"))
    elif args.profiles_db:
        if not args.profile_id:
            raise ValueError("A profile ID is required")
        path = project_path(args.profiles_db)
        # Do not instantiate ProfileStore: opening that service can migrate the user's database.
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM profiles WHERE profile_id=?", (args.profile_id,)
            ).fetchone()
        if not row:
            raise ValueError("Unknown profile")
        payload = json.loads(row[0])
    else:
        return ()
    decoded = profile_from_dict(payload)
    if not decoded.ok or not CatalogService(catalog).validate_structure(decoded.data).ok:
        raise ValueError("Structural profile differs from the supplied catalog")
    return decoded.data.legs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    evaluation = commands.add_parser(
        "evaluate", help="Known synthetic truth, explicitly not operational validation"
    )
    evaluation.add_argument("--directory", default="data/phase3a")
    evaluation.add_argument("--output", default="docs/PHASE3A_SYNTHETIC_EVALUATION.json")
    replay = commands.add_parser(
        "replay", help="Saved local snapshots or an explicitly synthetic scenario"
    )
    replay.add_argument("--catalog", required=True)
    source = replay.add_mutually_exclusive_group(required=True)
    source.add_argument("--capture", nargs="+")
    source.add_argument("--scenario", choices=[s["name"] for s in specs()])
    replay.add_argument("--gap", type=int, choices=[20, 40, 90], default=20)
    replay.add_argument("--db", default="data/phase3a/reconstruction.sqlite3")
    replay.add_argument("--output", default="data/phase3a/replay-summary.json")
    profile = replay.add_mutually_exclusive_group()
    profile.add_argument("--profile-json")
    profile.add_argument("--profiles-db")
    replay.add_argument("--profile-id")
    replay.add_argument("--parameters", help="Local JSON containing parameter overrides")
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            directory = project_path(args.directory)
            catalog_path = create_catalog(directory / "fixtures")
            matrix, safety = [], []
            with (
                Catalog(catalog_path) as catalog,
                EvidenceStore(directory / "reconstruction.sqlite3") as store,
            ):
                cases = specs()
                for gap in (20, 40, 90):
                    case = build_case(catalog, cases[0], gap)
                    result = ReconstructionEngine(catalog).run(
                        case.snapshots, legs=case.legs, evidence=case.evidence
                    )
                    metric = evaluate_case(case, result, catalog)
                    matrix.append({"gap_seconds": gap, **metric, **store.save(result)})
                for spec in cases:
                    case = build_case(catalog, spec)
                    result = ReconstructionEngine(catalog).run(
                        case.snapshots, legs=case.legs, evidence=case.evidence
                    )
                    safety.append({**evaluate_case(case, result, catalog), **store.save(result)})
            report = {
                "origin": "synthetic_only_known_truth_no_real_validation",
                "matrix": matrix,
                "scenarios": safety,
                "parameters": Parameters(),
                "algorithm_version": result.algorithm_version,
                "algorithm_sha256": result.algorithm_sha256,
                "real_operational_validation": False,
                "network_requests": 0,
            }
        else:
            parameters = (
                Parameters(**json.loads(project_path(args.parameters).read_text(encoding="utf-8")))
                if args.parameters
                else Parameters()
            )
            with Catalog(project_path(args.catalog)) as catalog:
                legs = profile_legs(args, catalog)
                if args.scenario:
                    case = build_case(
                        catalog, next(s for s in specs() if s["name"] == args.scenario), args.gap
                    )
                    snapshots, evidence = case.snapshots, case.evidence
                    legs = legs or case.legs
                else:
                    snapshots = tuple(
                        read_saved_capture(project_path(path), catalog.info()["sha256"])
                        for path in args.capture
                    )
                    evidence = ()
                result = ReconstructionEngine(catalog, parameters).run(
                    snapshots, legs=legs, evidence=evidence
                )
            with EvidenceStore(project_path(args.db)) as store:
                saved = store.save(result)
            report = {**summary(result), **saved}
        output = project_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(canonical(report) + "\n", encoding="utf-8")
        print(
            canonical(
                {"output": str(output), "network_requests": 0, "real_operational_validation": False}
            )
        )
        return 0
    except (ValueError, TypeError, OSError, sqlite3.Error, KeyError) as error:
        parser.exit(
            2, f"Offline input rejected ({type(error).__name__}); no acquisition was attempted.\n"
        )


if __name__ == "__main__":
    raise SystemExit(main())
