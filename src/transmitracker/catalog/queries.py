"""Read-only queries for scheduled boarding choices, not live arrival predictions."""

import json
import math
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path

from transmitracker.catalog import CatalogError
from transmitracker.catalog.common import BOGOTA, aware, normalized
from transmitracker.catalog.schema import SCHEMA_VERSION


class Catalog:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        if self.connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            self.close()
            raise CatalogError("Unsupported catalog schema")

    def close(self):
        self.connection.close()

    def search_routes(self, query, *, limit=25):
        if not isinstance(query, str) or not 1 <= limit <= 1000:
            raise CatalogError("Invalid route search")
        self.connection.create_function("search_normalized", 1, normalized, deterministic=True)
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT route_id,short_name,long_name FROM routes WHERE instr(search_normalized(route_id||' '||short_name||' '||long_name),?)>0 ORDER BY short_name,route_id LIMIT ?",
                (normalized(query.strip()), limit),
            )
        ]

    def structural_routes(self, origin):
        family = self.stop_family(origin)
        marks = ",".join("?" for _ in family)
        return [
            dict(row)
            for row in self.connection.execute(
                f"""
            SELECT DISTINCT r.route_id,r.short_name,r.long_name FROM routes r
            JOIN patterns p ON p.route_id=r.route_id JOIN pattern_stops o ON o.pattern_id=p.pattern_id
            WHERE o.stop_id IN ({marks}) AND o.pickup_type=0
            AND EXISTS (SELECT 1 FROM pattern_stops d WHERE d.pattern_id=p.pattern_id AND d.sequence>o.sequence AND d.drop_off_type=0)
            ORDER BY r.short_name,r.route_id""",
                family,
            )
        ]

    def structural_patterns(self, route_id, origin=None):
        parameters = [route_id]
        if origin is None:
            source = "patterns p"
            extra = ""
            projection = "'' AS origin_platform_id,0 AS origin_sequence"
        else:
            family = self.stop_family(origin)
            parameters.extend(family)
            source = "patterns p JOIN pattern_stops o ON o.pattern_id=p.pattern_id"
            extra = f"AND o.stop_id IN ({','.join('?' for _ in family)}) AND o.pickup_type=0 AND EXISTS (SELECT 1 FROM pattern_stops d WHERE d.pattern_id=p.pattern_id AND d.sequence>o.sequence AND d.drop_off_type=0)"
            projection = "o.stop_id AS origin_platform_id,o.sequence AS origin_sequence"
        rows = self.connection.execute(
            f"SELECT p.route_id,p.direction_id,p.pattern_id,{projection} FROM {source} WHERE p.route_id=? {extra} ORDER BY p.pattern_id,origin_sequence",
            parameters,
        )
        return [
            {
                **dict(row),
                "service_dates": (),
                "next_boarding_at": None,
                "time_basis": "structure_only_no_date",
            }
            for row in rows
        ]

    def structural_stops(self, pattern_id, origin_sequence=None):
        params = [pattern_id]
        if origin_sequence is None:
            clause = "o.pickup_type=0 AND EXISTS (SELECT 1 FROM pattern_stops d WHERE d.pattern_id=o.pattern_id AND d.sequence>o.sequence AND d.drop_off_type=0)"
        else:
            clause = "o.drop_off_type=0 AND o.sequence>?"
            params.append(origin_sequence)
        return [
            dict(row)
            for row in self.connection.execute(
                f"""
            SELECT s.stop_id,s.name,o.sequence,s.parent_station,s.platform_code
            FROM pattern_stops o JOIN stops s ON s.stop_id=o.stop_id
            WHERE o.pattern_id=? AND {clause} ORDER BY o.sequence""",
                params,
            )
        ]

    def validate_leg_structure(self, leg):
        family = self.stop_family(leg.origin_stop_id)
        row = self.connection.execute(
            f"""
            SELECT 1 FROM patterns p JOIN pattern_stops o ON o.pattern_id=p.pattern_id
            JOIN pattern_stops d ON d.pattern_id=p.pattern_id
            WHERE p.pattern_id=? AND p.route_id=? AND p.direction_id IS ?
            AND o.sequence=? AND o.stop_id IN ({",".join("?" for _ in family)}) AND o.pickup_type=0
            AND d.sequence=? AND d.stop_id=? AND d.drop_off_type=0 AND d.sequence>o.sequence
            """,
            (
                leg.pattern_id,
                leg.route_id,
                leg.direction_id,
                leg.origin_sequence,
                *family,
                leg.destination_sequence,
                leg.destination_stop_id,
            ),
        ).fetchone()
        if not row:
            raise CatalogError("Invalid structural leg")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def info(self):
        row = dict(self.connection.execute("SELECT * FROM catalog_versions").fetchone())
        row["counts"] = json.loads(row.pop("counts_json"))
        row["timings"] = json.loads(row.pop("timings_json"))
        row["indexes"] = [
            r[0]
            for r in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
            )
        ]
        return row

    def search_stops(self, query: str, *, limit=20) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise CatalogError("Search limit must be between 1 and 1000")
        tokens = re.findall(r"\w+", normalized(query))
        if not tokens:
            return []
        expression = " AND ".join('"' + word.replace('"', '""') + '"*' for word in tokens)
        return [
            dict(row)
            for row in self.connection.execute(
                """
            WITH matches AS (
                SELECT stop_id FROM stop_search WHERE stop_search MATCH ?
                UNION SELECT stop_id FROM stops WHERE stop_id=?
            )
            SELECT s.*,p.name AS parent_name,
                   (SELECT COUNT(*) FROM stops child WHERE child.parent_station=s.stop_id) AS child_count
            FROM matches JOIN stops s ON s.stop_id=matches.stop_id
            LEFT JOIN stops p ON p.stop_id=s.parent_station
            ORDER BY CASE WHEN s.code=? OR s.stop_id=? THEN 0 ELSE 1 END,
                     s.location_type DESC,s.name,s.stop_id LIMIT ?
        """,
                (expression, query, query, query, limit),
            )
        ]

    def stop_family(self, stop_id: str) -> list[str]:
        if not self.connection.execute(
            "SELECT 1 FROM stops WHERE stop_id=?", (stop_id,)
        ).fetchone():
            raise CatalogError(f"Unknown stop_id: {stop_id}")
        # UNION stops cycles from recurring; never expands siblings of a platform.
        return [
            row[0]
            for row in self.connection.execute(
                """
            WITH RECURSIVE family(stop_id) AS (
              SELECT stop_id FROM stops WHERE stop_id=?
              UNION SELECT s.stop_id FROM stops s JOIN family f ON s.parent_station=f.stop_id
            ) SELECT stop_id FROM family
        """,
                (stop_id,),
            )
        ]

    def active_services(self, service_date: date) -> set[str]:
        weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
            service_date.weekday()
        ]
        day = service_date.strftime("%Y%m%d")
        result = {
            r[0]
            for r in self.connection.execute(
                f"SELECT service_id FROM calendar WHERE {weekday}=1 AND start_date<=? AND end_date>=?",
                (day, day),
            )
        }
        for row in self.connection.execute(
            "SELECT service_id,exception_type FROM calendar_dates WHERE date=?", (day,)
        ):
            if row[1] == 1:
                result.add(row[0])
            else:
                result.discard(row[0])
        return result

    def _service_windows(self, when, end, *, unresolved=False):
        """Existing service-date range, including published GTFS times >24h."""
        max_seconds = self.connection.execute("""SELECT COALESCE(MAX(value),0) FROM (
            SELECT MAX(max_seconds) AS value FROM trips
            UNION ALL SELECT MAX(f.end + t.max_seconds - t.first_departure)
            FROM frequencies f JOIN trips t ON t.trip_pk=f.trip_pk
        )""").fetchone()[0]
        if unresolved:
            # A missing frequency anchor must not hide a published >24h window.
            max_seconds = max(
                max_seconds,
                self.connection.execute("SELECT COALESCE(MAX(end),0) FROM frequencies").fetchone()[
                    0
                ],
            )
        # Supports all >24h times present in this version, rather than assuming one previous day.
        first_day = when.date() - timedelta(days=max_seconds // 86400)
        service_day = first_day
        while service_day <= end.date():
            services = self.active_services(service_day)
            if not services:
                service_day += timedelta(days=1)
                continue
            midnight = datetime.combine(service_day, time(), BOGOTA)
            low, high = (when - midnight).total_seconds(), (end - midnight).total_seconds()
            yield service_day, services, midnight, low, high
            service_day += timedelta(days=1)

    def _candidates(
        self,
        origin: str,
        when: datetime,
        window_minutes: int,
        *,
        route_id=None,
        pattern_id=None,
        include_conditional=False,
        all_departures=False,
    ):
        when = aware(when)
        if not 1 <= window_minutes <= 1440:
            raise CatalogError("Departure window must be between 1 and 1440 minutes")
        stops = self.stop_family(origin)
        end = when + timedelta(minutes=window_minutes)
        for service_day, services, midnight, low, high in self._service_windows(when, end):
            parameters = [*stops, *sorted(services), low, high]
            clause = ""
            if route_id is not None:
                clause += " AND t.route_id=?"
                parameters.append(route_id)
            if pattern_id is not None:
                clause += " AND t.pattern_id=?"
                parameters.append(pattern_id)
            pickup_clause = "o.pickup_type<>1" if include_conditional else "o.pickup_type=0"
            drop_clause = "d.drop_off_type<>1" if include_conditional else "d.drop_off_type=0"
            sql = f"""
              SELECT t.*,o.sequence AS origin_sequence,o.stop_id AS origin_platform_id,
                     o.departure AS origin_departure,o.pickup_type AS boarding_type,
                     r.short_name,r.long_name
              FROM stop_times o JOIN trips t ON t.trip_pk=o.trip_pk
              JOIN routes r ON r.route_id=t.route_id
              WHERE o.stop_id IN ({",".join("?" for _ in stops)})
                AND t.service_id IN ({",".join("?" for _ in services)})
                AND {pickup_clause} AND o.departure IS NOT NULL
                AND EXISTS(SELECT 1 FROM stop_times d WHERE d.trip_pk=t.trip_pk AND d.sequence>o.sequence AND {drop_clause})
                AND (o.departure BETWEEN ? AND ? OR EXISTS(SELECT 1 FROM frequencies f WHERE f.trip_pk=t.trip_pk))
                {clause}
            """
            for raw in self.connection.execute(sql, parameters):
                record = dict(raw)
                frequency_rows = self.connection.execute(
                    "SELECT * FROM frequencies WHERE trip_pk=?", (record["trip_pk"],)
                ).fetchall()
                departures = []
                if not frequency_rows:
                    departures.append((record["origin_departure"], "scheduled", None))
                elif record["first_departure"] is not None:
                    offset = record["origin_departure"] - record["first_departure"]
                    for frequency in frequency_rows:
                        earliest, latest = frequency["start"] + offset, frequency["end"] + offset
                        if frequency["exact_times"]:
                            departure = (
                                earliest
                                + max(0, math.ceil((low - earliest) / frequency["headway"]))
                                * frequency["headway"]
                            )
                            while departure < latest and departure <= high:
                                departures.append(
                                    (departure, "frequency_exact", frequency["headway"])
                                )
                                if not all_departures:
                                    break
                                departure += frequency["headway"]
                        elif earliest <= high and latest > low:
                            # This is an availability bound, never an invented exact departure.
                            departures.append(
                                (
                                    max(earliest, low),
                                    "frequency_window_estimated",
                                    frequency["headway"],
                                )
                            )
                for departure, basis, headway in departures:
                    if not low <= departure <= high:
                        continue
                    yield {
                        **record,
                        "service_date": service_day.isoformat(),
                        "boarding_at": (midnight + timedelta(seconds=departure)).isoformat(),
                        "boarding_seconds": departure,
                        "midnight": midnight,
                        "basis": basis,
                        "headway_seconds": headway,
                    }

    def has_unresolved_boarding(self, leg, when, until):
        """Diagnostic only: active structure whose missing times cannot exclude this window.

        No departure is synthesized. Published neighboring times can exclude a
        window, but an overlap of bounds never proves a boarding within it.
        Service dates use the published-time lookback, also considering frequency
        windows when their template anchor is missing. Unbounded offsets remain
        unresolved; this is not proof of temporal membership or a boarding time.
        """
        self.validate_leg_structure(leg)
        when = aware(when)
        end = aware(until)
        if not when <= end <= when + timedelta(minutes=1440):
            raise CatalogError("Diagnostic window must be between 0 and 1440 minutes")
        stops = self.stop_family(leg.origin_stop_id)
        for _, services, _, low, high in self._service_windows(when, end, unresolved=True):
            rows = self.connection.execute(
                f"""
                SELECT t.trip_pk,t.first_departure FROM trips t
                JOIN stop_times o ON o.trip_pk=t.trip_pk
                JOIN stop_times d ON d.trip_pk=t.trip_pk
                WHERE t.route_id=? AND t.pattern_id=? AND t.direction_id IS ?
                AND t.service_id IN ({",".join("?" for _ in services)})
                AND o.stop_id IN ({",".join("?" for _ in stops)}) AND o.sequence=?
                AND o.pickup_type=0 AND d.stop_id=? AND d.sequence=?
                AND d.sequence>o.sequence AND d.drop_off_type=0
                AND (o.departure IS NULL OR (t.first_departure IS NULL AND
                     EXISTS(SELECT 1 FROM frequencies f WHERE f.trip_pk=t.trip_pk)))
                """,
                (
                    leg.route_id,
                    leg.pattern_id,
                    leg.direction_id,
                    *sorted(services),
                    *stops,
                    leg.origin_sequence,
                    leg.destination_stop_id,
                    leg.destination_sequence,
                ),
            )
            for row in rows:
                prior = self.connection.execute(
                    "SELECT MAX(arrival),MAX(departure) FROM stop_times WHERE trip_pk=? AND sequence<=?",
                    (row["trip_pk"], leg.origin_sequence),
                ).fetchone()
                following = self.connection.execute(
                    "SELECT MIN(arrival),MIN(departure) FROM stop_times WHERE trip_pk=? AND sequence>?",
                    (row["trip_pk"], leg.origin_sequence),
                ).fetchone()
                lower = max((v for v in prior if v is not None), default=None)
                upper = min((v for v in following if v is not None), default=None)
                frequencies = self.connection.execute(
                    "SELECT start,end FROM frequencies WHERE trip_pk=?", (row["trip_pk"],)
                ).fetchall()
                if frequencies:
                    # Template clocks are relative to the first departure, not
                    # absolute clocks for frequency instances. Without that anchor,
                    # only the published start supplies a lower bound; end is not
                    # a bound on downstream boardings with an unknown offset.
                    anchor = row["first_departure"]
                    bounds = [
                        (
                            f["start"] + max(0, lower - anchor)
                            if anchor is not None and lower is not None
                            else f["start"],
                            f["end"] + upper - anchor
                            if anchor is not None and upper is not None
                            else None,
                        )
                        for f in frequencies
                    ]
                else:
                    bounds = [(lower, upper)]
                if any((a is None or a <= high) and (b is None or b >= low) for a, b in bounds):
                    return True
        return False

    def scheduled_connections(self, leg, when, *, window_minutes=120):
        """All explicit alternatives for one saved leg, with the existing calendar rules.

        Unlike destinations(), do not collapse trips by stop occurrence: a later
        boarding may arrive earlier. Unresolved frequency/time rows have no exact
        boarding/arrival and cannot be used to prove a timed itinerary.
        """
        self.validate_leg_structure(leg)
        results = {}
        names = {}
        for candidate in self._candidates(
            leg.origin_stop_id,
            when,
            window_minutes,
            route_id=leg.route_id,
            pattern_id=leg.pattern_id,
            all_departures=True,
        ):
            if candidate["origin_sequence"] != leg.origin_sequence:
                continue
            destination = self.connection.execute(
                "SELECT t.arrival,s.name FROM stop_times t JOIN stops s ON s.stop_id=t.stop_id WHERE t.trip_pk=? AND t.sequence=? AND t.stop_id=? AND t.drop_off_type=0",
                (candidate["trip_pk"], leg.destination_sequence, leg.destination_stop_id),
            ).fetchone()
            if destination is None:
                continue
            offset = candidate["boarding_seconds"] - candidate["origin_departure"]
            arrival = (
                destination["arrival"] + offset if destination["arrival"] is not None else None
            )
            unresolved = candidate["basis"] == "frequency_window_estimated" or arrival is None
            if arrival is not None and arrival < candidate["boarding_seconds"]:
                continue
            platform = candidate["origin_platform_id"]
            if platform not in names:
                names[platform] = self.connection.execute(
                    "SELECT name FROM stops WHERE stop_id=?", (platform,)
                ).fetchone()[0]
            key = (
                candidate["trip_id"],
                candidate["service_date"],
                candidate["boarding_at"],
                platform,
            )
            results[key] = {
                "trip_id": candidate["trip_id"],
                "service_date": candidate["service_date"],
                "boarding_at": None if unresolved else candidate["boarding_at"],
                "arrival_at": None
                if unresolved
                else (candidate["midnight"] + timedelta(seconds=arrival)).isoformat(),
                "availability_from": candidate["boarding_at"],
                "time_basis": candidate["basis"],
                "origin_platform_id": platform,
                "origin_name": names[platform],
                "destination_name": destination["name"],
                "route_name": candidate["short_name"],
            }
        return sorted(results.values(), key=lambda r: (r["availability_from"], r["trip_id"]))

    def options(
        self, origin: str, when: datetime, *, window_minutes=120, include_conditional=False
    ) -> list[dict]:
        grouped = {}
        for row in self._candidates(
            origin, when, window_minutes, include_conditional=include_conditional
        ):
            key = (
                row["route_id"],
                row["direction_id"],
                row["pattern_id"],
                row["origin_platform_id"],
                row["origin_sequence"],
            )
            if key not in grouped:
                grouped[key] = {
                    k: row[k]
                    for k in (
                        "route_id",
                        "direction_id",
                        "pattern_id",
                        "origin_platform_id",
                        "origin_sequence",
                        "short_name",
                        "long_name",
                        "headsign",
                        "boarding_type",
                    )
                }
                grouped[key].update(
                    availability_from=row["boarding_at"],
                    next_boarding_at=None
                    if row["basis"] == "frequency_window_estimated"
                    else row["boarding_at"],
                    time_basis=row["basis"],
                    headway_seconds=row["headway_seconds"],
                    service_dates=set(),
                    trips=set(),
                )
            result = grouped[key]
            result["service_dates"].add(row["service_date"])
            result["trips"].add((row["trip_id"], row["service_date"]))
            if row["boarding_at"] < result["availability_from"]:
                result.update(
                    availability_from=row["boarding_at"],
                    next_boarding_at=None
                    if row["basis"] == "frequency_window_estimated"
                    else row["boarding_at"],
                    time_basis=row["basis"],
                    headway_seconds=row["headway_seconds"],
                )
        result = []
        for row in grouped.values():
            row["service_dates"] = sorted(row["service_dates"])
            row["trip_templates"] = len(row.pop("trips"))
            result.append(row)
        return sorted(
            result,
            key=lambda r: (
                r["short_name"],
                str(r["direction_id"]),
                r["pattern_id"],
                r["origin_sequence"],
            ),
        )

    def routes_for_stop(self, origin: str, when: datetime, *, window_minutes=120) -> list[dict]:
        routes = {}
        for option in self.options(origin, when, window_minutes=window_minutes):
            routes[option["route_id"]] = {
                k: option[k] for k in ("route_id", "short_name", "long_name")
            }
        return list(routes.values())

    def destinations(
        self,
        origin: str,
        route_id: str,
        direction_id: int | None,
        pattern_id: str,
        when: datetime,
        *,
        origin_sequence: int | None = None,
        window_minutes=120,
        include_conditional=False,
    ) -> list[dict]:
        pattern = self.connection.execute(
            "SELECT * FROM patterns WHERE pattern_id=?", (pattern_id,)
        ).fetchone()
        if (
            not pattern
            or pattern["route_id"] != route_id
            or pattern["direction_id"] != direction_id
        ):
            raise CatalogError("Route, direction and pattern are incompatible")
        candidates = list(
            self._candidates(
                origin,
                when,
                window_minutes,
                route_id=route_id,
                pattern_id=pattern_id,
                include_conditional=include_conditional,
            )
        )
        sequences = {row["origin_sequence"] for row in candidates}
        if origin_sequence is None and len(sequences) > 1:
            raise CatalogError("Origin occurs multiple times; choose origin_sequence explicitly")
        if origin_sequence is not None:
            candidates = [row for row in candidates if row["origin_sequence"] == origin_sequence]
        if not candidates:
            raise CatalogError("No eligible boarding for this origin/pattern/date/time window")
        results = {}
        drop_clause = "st.drop_off_type<>1" if include_conditional else "st.drop_off_type=0"
        for candidate in sorted(candidates, key=lambda r: r["boarding_at"]):
            for row in self.connection.execute(
                f"""
                SELECT st.sequence,st.stop_id,st.arrival,st.drop_off_type,s.code,s.name,s.parent_station
                FROM stop_times st JOIN stops s ON s.stop_id=st.stop_id
                WHERE st.trip_pk=? AND st.sequence>? AND {drop_clause}
                ORDER BY st.sequence
            """,
                (candidate["trip_pk"], candidate["origin_sequence"]),
            ):
                offset = candidate["boarding_seconds"] - candidate["origin_departure"]
                arrival = row["arrival"] + offset if row["arrival"] is not None else None
                if arrival is not None and arrival < candidate["boarding_seconds"]:
                    continue
                if row["sequence"] not in results:
                    estimated = candidate["basis"] == "frequency_window_estimated"
                    results[row["sequence"]] = {
                        **{
                            key: row[key]
                            for key in (
                                "sequence",
                                "stop_id",
                                "drop_off_type",
                                "code",
                                "name",
                                "parent_station",
                            )
                        },
                        "arrival_seconds": None if estimated else arrival,
                        "template_arrival_seconds": row["arrival"],
                        "arrival_at": (
                            candidate["midnight"] + timedelta(seconds=arrival)
                        ).isoformat()
                        if arrival is not None and not estimated
                        else None,
                        "time_basis": candidate["basis"],
                        "service_date": candidate["service_date"],
                        "example_trip_id": candidate["trip_id"],
                        "boarding_at": None if estimated else candidate["boarding_at"],
                        "origin_platform_id": candidate["origin_platform_id"],
                        "origin_sequence": candidate["origin_sequence"],
                        "pattern_id": pattern_id,
                    }
        return sorted(results.values(), key=lambda r: r["sequence"])

    def validate_destination(
        self,
        origin,
        route_id,
        direction_id,
        pattern_id,
        when,
        destination_id,
        *,
        destination_sequence=None,
        **kwargs,
    ):
        for destination in self.destinations(
            origin, route_id, direction_id, pattern_id, when, **kwargs
        ):
            if destination["stop_id"] == destination_id and (
                destination_sequence is None or destination["sequence"] == destination_sequence
            ):
                return destination
        raise CatalogError(
            "Destination is not downstream with permitted drop-off in the selected service"
        )
