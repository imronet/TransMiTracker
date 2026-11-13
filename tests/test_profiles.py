import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, time

import pytest
from test_catalog import make_catalog_tables, write_zip

from transmitracker.catalog.common import file_hash, gtfs_seconds
from transmitracker.catalog.importer import import_catalog
from transmitracker.catalog.queries import Catalog
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import Leg, Profile, ProfileKind, Transfer, profile_from_dict
from transmitracker.profiles.services import CatalogService
from transmitracker.profiles.store import ProfileStore

WHEN = datetime.fromisoformat("2026-11-09T07:45:00-05:00")


@pytest.fixture(scope="module")
def profile_catalogs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("profiles_catalogs")
    tables = make_catalog_tables()
    for index in (1, 2):
        tables["trips.txt"][1].append(["MAIN_LATE" + str(index), "001", "WK", 0, "SH1"])
        for row in list(tables["stop_times.txt"][1]):
            if row[0] == "MAIN":
                copy = list(row)
                copy[0] = "MAIN_LATE" + str(index)
                for pos in (3, 4):
                    seconds = gtfs_seconds(copy[pos]) + 1800 * index
                    copy[pos] = f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
                tables["stop_times.txt"][1].append(copy)
    paths = []
    for version in range(3):
        data = deepcopy(tables)
        if version:
            data["routes.txt"][1][0][2] += f" v{version}"
        if version == 2:
            data["stop_times.txt"][1][:] = [
                r
                for r in data["stop_times.txt"][1]
                if r[0] not in {"MAIN", "MAIN_LATE1", "MAIN_LATE2"}
            ]
            data["trips.txt"][1][:] = [
                r for r in data["trips.txt"][1] if r[0] not in {"MAIN", "MAIN_LATE1", "MAIN_LATE2"}
            ]
        zip_path = write_zip(directory / f"v{version}.zip", data)
        path = directory / f"v{version}.sqlite3"
        import_catalog(zip_path, path)
        paths.append(path)
    return paths


@pytest.fixture
def profile(profile_catalogs):
    with Catalog(profile_catalogs[0]) as catalog:
        pattern = catalog.connection.execute(
            "SELECT pattern_id FROM trips WHERE trip_id='MAIN'"
        ).fetchone()[0]
        return Profile(
            "commute",
            ProfileKind.TO_WORK,
            catalog.info()["sha256"],
            (Leg("0006", "001", pattern, 0, 10, "0004", 40),),
            (),
            0,
            3,
            time(10),
            time(7, 30),
            (0, 1, 2, 3, 4),
            2,
        )


@pytest.fixture
def store(tmp_path, profile_catalogs):
    with ProfileStore(tmp_path / "profiles.sqlite3") as store:
        for path in profile_catalogs:
            assert store.register_catalog(path).ok
        yield store


def test_typed_gui_contracts(profile_catalogs, profile):
    with Catalog(profile_catalogs[0]) as catalog:
        service = CatalogService(catalog)
        stops = service.search_stops("plataforma a")
        assert stops.ok and stops.data[0].stop_id == "0001"
        assert service.routes("0001", WHEN).ok
        patterns = service.patterns("0001", WHEN)
        assert patterns.ok and patterns.data[0].pattern_id
        assert service.destinations(profile.legs[0], WHEN).ok
        result = service.validate(profile, WHEN)
        assert result.ok and result.data.basis.endswith("not_prediction")
        assert result.data.legs[0].scheduled_arrival_at == "2026-11-09T08:20:00-05:00"
        assert result.data.arrival_with_walk_and_margin == "2026-11-09T08:25:00-05:00"
        assert result.to_dict()["contract_version"] == 1
        json.dumps(result.to_dict())
        assert not service.search_stops(None).ok
        assert service.routes("UNKNOWN", WHEN).errors[0].code == "CATALOG_SELECTION_INVALID"


