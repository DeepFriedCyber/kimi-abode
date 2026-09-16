"""FastAPI router for POI (Point of Interest) endpoints."""

from __future__ import annotations

import random
import time

from fastapi import APIRouter, HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

router = APIRouter()

# ------------------------------------------------------------------ rate limiter
_rate_window_ms: int = 60_000
_rate_max: int = 20  # per window


class _RateLimiter:
    """Simple per-IP in-memory rate limiter."""

    def __init__(self, window_ms: int = _rate_window_ms, max_reqs: int = _rate_max):
        self.window_ms = window_ms
        self.max_reqs = max_reqs
        self._buckets: dict[str, list[float]] = {}

    def allow(self, ip: str) -> bool:
        now = time.time()
        bucket = self._buckets.get(ip)
        if bucket is None:
            self._buckets[ip] = [now]
            return True
        # Evict old entries
        cutoff = now - (self.window_ms / 1000)
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= self.max_reqs:
            return False
        bucket.append(now)
        return True

    def cleanup(self) -> None:
        """Remove stale buckets to prevent memory leaks."""
        now = time.time()
        cutoff = now - (self.window_ms / 1000)
        stale = [ip for ip, ts in self._buckets.items() if ts and ts[-1] < cutoff]
        for ip in stale:
            del self._buckets[ip]


import time

_rate_limiter = _RateLimiter()


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


# Runtime state — filled by main.py
_poi_data: list[dict] = []


def set_poi_data(data: list[dict]):
    global _poi_data
    _poi_data = data


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance in metres between two coordinates."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371000  # Earth radius in metres
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def decay_score(distance_m: float, half_life: float = 500.0) -> float:
    """Score that decays exponentially with distance.

    At distance = half_life, score = 0.5.
    """
    return 0.5 ** (distance_m / half_life)


def nearest(points: list[dict], target_lat: float, target_lon: float, n: int = 5) -> list[dict]:
    """Find the N nearest POI points to a target coordinate."""
    for p in points:
        if "distance_m" not in p:
            p["distance_m"] = haversine_m(target_lat, target_lon, p["lat"], p["lon"])
        if "decay_score" not in p:
            p["decay_score"] = decay_score(p["distance_m"])

    sorted_pts = sorted(points, key=lambda p: p["distance_m"])
    return sorted_pts[:n]


def score_property(points: list[dict], target_lat: float, target_lon: float) -> dict[str, float]:
    """Score a property against POI categories."""
    nearest_points = nearest(points, target_lat, target_lon)
    scores = {}
    for pt in nearest_points:
        cat = pt["category"]
        if cat not in scores:
            scores[cat] = 0.0
        scores[cat] += pt["decay_score"] * 100
    return scores


# ------------------------------------------------------------------ validation helpers
VALID_BBOX_BOUNDS = (-90, -180, 90, 180)


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse and validate bounding box string."""
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be lat_min,lon_min,lat_max,lon_max")

    try:
        coords = [float(x) for x in parts]
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox values must be numbers")

    # Validate range
    for coord, (lo, hi) in zip(coords, [VALID_BBOX_BOUNDS[::2], VALID_BBOX_BOUNDS[1::2]]):
        if coord < lo or coord > hi:
            raise HTTPException(status_code=400, detail=f"bbox values must be within {min(lo,hi)}-{max(lo,hi)}")

    # Validate area isn't absurdly large (> 1% of Earth surface)
    lat_min, lon_min, lat_max, lon_max = coords
    if (lat_max - lat_min) > 60 or (lon_max - lon_min) > 60:
        raise HTTPException(status_code=400, detail="bbox too large — use multiple smaller queries")

    return coords


async def _check_auth(request: Request) -> None:
    """Require X-API-Key header for write operations."""
    api_key = request.headers.get("x-api-key", "")
    expected = __import__("os").getenv("POI_INGEST_API_KEY", "")
    if not expected or api_key == expected:
        return
    # If POI_INGEST_API_KEY is set but header doesn't match → forbidden
    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Valid API key required")


# ------------------------------------------------------------------ endpoints

@router.post("/poi/ingest")
async def ingest_pois(body: dict, request: Request):
    """Ingest POI data from Overpass API for a bounding box.

    POST body: {"bbox": "lat_min,lon_min,lat_max,lon_max"}
    Requires X-API-Key header when POI_INGEST_API_KEY is set.
    """
    await _check_auth(request)

    ip = _get_ip(request)
    if not _rate_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="Too many ingest requests — try again later")

    bbox = body.get("bbox", "")
    lat_min, lon_min, lat_max, lon_max = _parse_bbox(bbox)

    # In production: query Overpass API
    # For now: generate sample POIs in the bbox
    rng = random.Random(hash(bbox))  # deterministic for testing

    categories = ["restaurant", "pub", "school", "supermarket", "hospital", "station"]
    new_pois = []
    for _ in range(50):
        cat = rng.choice(categories)
        new_pois.append({
            "name": f"{cat.title()} {rng.randint(1, 200)}",
            "osm_id": rng.randint(1_000_000, 9_999_999),
            "lat": rng.uniform(lat_min, lat_max),
            "lon": rng.uniform(lon_min, lon_max),
            "category": cat,
        })

    global _poi_data
    _poi_data.extend(new_pois)

    return {"ingested": len(new_pois), "total": len(_poi_data)}


@router.get("/poi/nearby")
async def nearby_pois(lat: float, lon: float, category: str = "", n: int = 5):
    """Get nearby POIs for a property."""
    if not _poi_data:
        return {"nearby": [], "message": "No POI data ingested"}

    nearest_points = nearest(_poi_data, lat, lon)
    scores = score_property(_poi_data, lat, lon)

    results = []
    for pt in nearest_points:
        if category and pt["category"] != category:
            continue
        results.append({
            "name": pt["name"],
            "category": pt["category"],
            "distance_m": round(pt["distance_m"], 1),
            "walk_time_min": max(1, round(pt["distance_m"] / 80)),  # ~80 m/min walking
            "decay_score": round(pt["decay_score"], 3),
        })

    return {"nearby": results[:n], "category_scores": scores}


@router.get("/poi/health")
async def poi_health():
    return {"status": "ok", "total_pois": len(_poi_data)}
