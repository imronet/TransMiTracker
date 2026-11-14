"""Read-only adapter reusing profile deserialization/state, never store initialization."""

import sqlite3
from pathlib import Path

from transmitracker.profiles.contracts import failure
from transmitracker.profiles.models import ProfileKind
from transmitracker.profiles.services import shape_errors
from transmitracker.profiles.store import ProfileStore


class ProfileReadError(ValueError):
    """Fixed safe diagnostic codes, never private SQLite/payload details."""


class ReadOnlyProfileStore(ProfileStore):
    """All SQL is constrained by mode=ro and query_only, including inherited APIs.

    Do not call ProfileStore.__init__: it creates tables and writes user_version.
    Only current schema 2 is supported; older stores must not be migrated here.
    """

    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ProfileReadError("PROFILE_STORE_MISSING")
        self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA query_only=ON")
            self.connection.execute("BEGIN")
            if self.connection.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise ProfileReadError("PROFILE_SCHEMA_UNSUPPORTED")
            required = {
                "profiles": {"profile_id", "kind", "catalog_sha256", "revision", "payload_json"},
                "active_catalog": {"singleton", "sha256"},
                "profile_revisions": {"profile_id", "revision", "validation_json"},
                "profile_schedule_checks": {"profile_id", "profile_revision", "result_json"},
            }
            for table, columns in required.items():
                actual = {r["name"] for r in self.connection.execute(f"PRAGMA table_info({table})")}
                if not columns <= actual:
                    raise ProfileReadError("PROFILE_SCHEMA_UNSUPPORTED")
        except Exception:
            self.close()
            raise

    def load(self, profile_id):
        try:
            loaded = super().load(profile_id)
            if not loaded.ok:
                return loaded
            stored = loaded.data
            profile = stored.profile
            row = self.connection.execute(
                "SELECT kind,catalog_sha256,revision FROM profiles WHERE profile_id=?",
                (profile_id,),
            ).fetchone()
            if (
                shape_errors(profile)
                or profile.profile_id != profile_id
                or row["kind"] != profile.kind.value
                or row["catalog_sha256"] != profile.catalog_sha256
                or type(stored.revision) is not int
                or stored.revision < 1
            ):
                return failure(
                    "PROFILE_PAYLOAD_INVALID", "profile", "Configured profile is invalid"
                )
            return loaded
        except (ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
            return failure(
                "PROFILE_PAYLOAD_INVALID", "profile", "Configured profile cannot be read"
            )

    def select(self, *, profile_id=None, kind=None):
        if (profile_id is None) == (kind is None):
            return failure("PROFILE_SELECTION_REQUIRED", "profile", "Select one configured profile")
        if kind is not None:
            try:
                kind = ProfileKind(kind)
            except ValueError:
                return failure("PROFILE_SELECTION_INVALID", "kind", "Unknown profile kind")
            row = self.connection.execute(
                "SELECT profile_id FROM profiles WHERE kind=?", (kind.value,)
            ).fetchone()
            if row is None:
                return failure("PROFILE_NOT_FOUND", "profile", "No configured profile found")
            profile_id = row[0]
        return self.load(profile_id)
