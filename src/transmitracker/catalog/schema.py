"""Catalog schema migration 1. One immutable ZIP version per database file."""

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE catalog_versions (
 sha256 TEXT PRIMARY KEY, source_path TEXT NOT NULL, source_url TEXT,
 imported_at TEXT NOT NULL, zip_bytes INTEGER NOT NULL, batch_size INTEGER NOT NULL,
 counts_json TEXT NOT NULL, timings_json TEXT NOT NULL, schema_version INTEGER NOT NULL
);
CREATE TABLE agencies (agency_id TEXT, name TEXT NOT NULL, timezone TEXT NOT NULL);
CREATE TABLE services (service_id TEXT PRIMARY KEY) WITHOUT ROWID;
CREATE TABLE routes (
 route_id TEXT PRIMARY KEY, agency_id TEXT, short_name TEXT NOT NULL,
 long_name TEXT NOT NULL, route_type INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE stops (
 stop_id TEXT PRIMARY KEY, code TEXT, name TEXT NOT NULL, latitude REAL, longitude REAL,
 location_type INTEGER NOT NULL, parent_station TEXT REFERENCES stops(stop_id), platform_code TEXT
) WITHOUT ROWID;
CREATE TABLE shapes (shape_id TEXT PRIMARY KEY) WITHOUT ROWID;
CREATE TABLE shape_points (
 shape_id TEXT NOT NULL REFERENCES shapes(shape_id), sequence INTEGER NOT NULL CHECK(sequence>=0),
 latitude REAL NOT NULL, longitude REAL NOT NULL, distance REAL,
 PRIMARY KEY(shape_id,sequence)
) WITHOUT ROWID;
CREATE TABLE patterns (
 pattern_id TEXT PRIMARY KEY, route_id TEXT NOT NULL REFERENCES routes(route_id),
 direction_id INTEGER, shape_id TEXT REFERENCES shapes(shape_id), stop_count INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE trips (
 trip_pk INTEGER PRIMARY KEY, trip_id TEXT NOT NULL UNIQUE,
 route_id TEXT NOT NULL REFERENCES routes(route_id), service_id TEXT NOT NULL REFERENCES services(service_id),
 headsign TEXT, direction_id INTEGER CHECK(direction_id IN (0,1)),
 shape_id TEXT REFERENCES shapes(shape_id), pattern_id TEXT REFERENCES patterns(pattern_id),
 first_departure INTEGER, max_seconds INTEGER
);
CREATE TABLE stop_times (
 trip_pk INTEGER NOT NULL REFERENCES trips(trip_pk), sequence INTEGER NOT NULL CHECK(sequence>=0),
 stop_id TEXT NOT NULL REFERENCES stops(stop_id), arrival INTEGER, departure INTEGER,
 pickup_type INTEGER NOT NULL CHECK(pickup_type BETWEEN 0 AND 3),
 drop_off_type INTEGER NOT NULL CHECK(drop_off_type BETWEEN 0 AND 3),
 timepoint INTEGER, shape_distance REAL,
 PRIMARY KEY(trip_pk,sequence)
) WITHOUT ROWID;
CREATE TABLE pattern_stops (
 pattern_id TEXT NOT NULL REFERENCES patterns(pattern_id), sequence INTEGER NOT NULL,
 stop_id TEXT NOT NULL REFERENCES stops(stop_id), pickup_type INTEGER NOT NULL,
 drop_off_type INTEGER NOT NULL, PRIMARY KEY(pattern_id,sequence)
) WITHOUT ROWID;
CREATE TABLE calendar (
 service_id TEXT PRIMARY KEY REFERENCES services(service_id),
 monday INTEGER NOT NULL, tuesday INTEGER NOT NULL, wednesday INTEGER NOT NULL,
 thursday INTEGER NOT NULL, friday INTEGER NOT NULL, saturday INTEGER NOT NULL, sunday INTEGER NOT NULL,
 start_date TEXT NOT NULL, end_date TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE calendar_dates (
 service_id TEXT NOT NULL REFERENCES services(service_id), date TEXT NOT NULL,
 exception_type INTEGER NOT NULL CHECK(exception_type IN (1,2)), PRIMARY KEY(service_id,date)
) WITHOUT ROWID;
CREATE TABLE frequencies (
 trip_pk INTEGER NOT NULL REFERENCES trips(trip_pk), start INTEGER NOT NULL, end INTEGER NOT NULL,
 headway INTEGER NOT NULL CHECK(headway>0), exact_times INTEGER NOT NULL CHECK(exact_times IN (0,1)),
 PRIMARY KEY(trip_pk,start)
) WITHOUT ROWID;
CREATE TABLE feed_info (row_json TEXT NOT NULL);
"""

INDEXES = """
CREATE INDEX idx_stops_parent ON stops(parent_station);
CREATE INDEX idx_stops_code ON stops(code);
CREATE INDEX idx_stop_times_stop_departure ON stop_times(stop_id,departure,trip_pk,sequence);
CREATE INDEX idx_trips_route_pattern_service ON trips(route_id,pattern_id,service_id);
CREATE INDEX idx_trips_service ON trips(service_id);
CREATE INDEX idx_trips_pattern ON trips(pattern_id);
CREATE INDEX idx_pattern_stops_stop ON pattern_stops(stop_id,pattern_id,sequence);
CREATE INDEX idx_patterns_route_direction ON patterns(route_id,direction_id);
CREATE VIRTUAL TABLE stop_search USING fts5(stop_id UNINDEXED,name,code,tokenize='unicode61 remove_diacritics 2');
INSERT INTO stop_search SELECT stop_id,name,COALESCE(code,'') FROM stops;
"""
