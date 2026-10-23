"""POI scorer — reusable scoring functions for point-of-interest proximity."""

from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
from typing import Iterable, NamedTuple


class PoiPoint(NamedTuple):
    """A single POI point with coordinates and metadata."""

    name: str
    osm_id: int
    lat: float
    lon: float
    category: str
    distance_m: float = 0.0
    decay_score: float = 0.0


EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two WGS84 coordinates."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    # Clamp guards against floating-point drift producing a >1 value.
    return EARTH_RADIUS_M * 2 * atan2(sqrt(min(1.0, a)), sqrt(max(0.0, 1 - a)))


def decay_score(distance_m: float, half_life: float = 500.0) -> float:
    """Exponential decay: 1.0 at the point, 0.5 at `half_life` metres."""
    if distance_m < 0:
        raise ValueError("distance_m must be non-negative")
    return 0.5 ** (distance_m / half_life)


def _has_coordinates(point: dict) -> bool:
    return (
        point.get("lat") is not None
        and point.get("lon") is not None
    )


def annotate_distances(
    points: Iterable[dict],
    target_lat: float,
    target_lon: float,
) -> list[dict]:
    """Return copies of `points` with fresh distance/decay values.

    Copies matter: the previous implementation mutated the caller's list and
    reused distances computed for a different property.
    """
    annotated: list[dict] = []
    for point in points:
        if not _has_coordinates(point):
            continue
        distance = haversine_m(target_lat, target_lon, point["lat"], point["lon"])
        annotated.append(
            {
                **point,
                "distance_m": distance,
                "decay_score": decay_score(distance),
            }
        )
    return annotated


def nearest(
    points: Iterable[dict],
    target_lat: float,
    target_lon: float,
    n: int = 5,
) -> list[dict]:
    """Return the `n` nearest points, each annotated with distance and score."""
    annotated = annotate_distances(points, target_lat, target_lon)
    annotated.sort(key=lambda point: point["distance_m"])
    return annotated[: max(0, n)]


def score_property(
    points: Iterable[dict],
    target_lat: float,
    target_lon: float,
    *,
    half_life: float = 500.0,
    cap_per_category: float = 100.0,
) -> dict[str, float]:
    """Aggregate proximity scores per category, capped to avoid a single
    category (e.g. 40 restaurants) dominating the ranking."""
    scores: dict[str, float] = {}
    for point in points:
        if not _has_coordinates(point):
            continue
        category = point.get("category", "unknown")
        distance = haversine_m(target_lat, target_lon, point["lat"], point["lon"])
        scores[category] = scores.get(category, 0.0) + decay_score(distance, half_life) * 100

    return {
        category: round(min(value, cap_per_category), 2)
        for category, value in scores.items()
    }