@pytest.mark.parametrize("count", [1, 2, 3])
def test_one_to_three_chained_legs(profile_catalogs, profile, count):
    first = profile.legs[0]
    legs = (
        replace(first, destination_stop_id="0001", destination_sequence=20),
        replace(
            first,
            origin_stop_id="0001",
            origin_sequence=20,
            destination_stop_id="0003",
            destination_sequence=30,
        ),
        replace(first, origin_stop_id="0003", origin_sequence=30),
    )[:count]
    changed = replace(profile, legs=legs, transfers=tuple(Transfer(1, 1) for _ in range(count - 1)))
    with Catalog(profile_catalogs[0]) as catalog:
        result = CatalogService(catalog).validate(changed, WHEN)
        assert result.ok, result.to_dict()
        assert len(result.data.legs) == count
        assert (
            len([w for w in result.warnings if w.code == "TRANSFER_PATH_UNVERIFIED"]) == count - 1
        )
        assert result.data.spatial_connections_verified == (count == 1)
        if count > 1:
            assert result.data.legs[1].ready_at == "2026-11-09T08:02:00-05:00"
            assert changed.transfers[0].walking_minutes == 1


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("legs", (), "LEG_COUNT"),
        ("legs", (None,), "LEG_COUNT"),
        ("transfers", (Transfer(0),), "TRANSFER_COUNT"),
        ("initial_walk_minutes", -1, "INVALID_MINUTES"),
        ("final_walk_minutes", True, "INVALID_MINUTES"),
        ("active_weekdays", (0, 0), "INVALID_WEEKDAYS"),
        ("active_weekdays", (), "INVALID_WEEKDAYS"),
        ("arrival_day_offset", 2, "INVALID_DAY_OFFSET"),
        ("catalog_sha256", "missing", "INVALID_CATALOG_HASH"),
    ],
)
def test_invalid_models_return_field_codes(profile_catalogs, profile, field, value, code):
    with Catalog(profile_catalogs[0]) as catalog:
        result = CatalogService(catalog).validate(replace(profile, **{field: value}), WHEN)
        assert not result.ok and code in {e.code for e in result.errors}


def test_invalid_leg_service_direction_sequence_and_date(profile_catalogs, profile):
    with Catalog(profile_catalogs[0]) as catalog:
        service = CatalogService(catalog)
        for leg in (
            replace(profile.legs[0], direction_id=1),
            replace(profile.legs[0], destination_stop_id="0005"),
        ):
            assert (
                service.validate(replace(profile, legs=(leg,)), WHEN).errors[0].code
                == "LEG_SERVICE_INVALID"
            )
        bad = replace(profile.legs[0], destination_sequence=5)
        assert (
            service.validate(replace(profile, legs=(bad,)), WHEN).errors[0].code
            == "INVALID_SEQUENCE"
        )
        assert service.validate(profile, datetime(2026, 11, 9)).errors[0].code == "INVALID_DATETIME"
        assert (
            service.validate(profile, WHEN.replace(day=12)).errors[0].code == "LEG_SERVICE_INVALID"
        )
        assert (
            service.validate(replace(profile, active_weekdays=(1,)), WHEN).errors[0].code
            == "PROFILE_INACTIVE_DAY"
        )
        assert (
            service.validate(replace(profile, arrival_deadline=time(8)), WHEN).errors[0].code
            == "ARRIVAL_DEADLINE_EXCEEDED"
        )
        assert any(
            w.code == "NOTICE_AFTER_DEPARTURE"
            for w in service.validate(replace(profile, notification_time=time(9)), WHEN).warnings
        )


def test_no_proximity_assumption_and_user_walk_is_preserved(profile_catalogs, profile):
    leg = profile.legs[0]
    changed = replace(
        profile,
        legs=(
            replace(leg, destination_stop_id="0001", destination_sequence=20),
            replace(leg, origin_stop_id="0001", origin_sequence=20),
        ),
        transfers=(Transfer(20, 2),),
    )
    with Catalog(profile_catalogs[0]) as catalog:
        result = CatalogService(catalog).validate(changed, WHEN)
        assert result.ok
        assert result.data.legs[1].ready_at == "2026-11-09T08:22:00-05:00"
        assert result.data.legs[1].boarding_at == "2026-11-09T08:30:00-05:00"
        assert not result.data.spatial_connections_verified


def test_strict_serialization_rejects_secrets(profile):
    payload = primitive(profile)
    assert profile_from_dict(payload).data == profile
    assert not profile_from_dict({**payload, "telegram_token": "synthetic-placeholder"}).ok
    payload["legs"][0]["api_key"] = "synthetic-placeholder"
    assert not profile_from_dict(payload).ok


def test_persistence_directions_revisions_and_no_catalog_writes(store, profile, profile_catalogs):
    before = file_hash(profile_catalogs[0])
    assert store.activate_catalog(profile.catalog_sha256, changed_at=WHEN).ok
    saved = store.save(profile, departure_at=WHEN)
    assert saved.ok and saved.data.revision == 1
    assert store.load(profile.profile_id).data.profile == profile
    assert store.save(profile, departure_at=WHEN).errors[0].code == "PROFILE_REVISION_CONFLICT"
    assert store.save(profile, departure_at=WHEN, expected_revision=1).data.revision == 2
    returning = replace(profile, profile_id="return", kind=ProfileKind.TO_HOME)
    assert store.save(returning, departure_at=WHEN).ok
    assert (
        store.save(replace(profile, profile_id="third"), departure_at=WHEN).errors[0].code
        == "PROFILE_KIND_EXISTS"
    )
    assert (
        store.connection.execute(
            "SELECT COUNT(*) FROM profile_revisions WHERE profile_id='commute'"
        ).fetchone()[0]
        == 2
    )
    assert file_hash(profile_catalogs[0]) == before


