"""FastAPI router for POI (Point of Interest) endpoints."""

from __future__ import annotations

import hmac
import logging
import os
import time
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..poi.overpass import fetch_pois
from ..poi.scorer import annotate_distances, score_property

logger = logging.getLogger(__name__)
router = APIRouter()

# ------------------------------------------------------------------ rate limiter
RATE_WINDOW_SECONDS = 60
RATE_MAX_REQUESTS = 20
MAX_STORED_POIS = 50_000


class RateLimiter:
    """Per-IP fixed-window limiter for the (expensive) ingest endpoint."""

    def __init__(self, window_seconds: int = RATE_WINDOW_SECONDS, max_requests: int = RATE_MAX_REQUESTS):
        self.window = window_seconds
        self.max_requests = max_requests
        self._buckets: dict[str, list[float]] = {}
        self._last_cleanup = time.time()

    def allow(self, key: str) -> bool:
        now = time.time()
        self._cleanup(now)

        bucket = self._buckets.setdefault(key, [])
        cutoff = now - self.window
        bucket[:] = [timestamp for timestamp in bucket if timestamp > cutoff]

        if len(bucket) >= self.max_requests:
            return False

        bucket.append(now)
        return True

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self.window:
            return
        self._last_cleanup = now
        cutoff = now - self.window
        for key in [k for k, v in self._buckets.items() if not v or v[-1] < cutoff]:
            del self._buckets[key]


_rate_limiter = RateLimiter()


def _trust_proxy() -> bool:
    return os.getenv("TRUST_PROXY_HEADERS", "").strip().lower() in {"1", "true", "yes"}


def _client_ip(request: Request) -> str:
    if _trust_proxy():
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------------ auth
def _expected_api_key() -> str:
    # Support the legacy name so existing deployments do not silently lose auth.
    return os.getenv("POI_INGEST_API_KEY") or os.getenv("POI_INJECTION_SECRET") or ""


async def _check_auth(request: Request) -> None:
    """Require X-API-Key for write operations.

    Fails closed in production when no key is configured; allows local
    development with a loud warning.
    """
    expected = _expected_api_key()
    if not expected:
        if os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "")).lower() == "production":
            raise HTTPException(status_code=503, detail="POI ingest is not configured")
        logger.warning(
            "POI ingest auth is DISABLED (set POI_INGEST_API_KEY). Local only."
        )
        return

    provided = request.headers.get("x-api-key", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Authentication required")


# ------------------------------------------------------------------ validation
BBOX_LAT = (-90.0, 90.0)
BBOX_LON = (-180.0, 180.0)
MAX_BBOX_SPAN = 60.0


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in bbox.split(",")]
    if len(parts) != 4:
        raise HTTPException(
            status_code=400, detail="bbox must be lat_min,lon_min,lat_max,lon_max"
        )

    try:
        lat_min, lon_min, lat_max, lon_max = (float(part) for part in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox values must be numbers") from None

    if not (BBOX_LAT[0] <= lat_min <= BBOX_LAT[1]) or not (BBOX_LAT[0] <= lat_max <= BBOX_LAT[1]):
        raise HTTPException(status_code=400, detail="latitude out of range [-90, 90]")
    if not (BBOX_LON[0] <= lon_min <= BBOX_LON[1]) or not (BBOX_LON[0] <= lon_max <= BBOX_LON[1]):
        raise HTTPException(status_code=400, detail="longitude out of range [-180, 180]")

    if lat_min >= lat_max or lon_min >= lon_max:
        raise HTTPException(status_code=400, detail="bbox must have min < max")
    if (lat_max - lat_min) > MAX_BBOX_SPAN or (lon_max - lon_min) > MAX_BBOX_SPAN:
        raise HTTPException(status_code=400, detail="bbox too large — split the query")

    return lat_min, lon_min, lat_max, lon_max


# ------------------------------------------------------------------ runtime state
_poi_data: list[dict[str, Any]] = []


def set_poi_data(data: list[dict]) -> None:
    global _poi_data
    _poi_data = list(data)


def get_poi_data() -> list[dict[str, Any]]:
    """Amenity cache (loaded from data/poi_cache.json at startup)."""
    return _poi_data


# ------------------------------------------------------------------ endpoints
@router.post("/ingest")
async def ingest_pois(body: dict, request: Request):
    """Ingest POIs from OpenStreetMap for a bounding box."""
    await _check_auth(request)

    if not _rate_limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many ingest requests")

    bbox = _parse_bbox(str(body.get("bbox", "")))

    pois = await fetch_pois(bbox)
    if not pois:
        return {
            "ingested": 0,
            "total": len(_poi_data),
            "message": "Overpass returned no POIs for this bounding box",
        }

    seen = {(poi.get("osm_id"), poi.get("category")) for poi in _poi_data}
    fresh: list[dict[str, Any]] = []
    for poi in pois:
        key = (poi.get("osm_id"), poi.get("category"))
        if key in seen:
            continue
        seen.add(key)  # dedupe within the incoming batch as well as against stored data
        fresh.append(poi)

    remaining = max(0, MAX_STORED_POIS - len(_poi_data))
    _poi_data.extend(fresh[:remaining])

    return {"ingested": len(fresh[:remaining]), "total": len(_poi_data)}


@router.get("/nearby")
async def nearby_pois(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    category: str = "",
    n: Annotated[int, Query(ge=1, le=50)] = 5,
    radius: Annotated[int, Query(ge=50, le=50_000)] = 5_000,
):
    """Return the nearest POIs within `radius` metres, optionally by category."""
    if not _poi_data:
        return {"nearby": [], "category_scores": {}, "message": "No POI data ingested"}

    # Filter first: taking the global nearest N and then filtering by category
    # can return an empty list even when matching POIs exist.
    category_pool = [
        poi for poi in _poi_data if not category or poi.get("category") == category
    ]
    if not category_pool:
        return {"nearby": [], "category_scores": {}, "message": "No POIs in that category"}

    # Distance-filter before slicing so a property outside the loaded area does
    # not "see" amenities hundreds of kilometres away.
    within_radius = [
        point
        for point in annotate_distances(category_pool, lat, lon)
        if point["distance_m"] <= radius
    ]
    within_radius.sort(key=lambda point: point["distance_m"])

    results = [
        {
            "name": point["name"],
            "category": point["category"],
            "distance_m": round(point["distance_m"], 1),
            "walk_time_min": max(1, round(point["distance_m"] / 80)),
            "decay_score": round(point["decay_score"], 3),
        }
        for point in within_radius[:n]
    ]

    return {
        "nearby": results,
        "category_scores": score_property(within_radius, lat, lon),
    }


@router.get("/health")
async def poi_health():
    return {
        "status": "ok",
        "total_pois": len(_poi_data),
        "ingest_auth": "enabled" if _expected_api_key() else "disabled",
    }
