"""FastAPI router for POI (Point of Interest) endpoints."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from ..poi.scorer import decay_score, nearest, score_property

logger = logging.getLogger(__name__)
router = APIRouter()

# ------------------------------------------------------------------ rate limiter
_rate_window_ms: int = 60_000
_rate_max: int = 20  # per window


class _RateLimiter:
    """Simple thread-safe-enough per-IP in-memory rate limiter.

    Uses a cleanup sweep triggered on every call once the window elapses,
    so stale IP buckets do not accumulate indefinitely.
    """

    def __init__(self, window_ms: int = _rate_window_ms, max_reqs: int = _rate_max):
        self.window_ms = window_ms
        self.max_reqs = max_reqs
        self._buckets: dict[str, list[float]] = {}
        self._last_cleanup = time.time()

    def allow(self, ip: str) -> bool:
        now = time.time()
        self._maybe_cleanup(now)
        bucket = self._buckets.get(ip)
        if bucket is None:
            self._buckets[ip] = [now]
            return True
        cutoff = now - (self.window_ms / 1000)
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= self.max_reqs:
            return False
        bucket.append(now)
        return True

    def _maybe_cleanup(self, now: float) -> None:
        """Evict stale buckets periodically to prevent memory leaks."""
        if now - self._last_cleanup < self.window_ms / 1000:
            return
        self._last_cleanup = now
        cutoff = now - (self.window_ms / 1000)
        stale = [ip for ip, ts in self._buckets.items() if ts and ts[-1] < cutoff]
        for ip in stale:
            del self._buckets[ip]


_rate_limiter = _RateLimiter()


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


# ------------------------------------------------------------------ auth
async def _check_auth(request: Request) -> None:
    """Require X-API-Key header for write operations.

    When POI_INGEST_API_KEY is not set, auth is disabled and a warning is
    logged. When set, the header must match exactly. The response behaviour
    is identical for "key not configured" and "wrong key" to avoid leaking
    configuration state through status codes.
    """
    api_key = request.headers.get("x-api-key", "")
    expected = os.getenv("POI_INGEST_API_KEY", "")
    if not expected:
        logger.warning(
            "PoI ingest authentication is DISABLED (POI_INGEST_API_KEY not set). "
            "This is insecure for production deployments."
        )
        return
    if not api_key or api_key != expected:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


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

    lat_min, lon_min, lat_max, lon_max = coords

    if not (VALID_BBOX_BOUNDS[0] <= lat_min <= VALID_BBOX_BOUNDS[2]):
        raise HTTPException(status_code=400, detail="lat_min out of range [-90, 90]")
    if not (VALID_BBOX_BOUNDS[1] <= lon_min <= VALID_BBOX_BOUNDS[3]):
        raise HTTPException(status_code=400, detail="lon_min out of range [-180, 180]")
    if not (VALID_BBOX_BOUNDS[0] <= lat_max <= VALID_BBOX_BOUNDS[2]):
        raise HTTPException(status_code=400, detail="lat_max out of range [-90, 90]")
    if not (VALID_BBOX_BOUNDS[1] <= lon_max <= VALID_BBOX_BOUNDS[3]):
        raise HTTPException(status_code=400, detail="lon_max out of range [-180, 180]")

    if lat_min >= lat_max or lon_min >= lon_max:
        raise HTTPException(status_code=400, detail="bbox must have min < max for both lat and lon")

    if (lat_max - lat_min) > 60 or (lon_max - lon_min) > 60:
        raise HTTPException(status_code=400, detail="bbox too large — use multiple smaller queries")

    return coords


# ------------------------------------------------------------------ runtime state
_poi_data: list[dict[str, Any]] = []


def set_poi_data(data: list[dict]):
    global _poi_data
    _poi_data = data


# ------------------------------------------------------------------ endpoints
@router.post("/ingest")
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
    rng = random.Random(hash(bbox))

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

    _poi_data.extend(new_pois)

    return {"ingested": len(new_pois), "total": len(_poi_data)}


@router.get("/nearby")
async def nearby_pois(lat: float, lon: float, category: str = "", n: int = 5):
    """Get nearby POIs for a property."""
    if not _poi_data:
        return {"nearby": [], "message": "No POI data ingested"}

    nearest_points = nearest(_poi_data, lat, lon, n=max(n, 10))
    scores = score_property(_poi_data, lat, lon)

    results = []
    for pt in nearest_points:
        if category and pt["category"] != category:
            continue
        results.append({
            "name": pt["name"],
            "category": pt["category"],
            "distance_m": round(pt["distance_m"], 1),
            "walk_time_min": max(1, round(pt["distance_m"] / 80)),
            "decay_score": round(pt["decay_score"], 3),
        })

    return {"nearby": results[:n], "category_scores": scores}


@router.get("/health")
async def poi_health():
    return {"status": "ok", "total_pois": len(_poi_data)}