def test_catalog_activation_never_migrates_profiles_silently(store, profile, profile_catalogs):
    assert store.save(profile, departure_at=WHEN).ok
    with Catalog(profile_catalogs[1]) as catalog:
        target = catalog.info()["sha256"]
    activation = store.activate_catalog(target, changed_at=WHEN)
    assert activation.ok and profile.profile_id in activation.data
    loaded = store.load(profile.profile_id)
    assert loaded.data.profile.catalog_sha256 == profile.catalog_sha256
    assert loaded.warnings[0].code == "PROFILE_CATALOG_NOT_ACTIVE"
    preview = store.preview_migration(profile.profile_id, target, departure_at=WHEN)
    assert preview.ok and preview.data.validation["ok"]
    assert store.load(profile.profile_id).data.revision == 1
    applied = store.apply_migration(preview.data, departure_at=WHEN, expected_revision=1)
    assert applied.ok and applied.data.profile.catalog_sha256 == target
    assert (
        store.apply_migration(preview.data, departure_at=WHEN, expected_revision=1).errors[0].code
        == "PROFILE_REVISION_CONFLICT"
    )


def test_removed_pattern_blocks_migration_but_preserves_original(store, profile, profile_catalogs):
    store.save(profile, departure_at=WHEN)
    with Catalog(profile_catalogs[2]) as catalog:
        target = catalog.info()["sha256"]
    preview = store.preview_migration(profile.profile_id, target, departure_at=WHEN)
    assert not preview.data.validation["ok"]
    result = store.apply_migration(preview.data, departure_at=WHEN, expected_revision=1)
    assert not result.ok
    assert store.load(profile.profile_id).data.profile == profile


def test_store_cannot_be_catalog(profile_catalogs):
    before = file_hash(profile_catalogs[0])
    with pytest.raises(ValueError, match="catalog"):
        ProfileStore(profile_catalogs[0])
    assert file_hash(profile_catalogs[0]) == before


def test_missing_profile_and_catalog_contract(store, profile):
    assert store.load("missing").errors[0].code == "PROFILE_NOT_FOUND"
    assert (
        store.activate_catalog("f" * 64, changed_at=WHEN).errors[0].code == "CATALOG_NOT_REGISTERED"
    )
    assert (
        store.save(replace(profile, catalog_sha256="f" * 64), departure_at=WHEN).errors[0].code
        == "CATALOG_NOT_REGISTERED"
    )


@pytest.mark.parametrize(
    "departure,offset,weekdays",
    [
        ("2026-11-14T00:55:00-05:00", 0, (5,)),
        ("2026-11-13T23:55:00-05:00", 1, (4,)),
    ],
)
def test_profile_midnight_and_explicit_next_day(
    profile_catalogs, profile, departure, offset, weekdays
):
    with Catalog(profile_catalogs[0]) as catalog:
        pattern = catalog.connection.execute(
            "SELECT pattern_id FROM trips WHERE trip_id='NIGHT'"
        ).fetchone()[0]
        changed = replace(
            profile,
            legs=(Leg("0001", "001", pattern, 0, 10, "0004", 20),),
            active_weekdays=weekdays,
            arrival_deadline=time(1, 30),
            arrival_day_offset=offset,
        )
        result = CatalogService(catalog).validate(changed, datetime.fromisoformat(departure))
        assert result.ok, result.to_dict()
        assert result.data.legs[0].service_date == "2026-11-13"
        assert result.data.arrival_with_walk_and_margin == "2026-11-14T01:15:00-05:00"


def test_profile_does_not_invent_frequency_times_or_transfer_connections(profile_catalogs, profile):
    with Catalog(profile_catalogs[0]) as catalog:
        pattern = catalog.connection.execute(
            "SELECT pattern_id FROM trips WHERE trip_id='FREQ_APPROX'"
        ).fetchone()[0]
        changed = replace(
            profile,
            legs=(Leg("0001", "008", pattern, 0, 10, "0004", 20),),
            arrival_deadline=time(2),
        )
        result = CatalogService(catalog).validate(changed, WHEN.replace(day=10, hour=0, minute=30))
        assert result.errors[0].code == "SCHEDULE_TIME_UNRESOLVED"
        first = profile.legs[0]
        unreachable = replace(
            profile,
            legs=(
                replace(first, destination_stop_id="0001", destination_sequence=20),
                replace(first, origin_stop_id="0001", origin_sequence=20),
            ),
            transfers=(Transfer(1000),),
        )
        result = CatalogService(catalog).validate(unreachable, WHEN)
        assert result.errors[0].field == "legs.1"
