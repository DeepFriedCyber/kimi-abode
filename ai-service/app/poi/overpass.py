"""Overpass integration — fetch POIs from OpenStreetMap's Overpass API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Common Overpass queries for UK POI categories.
OVERPASS_QUERIES: dict[str, str] = {
    "restaurant": "[out:json];(node["amenity"="restaurant"](bbox);way["amenity"="restaurant"](bbox););out center;",
    "pub": '[out:json];(node["amenity"="pub"](bbox);way["amenity"="pub"](bbox););out center;',
    "school": '[out:json];(node["amenity"="school"](bbox);way["amenity"="school"](bbox););out center;',
    "supermarket": '[out:json];(node["shop"="supermarket"](bbox);way["shop"="supermarket"](bbox););out center;',
    "hospital": '[out:json];(node["amenity"="hospital"](bbox);way["amenity"="hospital"](bbox););out center;',
    "station": '[out:json];(node["railway"="station"](bbox);way["railway"="station"](bbox););out center;',
}


async def fetch_pois(bbox: tuple[float, float, float, float], categories: list[str] | None = None) -> list[dict]:
    """Fetch POIs from Overpass API for the given bounding box."""
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    cats = categories or list(OVERPASS_QUERIES.keys())

    all_pois = []
    tasks = [fetch_category(bbox_str, cat) for cat in cats]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            continue
        all_pois.extend(result)

    return all_pois


async def fetch_category(bbox_str: str, category: str) -> list[dict]:
    """Fetch a single POI category from Overpass."""
    import aiohttp

    query = OVERPASS_QUERIES.get(category, "")
    if not query:
        return []

    try:
        async with aiohttp.ClientSession() as session:
            params = {"data": query}
            async with session.post(OVERPASS_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                return [
                    {
                        "name": elem.get("tags", {}).get("name", elem.get("tags", {}).get("alt_name", "")),
                        "osm_id": elem.get("id"),
                        "lat": elem["center"]["lat"] if "center" in elem else (elem.get("lat") or 0),
                        "lon": elem["center"]["lon"] if "center" in elem else (elem.get("lon") or 0),
                        "category": category,
                    }
                    for elem in data.get("elements", [])
                ]
    except Exception:
        return []
