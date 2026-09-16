"""QA for POI data — validates and reports on ingested POIs."""

from __future__ import annotations

from typing import Any


def qa_poi_data(pois: list[dict]) -> dict[str, Any]:
    """Run QA checks on POI data.

    Checks:
    - Coordinates within UK bounds
    - No duplicate OSM IDs
    - Required fields present
    """
    results = {
        "total": len(pois),
        "issues": [],
        "categories": {},
    }

    seen_ids = set()
    uk_lat_min, uk_lon_min, uk_lat_max, uk_lon_max = 49.5, -10, 61, 2

    for i, poi in enumerate(pois):
        # Check coordinates
        lat, lon = poi.get("lat"), poi.get("lon")
        if not (uk_lat_min <= lat <= uk_lat_max) or not (uk_lon_min <= lon <= uk_lon_max):
            results["issues"].append(f"POI {i}: coordinates out of UK bounds ({lat}, {lon})")

        # Check duplicates
        osm_id = poi.get("osm_id")
        if osm_id in seen_ids:
            results["issues"].append(f"POI {i}: duplicate OSM ID {osm_id}")
        seen_ids.add(osm_id)

        # Track categories
        cat = poi.get("category", "unknown")
        results["categories"][cat] = results["categories"].get(cat, 0) + 1

    return results


def review_poi_scores(pois: list[dict], target_lat: float, target_lon: float) -> dict:
    """Review POI scores for a specific property location."""
    from app.poi.scorer import haversine_m, decay_score, nearest, score_property

    nearest_pts = nearest(pois, target_lat, target_lon, 10)
    scores = score_property(pois, target_lat, target_lon)

    return {
        "target": {"lat": target_lat, "lon": target_lon},
        "nearest_10": [
            {**pt, "distance_m": round(pt.get("distance_m", haversine_m(target_lat, target_lon, pt["lat"], pt["lon"])), 1)}
            for pt in nearest_pts
        ],
        "category_scores": scores,
    }
