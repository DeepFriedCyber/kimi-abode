"""Build POIs from a local OpenStreetMap extract (.osm.pbf).

This is the offline alternative to querying Overpass at runtime: stream a
regional extract once with pyosmium, keep the amenities inside the demo
bounding box, and write the same cache format the service already loads.

Extract source (221 MB, covers Cheshire East):
    https://download.openstreetmap.fr/extracts/europe/united_kingdom/england/north_west.osm.pbf
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

BBox = tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)

# amenity -> category, plus special cases below.
AMENITY_CATEGORIES = {
    "restaurant": "restaurant",
    "pub": "pub",
    "bar": "bar",
    "cafe": "cafe",
    "school": "school",
    "kindergarten": "nursery",
    "hospital": "hospital",
    "doctors": "doctors",
    "clinic": "doctors",
    "pharmacy": "pharmacy",
    "dentist": "dentist",
    "gym": "fitness",
}

SHOP_CATEGORIES = {
    "supermarket": "supermarket",
    "convenience": "convenience",
}

LEISURE_CATEGORIES = {
    "fitness_centre": "fitness",
    "sports_centre": "fitness",
    "park": "park",
    "playground": "playground",
}

RAILWAY_CATEGORIES = {
    "station": "station",
    "halt": "station",
    "tram_stop": "station",
}


def categorize(tags: dict[str, str] | Any) -> str | None:
    """Map OSM tags onto the categories the UI understands."""
    amenity = tags.get("amenity")
    if amenity in AMENITY_CATEGORIES:
        return AMENITY_CATEGORIES[amenity]

    shop = tags.get("shop")
    if shop in SHOP_CATEGORIES:
        return SHOP_CATEGORIES[shop]

    leisure = tags.get("leisure")
    if leisure in LEISURE_CATEGORIES:
        return LEISURE_CATEGORIES[leisure]

    railway = tags.get("railway")
    if railway in RAILWAY_CATEGORIES:
        return RAILWAY_CATEGORIES[railway]

    return None


def subtype(tags: dict[str, str] | Any) -> str | None:
    """Refine broad categories (e.g. a cricket club is not a gym)."""
    if tags.get("amenity") == "gym" or tags.get("leisure") == "fitness_centre":
        return "gym"
    if tags.get("leisure") == "sports_centre":
        return "sports_centre"
    if tags.get("amenity") == "clinic":
        return "clinic"
    return None


def in_bbox(lat: float, lon: float, bbox: BBox) -> bool:
    min_lat, min_lon, max_lat, max_lon = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def centroid(locations: Iterable[tuple[float, float]]) -> tuple[float, float] | None:
    """Average valid coordinates; used for ways (building footprints)."""
    points = list(locations)
    if not points:
        return None
    return (
        sum(lat for lat, _ in points) / len(points),
        sum(lon for _, lon in points) / len(points),
    )


def build_pois_from_pbf(path: str, bbox: BBox) -> list[dict[str, Any]]:
    """Stream an .osm.pbf and return amenities inside `bbox`.

    Requires `osmium` (pyosmium). Raises ImportError with a helpful message when
    it is not installed.
    """
    try:
        import osmium
    except ImportError as exc:  # pragma: no cover - dependency error path
        raise ImportError(
            "pyosmium is required for local extracts: pip install osmium"
        ) from exc

    class Handler(osmium.SimpleHandler):
        def __init__(self) -> None:
            super().__init__()
            self.pois: list[dict[str, Any]] = []

        def _add(self, osm_id: int, tags: Any, lat: float, lon: float) -> None:
            category = categorize(tags)
            if category is None or not in_bbox(lat, lon, bbox):
                return
            self.pois.append(
                {
                    "name": tags.get("name") or tags.get("alt_name") or category.title(),
                    "osm_id": osm_id,
                    "lat": lat,
                    "lon": lon,
                    "category": category,
                    "subtype": subtype(tags),
                    "brand": tags.get("brand") or tags.get("operator") or None,
                    "opening_hours": tags.get("opening_hours") or None,
                    "website": tags.get("website") or tags.get("contact:website") or None,
                    "street": tags.get("addr:street") or None,
                    "wheelchair": tags.get("wheelchair") or None,
                    "isced_level": tags.get("isced:level") or None,
                }
            )

        def node(self, node) -> None:  # noqa: ANN001 - pyosmium types
            if not node.tags:
                return
            self._add(node.id, node.tags, node.location.lat, node.location.lon)

        def way(self, way) -> None:  # noqa: ANN001
            if not way.tags or categorize(way.tags) is None:
                return

            points = []
            for node_ref in way.nodes:
                try:
                    location = node_ref.location
                except Exception:  # noqa: BLE001 - location unavailable
                    continue
                if location.valid():
                    points.append((location.lat, location.lon))

            centre = centroid(points)
            if centre:
                self._add(way.id, way.tags, centre[0], centre[1])

    handler = Handler()
    # locations=True populates node references for ways (needed for centroids).
    handler.apply_file(path, locations=True)
    logger.info("[OSM] %s POIs found in bbox %s", len(handler.pois), bbox)
    return handler.pois


def dedupe(pois: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate (osm_id, category) pairs."""
    unique: dict[tuple, dict[str, Any]] = {}
    for poi in pois:
        unique.setdefault((poi.get("osm_id"), poi.get("category")), poi)
    return list(unique.values())
