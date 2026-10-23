"""Overpass integration — fetch POIs from OpenStreetMap.

Public Overpass instances go down or rate-limit regularly, so requests fail over
across a configurable list. A successful endpoint becomes the preferred one for
subsequent queries.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINTS = [
    # osm.ch is deliberately excluded: it only carries Swiss data, so UK queries
    # return an empty result rather than an error (worse than failing).
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def _configured_endpoints() -> list[str]:
    single = os.getenv("OVERPASS_URL", "").strip()
    if single:
        return [single]

    configured = os.getenv("OVERPASS_ENDPOINTS", "").strip()
    if configured:
        endpoints = [item.strip() for item in configured.split(",") if item.strip()]
        if endpoints:
            return endpoints

    return DEFAULT_ENDPOINTS


ENDPOINTS = _configured_endpoints()
_preferred_endpoint = 0

# Overpass queries are wrapped in single quotes so the JSON selectors can keep
# their double quotes (a previous version produced a SyntaxError).
OVERPASS_QUERIES: dict[str, str] = {
    "restaurant": '[out:json][timeout:25];(node["amenity"="restaurant"]({bbox});way["amenity"="restaurant"]({bbox}););out center 1500;',
    "pub": '[out:json][timeout:25];(node["amenity"="pub"]({bbox});way["amenity"="pub"]({bbox}););out center 1500;',
    "school": '[out:json][timeout:25];(node["amenity"="school"]({bbox});way["amenity"="school"]({bbox}););out center 1500;',
    "supermarket": '[out:json][timeout:25];(node["shop"="supermarket"]({bbox});way["shop"="supermarket"]({bbox}););out center 1500;',
    "hospital": '[out:json][timeout:25];(node["amenity"="hospital"]({bbox});way["amenity"="hospital"]({bbox}););out center 1500;',
    "station": '[out:json][timeout:25];(node["railway"="station"]({bbox});way["railway"="station"]({bbox}););out center 1500;',
}

USER_AGENT = "AbodeAI/0.1 (property search POI enrichment)"


def _format_bbox(bbox: tuple[float, float, float, float]) -> str:
    """Overpass expects (south, west, north, east)."""
    lat_min, lon_min, lat_max, lon_max = bbox
    return f"{lat_min},{lon_min},{lat_max},{lon_max}"


async def fetch_pois(
    bbox: tuple[float, float, float, float],
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch POIs for the given bounding box, one request per category."""
    bbox_str = _format_bbox(bbox)
    cats = categories or list(OVERPASS_QUERIES.keys())

    import aiohttp

    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=45),
        headers={"User-Agent": USER_AGENT},
    ) as session:
        endpoint = await _select_endpoint(session, bbox_str, cats[0])
        if endpoint is None:
            return []

        results = await asyncio.gather(
            *(fetch_category(session, endpoint, bbox_str, category) for category in cats),
            return_exceptions=True,
        )

    pois: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("[Overpass] category fetch failed: %s", result)
            continue
        pois.extend(result)
    return pois


def _endpoint_order() -> list[str]:
    """Preferred endpoint first, then the rest."""
    return (
        [ENDPOINTS[_preferred_endpoint]]
        + [endpoint for index, endpoint in enumerate(ENDPOINTS) if index != _preferred_endpoint]
    )


async def _post_query(session: Any, endpoint: str, query: str, timeout_secs: float) -> dict | None:
    """POST an Overpass query, returning parsed JSON or None on failure."""
    import aiohttp

    try:
        async with session.post(
            endpoint,
            data={"data": query},
            timeout=aiohttp.ClientTimeout(total=timeout_secs),
        ) as response:
            if response.status != 200:
                logger.warning("[Overpass] HTTP %s from %s", response.status, endpoint)
                return None
            payload = await response.json(content_type=None)
    except Exception as exc:  # noqa: BLE001 - caller handles failover
        logger.warning("[Overpass] request to %s failed: %s", endpoint, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("[Overpass] non-JSON response from %s", endpoint)
        return None
    return payload


async def _select_endpoint(session: Any, bbox_str: str, category: str) -> str | None:
    """Probe endpoints once so a dead instance costs one short timeout, not N."""
    template = OVERPASS_QUERIES.get(category)
    if not template:
        category, template = next(iter(OVERPASS_QUERIES.items()))

    query = template.format(bbox=bbox_str)
    for endpoint in _endpoint_order():
        payload = await _post_query(session, endpoint, query, timeout_secs=12)
        if payload is not None:
            try:
                _preferred_endpoint = ENDPOINTS.index(endpoint)
            except ValueError:
                pass
            return endpoint

    logger.error("[Overpass] no reachable endpoint (tried %s)", ", ".join(ENDPOINTS))
    return None


async def fetch_category(session: Any, endpoint: str, bbox_str: str, category: str) -> list[dict[str, Any]]:
    """Fetch one category, failing over to other endpoints if needed."""
    template = OVERPASS_QUERIES.get(category)
    if not template:
        return []

    query = template.format(bbox=bbox_str)
    order = [endpoint] + [item for item in _endpoint_order() if item != endpoint]

    for candidate in order:
        payload = await _post_query(session, candidate, query, timeout_secs=25)
        if payload is not None:
            return _parse_elements(payload, category)

    return []


def _parse_elements(payload: dict, category: str) -> list[dict[str, Any]]:
    pois: list[dict[str, Any]] = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {}) or {}
        center = element.get("center") or {}
        latitude = center.get("lat", element.get("lat"))
        longitude = center.get("lon", element.get("lon"))
        if latitude is None or longitude is None:
            continue

        pois.append(
            {
                "name": tags.get("name") or tags.get("alt_name") or category.title(),
                "osm_id": element.get("id"),
                "lat": float(latitude),
                "lon": float(longitude),
                "category": category,
            }
        )
    return pois
