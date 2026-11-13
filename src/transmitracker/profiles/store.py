"""Profile database and catalog registry, always separate from GTFS databases."""

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from transmitracker.catalog.common import BOGOTA
from transmitracker.catalog.queries import Catalog
from transmitracker.profiles.contracts import Issue, Result, failure, primitive
from transmitracker.profiles.drafts import StoredDraft, check_draft
from transmitracker.profiles.models import Profile, profile_from_dict
from transmitracker.profiles.services import CatalogService, shape_errors

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS catalog_registry (
 sha256 TEXT PRIMARY KEY, path TEXT NOT NULL, registered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS active_catalog (singleton INTEGER PRIMARY KEY CHECK(singleton=1), sha256 TEXT NOT NULL REFERENCES catalog_registry(sha256));
CREATE TABLE IF NOT EXISTS profiles (
 profile_id TEXT PRIMARY KEY, kind TEXT NOT NULL UNIQUE,
 catalog_sha256 TEXT NOT NULL REFERENCES catalog_registry(sha256), revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_revisions (
 profile_id TEXT NOT NULL REFERENCES profiles(profile_id), revision INTEGER NOT NULL,
 saved_at TEXT NOT NULL, payload_json TEXT NOT NULL, validation_json TEXT NOT NULL,
 PRIMARY KEY(profile_id,revision)
);
CREATE TABLE IF NOT EXISTS catalog_events (
 event_id INTEGER PRIMARY KEY, previous_sha256 TEXT, target_sha256 TEXT NOT NULL,
 changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_drafts (
 profile_id TEXT PRIMARY KEY, kind TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL,
 revision INTEGER NOT NULL, base_profile_revision INTEGER NOT NULL,
 saved_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS profile_schedule_checks (
 profile_id TEXT PRIMARY KEY REFERENCES profiles(profile_id), profile_revision INTEGER NOT NULL,
 checked_at TEXT NOT NULL, departure_at TEXT NOT NULL, result_json TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredProfile:
    profile: Profile
    revision: int
    active_catalog_sha256: str | None
    configuration_state: str = "configured"


@dataclass(frozen=True)
class MigrationPreview:
    candidate: Profile
    source_revision: int
    target_catalog_sha256: str
    validation: dict


class ProfileStore:
    def __init__(self, path: Path):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as existing:
                tables = {
                    r[0]
                    for r in existing.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                version = existing.execute("PRAGMA user_version").fetchone()[0]
                if "catalog_versions" in tables or (
                    tables and ("profiles" not in tables or version not in (1, 2))
                ):
                    raise ValueError(
                        "Refusing to use a catalog or unrelated database as the profile store"
                    )
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.execute("PRAGMA user_version=2")
        self.path = path

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def register_catalog(self, path: Path) -> Result[str]:
        path = Path(path).resolve()
        if path == self.path:
            return failure(
                "DATABASE_SEPARATION_REQUIRED", "catalog", "Catalog and profile store must differ"
            )
        try:
            with Catalog(path) as catalog:
                sha = catalog.info()["sha256"]
            with self.connection:
                existing = self.connection.execute(
                    "SELECT sha256 FROM catalog_registry WHERE path=?", (str(path),)
                ).fetchone()
                if existing and existing[0] != sha:
                    return failure(
                        "CATALOG_PATH_REUSED",
                        "catalog",
                        "A registered catalog path cannot represent a different version",
                    )
                self.connection.execute(
                    "INSERT OR IGNORE INTO catalog_registry VALUES (?,?,?)",
                    (sha, str(path), datetime.now(BOGOTA).isoformat()),
                )
            return Result(data=sha)
        except (sqlite3.Error, OSError, ValueError):
            return failure(
                "CATALOG_UNAVAILABLE", "catalog", "Provide an imported, readable catalog"
            )

    def active_hash(self):
        row = self.connection.execute(
            "SELECT sha256 FROM active_catalog WHERE singleton=1"
        ).fetchone()
        return row[0] if row else None

    def catalog_path(self, sha: str) -> Result[str]:
        """Public registry lookup for consumers; no catalog/profile SQL in GUI code."""
        row = self.connection.execute(
            "SELECT path FROM catalog_registry WHERE sha256=?", (sha,)
        ).fetchone()
        if not row:
            return failure("CATALOG_NOT_REGISTERED", "catalog_sha256", "Catalog is not registered")
        return Result(data=row[0])

    def list_profiles(self) -> Result[tuple[StoredProfile, ...]]:
        ids = [
            r[0] for r in self.connection.execute("SELECT profile_id FROM profiles ORDER BY kind")
        ]
        values, warnings = [], []
        for profile_id in ids:
            loaded = self.load(profile_id)
            if not loaded.ok:
                return Result(errors=loaded.errors, warnings=tuple(warnings))
            values.append(loaded.data)
            warnings.extend(loaded.warnings)
        return Result(data=tuple(values), warnings=tuple(warnings))

    def activate_catalog(self, sha: str, *, changed_at: datetime) -> Result[tuple[str, ...]]:
        row = self.connection.execute(
            "SELECT path FROM catalog_registry WHERE sha256=?", (sha,)
        ).fetchone()
        if not row:
            return failure(
                "CATALOG_NOT_REGISTERED", "catalog_sha256", "Register this version first"
            )
        # Check readability before altering the active pointer; never touch the catalog itself.
        try:
            with Catalog(Path(row[0])) as catalog:
                if catalog.info()["sha256"] != sha:
                    return failure(
                        "CATALOG_VERSION_MISMATCH",
                        "catalog_sha256",
                        "Registered catalog metadata changed",
                    )
        except (sqlite3.Error, OSError, ValueError):
            return failure("CATALOG_UNAVAILABLE", "catalog", "Registered catalog is unavailable")
        if changed_at.tzinfo is None:
            return failure("INVALID_DATETIME", "changed_at", "Timezone is required")
        affected = tuple(
            r[0]
            for r in self.connection.execute(
                "SELECT profile_id FROM profiles WHERE catalog_sha256<>?", (sha,)
            )
        )
        previous = self.active_hash()
        with self.connection:
            self.connection.execute(
                "INSERT INTO active_catalog VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET sha256=excluded.sha256",
                (sha,),
            )
            self.connection.execute(
                "INSERT INTO catalog_events(previous_sha256,target_sha256,changed_at) VALUES (?,?,?)",
                (previous, sha, changed_at.isoformat()),
            )
        warnings = (
            (
                Issue(
                    "PROFILES_PINNED_TO_OLDER_CATALOG",
                    "profiles",
                    "Existing profiles retain their catalog and require explicit migration",
                ),
            )
            if affected
            else ()
        )
        return Result(data=affected, warnings=warnings)

    def load(self, profile_id: str) -> Result[StoredProfile]:
        row = self.connection.execute(
            "SELECT payload_json,revision FROM profiles WHERE profile_id=?", (profile_id,)
        ).fetchone()
        if not row:
            return failure("PROFILE_NOT_FOUND", "profile_id", "Profile does not exist")
        try:
            decoded = profile_from_dict(json.loads(row[0]))
        except (ValueError, TypeError):
            return failure(
                "PROFILE_PAYLOAD_INVALID",
                "profile",
                "Stored profile cannot be decoded; it was not deleted",
            )
        if not decoded.ok:
            return Result(errors=decoded.errors)
        active = self.active_hash()
        warnings = (
            (
                Issue(
                    "PROFILE_CATALOG_NOT_ACTIVE",
                    "catalog_sha256",
                    "Profile remains pinned to its saved version; revalidate before migrating",
                ),
            )
            if active and active != decoded.data.catalog_sha256
            else ()
        )
        check = self.connection.execute(
            "SELECT result_json FROM profile_schedule_checks WHERE profile_id=? AND profile_revision=?",
            (profile_id, row[1]),
        ).fetchone()
        old_validation = self.connection.execute(
            "SELECT validation_json FROM profile_revisions WHERE profile_id=? AND revision=?",
            (profile_id, row[1]),
        ).fetchone()
        validation = (
            json.loads(check[0])
            if check
            else json.loads(old_validation[0])
            if old_validation
            else {}
        )
        basis = (validation.get("data") or {}).get("basis", "")
        state = (
            "schedule_validated"
            if validation.get("ok") and basis == "static_schedule_validation_not_prediction"
            else "configured"
        )
        if active and active != decoded.data.catalog_sha256:
            state = "pending_migration"
        return Result(data=StoredProfile(decoded.data, row[1], active, state), warnings=warnings)

    def validate(self, profile: Profile, departure_at: datetime):
        errors = shape_errors(profile)
        if errors:
            return Result(errors=errors)
        row = self.connection.execute(
            "SELECT path FROM catalog_registry WHERE sha256=?", (profile.catalog_sha256,)
        ).fetchone()
        if not row:
            return failure(
                "CATALOG_NOT_REGISTERED", "catalog_sha256", "Profile's catalog must be registered"
            )
        try:
            with Catalog(Path(row[0])) as catalog:
                return CatalogService(catalog).validate(profile, departure_at)
        except (sqlite3.Error, OSError, ValueError):
            return failure("CATALOG_UNAVAILABLE", "catalog", "Pinned catalog cannot be read")

    def save(
        self, profile: Profile, *, departure_at: datetime, expected_revision: int = 0
    ) -> Result[StoredProfile]:
        validation = self.validate(profile, departure_at)
        if not validation.ok:
            return Result(errors=validation.errors, warnings=validation.warnings)
        return self._persist(profile, validation, expected_revision)

    def validate_structure(self, profile):
        errors = shape_errors(profile)
        if errors:
            return Result(errors=errors)
        registered = self.catalog_path(profile.catalog_sha256)
        if not registered.ok:
            return registered
        try:
            with Catalog(Path(registered.data)) as catalog:
                return CatalogService(catalog).validate_structure(profile)
        except (sqlite3.Error, OSError, ValueError):
            return failure("CATALOG_UNAVAILABLE", "catalog", "Pinned catalog is unavailable")

    def save_configuration(self, profile, *, expected_revision=0):
        validation = self.validate_structure(profile)
        if not validation.ok:
            return Result(errors=validation.errors, warnings=validation.warnings)
        return self._persist(profile, validation, expected_revision)

    def _persist(self, profile, validation, expected_revision):
        try:
            with self.connection:
                self.connection.execute("BEGIN IMMEDIATE")
                row = self.connection.execute(
                    "SELECT revision FROM profiles WHERE profile_id=?", (profile.profile_id,)
                ).fetchone()
                revision = row[0] if row else 0
                if revision != expected_revision:
                    return failure(
                        "PROFILE_REVISION_CONFLICT", "revision", "Reload the profile before saving"
                    )
                revision += 1
                payload = json.dumps(primitive(profile), ensure_ascii=False)
                self.connection.execute(
                    "INSERT INTO profiles VALUES (?,?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET kind=excluded.kind,catalog_sha256=excluded.catalog_sha256,revision=excluded.revision,payload_json=excluded.payload_json",
                    (
                        profile.profile_id,
                        profile.kind.value,
                        profile.catalog_sha256,
                        revision,
                        payload,
                    ),
                )
                self.connection.execute(
                    "INSERT INTO profile_revisions VALUES (?,?,?,?,?)",
                    (
                        profile.profile_id,
                        revision,
                        datetime.now(BOGOTA).isoformat(),
                        payload,
                        json.dumps(validation.to_dict(), ensure_ascii=False),
                    ),
                )
            return Result(
                data=self.load(profile.profile_id).data,
                warnings=validation.warnings,
            )
        except sqlite3.IntegrityError:
            return failure(
                "PROFILE_KIND_EXISTS", "kind", "One profile per commute direction is supported"
            )
        except sqlite3.Error:
            return failure("PROFILE_STORE_UNAVAILABLE", "store", "Profile could not be saved")

    def save_draft(
        self, profile_id, kind, payload, *, expected_revision=0, base_profile_revision=0
    ):
        try:
            check_draft(profile_id, kind, payload, base_profile_revision)
        except (ValueError, TypeError, KeyError):
            return failure("INVALID_DRAFT", "draft", "Invalid draft fields")
        try:
            with self.connection:
                self.connection.execute("BEGIN IMMEDIATE")
                current = self.connection.execute(
                    "SELECT revision FROM profile_drafts WHERE profile_id=?", (profile_id,)
                ).fetchone()
                revision = current[0] if current else 0
                if revision != expected_revision:
                    return failure("DRAFT_REVISION_CONFLICT", "draft", "Reload draft before saving")
                revision += 1
                self.connection.execute(
                    "INSERT INTO profile_drafts VALUES (?,?,?,?,?,?,0) ON CONFLICT(profile_id) DO UPDATE SET payload_json=excluded.payload_json,revision=excluded.revision,base_profile_revision=excluded.base_profile_revision,saved_at=excluded.saved_at,archived=0",
                    (
                        profile_id,
                        kind,
                        json.dumps(payload, ensure_ascii=False),
                        revision,
                        base_profile_revision,
                        datetime.now(BOGOTA).isoformat(),
                    ),
                )
            return Result(
                data=StoredDraft(profile_id, kind, payload, revision, base_profile_revision)
            )
        except sqlite3.Error:
            return failure("DRAFT_STORE_ERROR", "draft", "Could not save draft")

    def list_drafts(self):
        values = []
        for row in self.connection.execute(
            "SELECT * FROM profile_drafts WHERE archived=0 ORDER BY kind"
        ):
            payload = json.loads(row["payload_json"])
            check_draft(row["profile_id"], row["kind"], payload, row["base_profile_revision"])
            values.append(
                StoredDraft(
                    row["profile_id"],
                    row["kind"],
                    payload,
                    row["revision"],
                    row["base_profile_revision"],
                )
            )
        return tuple(values)

    def draft_revisions(self):
        return {
            r[0]: r[1]
            for r in self.connection.execute("SELECT profile_id,revision FROM profile_drafts")
        }

    def editor_states(self):
        rows = self.connection.execute(
            "SELECT d.profile_id,d.payload_json FROM profile_drafts d JOIN profiles p ON p.profile_id=d.profile_id WHERE d.archived=1 AND d.base_profile_revision=p.revision"
        )
        return {r[0]: json.loads(r[1]) for r in rows}

    def archive_draft(self, profile_id, expected_revision):
        with self.connection:
            self.connection.execute(
                "UPDATE profile_drafts SET archived=1 WHERE profile_id=? AND revision=?",
                (profile_id, expected_revision),
            )

    def record_schedule_check(self, profile, revision, departure_at, result):
        with self.connection:
            current = self.load(profile.profile_id)
            if (
                not current.ok
                or current.data.revision != revision
                or current.data.profile != profile
            ):
                return failure(
                    "PROFILE_REVISION_CONFLICT", "revision", "Example does not match stored profile"
                )
            self.connection.execute(
                "INSERT OR REPLACE INTO profile_schedule_checks VALUES (?,?,?,?,?)",
                (
                    profile.profile_id,
                    revision,
                    datetime.now(BOGOTA).isoformat(),
                    departure_at.isoformat(),
                    json.dumps(result.to_dict()),
                ),
            )
        return Result(data=True)

    def preview_migration(
        self, profile_id: str, target_sha: str, *, departure_at: datetime
    ) -> Result[MigrationPreview]:
        loaded = self.load(profile_id)
        if not loaded.ok:
            return Result(errors=loaded.errors)
        candidate = replace(loaded.data.profile, catalog_sha256=target_sha)
        validation = self.validate(candidate, departure_at)
        return Result(
            data=MigrationPreview(
                candidate, loaded.data.revision, target_sha, validation.to_dict()
            ),
            warnings=validation.warnings,
        )

    def apply_migration(
        self, preview: MigrationPreview, *, departure_at: datetime, expected_revision: int
    ):
        # Revalidate at application time; a preview never automatically updates a profile.
        if preview.source_revision != expected_revision:
            return failure(
                "PROFILE_REVISION_CONFLICT", "revision", "Migration preview revision differs"
            )
        if preview.candidate.catalog_sha256 != preview.target_catalog_sha256:
            return failure(
                "INVALID_MIGRATION_PREVIEW",
                "catalog_sha256",
                "Preview target and candidate version differ",
            )
        return self.save(
            preview.candidate, departure_at=departure_at, expected_revision=expected_revision
        )
