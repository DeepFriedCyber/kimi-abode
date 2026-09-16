"""POI scorer — reusable scoring functions for point-of-interest proximity."""

from math import atan2, cos, radians, sin, sqrt
from typing import NamedTuple


class PoiPoint(NamedTuple):
    """A single POI point with coordinates and metadata."""
    name: str
    osm_id: int
    lat: float
    lon: float
    category: str
    distance_m: float = 0.0
    decay_score: float = 0.0

from math import atan2, cos, radians, sin, sqrt


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two WGS84 coordinates."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def decay_score(distance_m: float, half_life: float = 500.0) -> float:
    """Exponential decay score. At distance=half_life, score=0.5."""
    return 0.5 ** (distance_m / half_life)


def nearest(points, target_lat: float, target_lon: float, n: int = 5):
    for p in points:
        if "distance_m" not in p:
            p["distance_m"] = haversine_m(target_lat, target_lon, p["lat"], p["lon"])
        if "decay_score" not in p:
            p["decay_score"] = decay_score(p["distance_m"])
    return sorted(points, key=lambda p: p["distance_m"])[:n]


def score_property(points, target_lat: float, target_lon: float) -> dict[str, float]:
    scores = {}
    for pt in points:
        dist = haversine_m(target_lat, target_lon, pt["lat"], pt["lon"])
        sc = decay_score(dist)
        cat = pt.get("category", "unknown")
        scores[cat] = scores.get(cat, 0) + sc * 100
    return {k: round(v, 2) for k, v in scores.items()}
