"""Separate SQLite evidence store; deterministic run keys allow reproducible reprocessing."""

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from transmitracker.reconstruction.models import (
    OriginalObservation,
    ProviderSnapshot,
    canonical,
    digest,
)

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS engine_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS batches(batch_id TEXT PRIMARY KEY,manifest_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(snapshot_id TEXT PRIMARY KEY,source TEXT NOT NULL,endpoint TEXT,payload_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL,origin TEXT NOT NULL,feed_as_of REAL,received_at REAL,metadata_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS originals(observation_id TEXT PRIMARY KEY,source TEXT NOT NULL,vehicle_id TEXT,reported_at REAL,representation_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sightings(snapshot_id TEXT NOT NULL REFERENCES snapshots,ordinal INTEGER NOT NULL,observation_id TEXT NOT NULL REFERENCES originals,PRIMARY KEY(snapshot_id,ordinal));
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES batches,catalog_sha256 TEXT NOT NULL,algorithm_version TEXT NOT NULL,parameters_json TEXT NOT NULL,targets_json TEXT NOT NULL,evidence_json TEXT NOT NULL,warnings_json TEXT NOT NULL,processed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS normalized(run_id TEXT NOT NULL REFERENCES runs,normalized_id TEXT NOT NULL,observation_id TEXT NOT NULL REFERENCES originals,snapshot_id TEXT NOT NULL REFERENCES snapshots,accepted INTEGER NOT NULL,data_json TEXT NOT NULL,PRIMARY KEY(run_id,normalized_id));
CREATE TABLE IF NOT EXISTS segments(run_id TEXT NOT NULL REFERENCES runs,segment_id TEXT NOT NULL,identity_id TEXT NOT NULL,pattern_id TEXT NOT NULL,started_at REAL NOT NULL,ended_at REAL NOT NULL,data_json TEXT NOT NULL,PRIMARY KEY(run_id,segment_id));
CREATE TABLE IF NOT EXISTS projections(run_id TEXT NOT NULL REFERENCES runs,normalized_id TEXT NOT NULL,pattern_id TEXT NOT NULL,data_json TEXT NOT NULL,PRIMARY KEY(run_id,normalized_id,pattern_id));
CREATE TABLE IF NOT EXISTS events(run_id TEXT NOT NULL REFERENCES runs,event_id TEXT NOT NULL,segment_id TEXT NOT NULL,pattern_id TEXT NOT NULL,stop_id TEXT NOT NULL,sequence INTEGER NOT NULL,accepted INTEGER NOT NULL,data_json TEXT NOT NULL,PRIMARY KEY(run_id,event_id),FOREIGN KEY(run_id,segment_id) REFERENCES segments(run_id,segment_id));
CREATE TABLE IF NOT EXISTS measurements(run_id TEXT NOT NULL REFERENCES runs,measurement_id TEXT NOT NULL,segment_id TEXT NOT NULL,pattern_id TEXT NOT NULL,origin_sequence INTEGER NOT NULL,destination_sequence INTEGER NOT NULL,accepted INTEGER NOT NULL,data_json TEXT NOT NULL,PRIMARY KEY(run_id,measurement_id));
CREATE TABLE IF NOT EXISTS rejections(run_id TEXT NOT NULL REFERENCES runs,subject_id TEXT NOT NULL,stage TEXT NOT NULL,reason TEXT NOT NULL,evidence_json TEXT NOT NULL,PRIMARY KEY(run_id,subject_id,stage,reason));
CREATE INDEX IF NOT EXISTS idx_original_vehicle_time ON originals(source,vehicle_id,reported_at);
CREATE INDEX IF NOT EXISTS idx_snapshot_provider_time ON snapshots(source,received_at,feed_as_of);
CREATE INDEX IF NOT EXISTS idx_run_version ON runs(catalog_sha256,algorithm_version);
CREATE INDEX IF NOT EXISTS idx_segment_identity_time ON segments(identity_id,started_at,ended_at);
CREATE INDEX IF NOT EXISTS idx_event_occurrence ON events(pattern_id,stop_id,sequence,accepted);
CREATE INDEX IF NOT EXISTS idx_measurement_target ON measurements(pattern_id,origin_sequence,destination_sequence,accepted);
CREATE INDEX IF NOT EXISTS idx_rejection_reason ON rejections(reason,run_id);
"""


class EvidenceStore:
    def __init__(self, path):
        path = Path(path).resolve()
        new_store = True
        if path.exists():
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as check:
                tables = {
                    r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                version = check.execute("PRAGMA user_version").fetchone()[0]
                if tables and ("engine_migrations" not in tables or version != 1):
                    raise ValueError("Refusing to modify a catalog, profile or unrelated database")
                new_store = not tables
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        if new_store:
            self.connection.executescript(SCHEMA)
            with self.connection:
                self.connection.execute(
                    "INSERT OR IGNORE INTO engine_migrations VALUES(1,?)",
                    (datetime.now(timezone.utc).isoformat(),),
                )
                self.connection.execute("PRAGMA user_version=1")
        else:
            self.connection.execute("PRAGMA foreign_keys=ON")

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def save(self, result):
        manifest = tuple(s.snapshot_id for s in result.snapshots)
        batch_id = digest(manifest)
        run_id = digest(
            (
                batch_id,
                result.catalog_sha256,
                result.algorithm_version,
                result.algorithm_sha256,
                result.parameters,
                result.targets,
                result.evidence,
            )
        )
        if self.connection.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
            return {"run_id": run_id, "reused": True}
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO batches VALUES(?,?)", (batch_id, canonical(manifest))
            )
            for snapshot in result.snapshots:
                metadata = asdict(snapshot)
                metadata.pop("observations")
                self.connection.execute(
                    "INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        snapshot.snapshot_id,
                        snapshot.source,
                        snapshot.endpoint,
                        snapshot.payload_sha256,
                        snapshot.catalog_sha256,
                        snapshot.origin,
                        snapshot.feed_as_of,
                        snapshot.received_at,
                        canonical(metadata),
                    ),
                )
                for ordinal, observation in enumerate(snapshot.observations):
                    self.connection.execute(
                        "INSERT OR IGNORE INTO originals VALUES(?,?,?,?,?)",
                        (
                            observation.observation_id,
                            observation.source,
                            observation.vehicle_id,
                            observation.reported_at,
                            canonical(observation),
                        ),
                    )
                    self.connection.execute(
                        "INSERT OR IGNORE INTO sightings VALUES(?,?,?)",
                        (snapshot.snapshot_id, ordinal, observation.observation_id),
                    )
            self.connection.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    batch_id,
                    result.catalog_sha256,
                    result.algorithm_version,
                    canonical(
                        {
                            "thresholds": result.parameters,
                            "algorithm_sha256": result.algorithm_sha256,
                        }
                    ),
                    canonical(result.targets),
                    canonical(result.evidence),
                    canonical(result.input_order_warnings),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.connection.executemany(
                "INSERT INTO normalized VALUES(?,?,?,?,?,?)",
                (
                    (
                        run_id,
                        r.normalized_id,
                        r.observation_id,
                        r.snapshot_id,
                        r.accepted,
                        canonical(r),
                    )
                    for r in result.normalized
                ),
            )
            self.connection.executemany(
                "INSERT INTO segments VALUES(?,?,?,?,?,?,?)",
                (
                    (
                        run_id,
                        s.segment_id,
                        s.identity.identity_id,
                        s.pattern_id,
                        s.started_at,
                        s.ended_at,
                        canonical(s),
                    )
                    for s in result.segments
                ),
            )
            self.connection.executemany(
                "INSERT INTO projections VALUES(?,?,?,?)",
                ((run_id, p.normalized_id, p.pattern_id, canonical(p)) for p in result.projections),
            )
            self.connection.executemany(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                (
                    (
                        run_id,
                        e.event_id,
                        e.segment_id,
                        e.pattern_id,
                        e.stop_id,
                        e.sequence,
                        e.accepted,
                        canonical(e),
                    )
                    for e in result.events
                ),
            )
            self.connection.executemany(
                "INSERT INTO measurements VALUES(?,?,?,?,?,?,?,?)",
                (
                    (
                        run_id,
                        m.measurement_id,
                        m.segment_id,
                        m.pattern_id,
                        m.origin_sequence,
                        m.destination_sequence,
                        m.accepted,
                        canonical(m),
                    )
                    for m in result.measurements
                ),
            )
            self.connection.executemany(
                "INSERT OR IGNORE INTO rejections VALUES(?,?,?,?,?)",
                (
                    (run_id, r.subject_id, r.stage, r.reason, canonical(r.evidence_ids))
                    for r in result.rejections
                ),
            )
        return {"run_id": run_id, "reused": False}

    def load_snapshot(self, snapshot_id):
        row = self.connection.execute(
            "SELECT metadata_json FROM snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
        if not row:
            raise ValueError("Unknown snapshot")

        def restore(value):
            return float(value["$nonfinite"]) if set(value) == {"$nonfinite"} else value

        metadata = json.loads(row[0], object_hook=restore)
        originals = self.connection.execute(
            "SELECT o.representation_json FROM sightings s JOIN originals o USING(observation_id) WHERE snapshot_id=? ORDER BY ordinal",
            (snapshot_id,),
        )
        return ProviderSnapshot(
            **metadata,
            observations=tuple(
                OriginalObservation(**json.loads(r[0], object_hook=restore)) for r in originals
            ),
        )
