"""Observed-position projection, conservative branch resolution and stop anchors."""

import bisect
import math
from dataclasses import dataclass

from transmitracker.research.temporal import EARTH


@dataclass(frozen=True)
class CandidateProjection:
    progress_m: float
    residual_m: float
    edge_index: int


class MeasuredShape:
    def __init__(self, points, published_distances=()):
        self.points = tuple(points)
        self.published = tuple(published_distances)
        self.xy = tuple(self.to_xy(p) for p in points)
        self.along = [0.0]
        for a, b in zip(self.xy, self.xy[1:], strict=False):
            self.along.append(self.along[-1] + math.dist(a, b))

    def to_xy(self, position):
        first = self.points[0]
        return (
            EARTH * math.radians(position[1] - first[1]) * math.cos(math.radians(first[0])),
            EARTH * math.radians(position[0] - first[0]),
        )

    def candidates(self, position):
        x, y = self.to_xy(position)
        choices = []
        for index, (a, b) in enumerate(zip(self.xy, self.xy[1:], strict=False)):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = self.along[index + 1] - self.along[index]
            if length == 0:
                continue
            fraction = min(1.0, max(0.0, ((x - a[0]) * dx + (y - a[1]) * dy) / length**2))
            choices.append(
                CandidateProjection(
                    self.along[index] + fraction * length,
                    math.hypot(x - a[0] - fraction * dx, y - a[1] - fraction * dy),
                    index,
                )
            )
        return sorted(choices, key=lambda p: (p.residual_m, p.progress_m, p.edge_index))

    def published_progress(self, value):
        """Map consistent GTFS distance units to measured metres; never assume unit=metre."""
        if (
            value is None
            or len(self.published) != len(self.along)
            or any(v is None for v in self.published)
        ):
            return None
        if (
            any(b <= a for a, b in zip(self.published, self.published[1:], strict=False))
            or not self.published[0] <= value <= self.published[-1]
        ):
            return None
        index = min(len(self.published) - 2, max(0, bisect.bisect_right(self.published, value) - 1))
        fraction = (value - self.published[index]) / (
            self.published[index + 1] - self.published[index]
        )
        return self.along[index] + fraction * (self.along[index + 1] - self.along[index])


@dataclass(frozen=True)
class StopAnchor:
    stop_id: str
    sequence: int
    latitude: float | None
    longitude: float | None
    progress_m: float | None
    reason: str
    pickup_type: int
    drop_off_type: int


@dataclass(frozen=True)
class PatternGeometry:
    pattern_id: str
    route_id: str
    shape_id: str
    shape: MeasuredShape
    stops: tuple[StopAnchor, ...]


class GeometryCatalog:
    def __init__(self, catalog, parameters):
        self.catalog, self.parameters, self.cache = catalog, parameters, {}

    def load(self, trip_id):
        if trip_id in self.cache:
            return self.cache[trip_id]
        trip = self.catalog.connection.execute(
            "SELECT * FROM trips WHERE trip_id=?", (trip_id,)
        ).fetchone()
        if not trip or not trip["shape_id"] or not trip["pattern_id"]:
            return None
        points = list(
            self.catalog.connection.execute(
                "SELECT latitude,longitude,distance FROM shape_points WHERE shape_id=? ORDER BY sequence",
                (trip["shape_id"],),
            )
        )
        if len(points) < 2:
            return None
        shape = MeasuredShape([(p[0], p[1]) for p in points], [p[2] for p in points])
        anchors = []
        previous = -1.0
        rows = self.catalog.connection.execute(
            "SELECT t.sequence,t.shape_distance,t.pickup_type,t.drop_off_type,s.* FROM stop_times t JOIN stops s ON s.stop_id=t.stop_id WHERE trip_pk=? ORDER BY t.sequence",
            (trip["trip_pk"],),
        )
        for stop in rows:
            progress, reason = None, "stop_coordinates_missing"
            if stop["latitude"] is not None and stop["longitude"] is not None:
                choices = shape.candidates((stop["latitude"], stop["longitude"]))
                if choices:
                    near = [
                        p
                        for p in choices
                        if p.residual_m <= choices[0].residual_m + self.parameters.projection_tie_m
                    ]
                    published = shape.published_progress(stop["shape_distance"])
                    if published is not None:
                        best = min(near, key=lambda p: abs(p.progress_m - published))
                        if abs(best.progress_m - published) <= self.parameters.stop_radius_m:
                            progress, reason = (
                                best.progress_m,
                                "consistent_published_shape_distance",
                            )
                    elif (
                        max(p.progress_m for p in near) - min(p.progress_m for p in near)
                        < self.parameters.branch_separation_m
                    ):
                        progress, reason = near[0].progress_m, "unique_stop_projection"
                    else:
                        reason = "ambiguous_stop_occurrence_geometry"
                    if choices[0].residual_m > self.parameters.max_offset_m:
                        progress, reason = None, "stop_far_from_shape"
            if progress is not None and progress < previous:
                progress, reason = None, "stop_anchor_order_conflict"
            if progress is not None:
                previous = progress
            anchors.append(
                StopAnchor(
                    stop["stop_id"],
                    stop["sequence"],
                    stop["latitude"],
                    stop["longitude"],
                    progress,
                    reason,
                    stop["pickup_type"],
                    stop["drop_off_type"],
                )
            )
        result = PatternGeometry(
            trip["pattern_id"], trip["route_id"], trip["shape_id"], shape, tuple(anchors)
        )
        if len(self.cache) >= 64:
            self.cache.pop(next(iter(self.cache)))
        self.cache[trip_id] = result
        return result


def select_projection(geometry, observation, parameters, previous=None, delta=None):
    candidates = geometry.shape.candidates((observation.latitude, observation.longitude))
    if not candidates or candidates[0].residual_m > parameters.max_offset_m:
        return None, "off_shape_or_missing_geometry"
    near = [
        c
        for c in candidates
        if c.residual_m <= candidates[0].residual_m + parameters.projection_tie_m
    ]
    target_index = next(
        (
            i
            for i, s in enumerate(geometry.stops)
            if s.sequence == observation.current_stop_sequence and s.stop_id == observation.stop_id
        ),
        None,
    )
    support = "unique_geometry"
    if target_index is not None and observation.current_status in (
        "IN_TRANSIT_TO",
        "STOPPED_AT",
        "INCOMING_AT",
    ):
        target = geometry.stops[target_index].progress_m
        prior = geometry.stops[target_index - 1].progress_m if target_index else 0.0
        if target is not None and prior is not None:
            low, high = prior - parameters.gps_error_m, target + parameters.gps_error_m
            if observation.current_status == "STOPPED_AT":
                low = target - parameters.stop_radius_m
            near = [c for c in near if low <= c.progress_m <= high]
            support = "published_stop_occurrence_and_geometry"
    if previous is not None:
        near = [
            c
            for c in near
            if -parameters.backtrack_tolerance_m
            <= c.progress_m - previous.progress_m
            <= parameters.max_speed_mps * delta + parameters.gps_error_m
        ]
        support += "_and_observed_continuity"
    if not near:
        return None, "progress_or_reported_sequence_conflict"
    if (
        max(c.progress_m for c in near) - min(c.progress_m for c in near)
        > parameters.branch_separation_m
    ):
        return None, "ambiguous_shape_branch"
    return near[0], support
