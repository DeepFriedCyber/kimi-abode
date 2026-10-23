"""Local OSM extract tests (tag mapping, bbox filtering, tiny PBF round-trip)."""

from __future__ import annotations

import pytest

from app.poi.osm_extract import (
    build_pois_from_pbf,
    categorize,
    centroid,
    dedupe,
    in_bbox,
)


class TestCategorise:
    def test_amenities(self):
        assert categorize({"amenity": "school"}) == "school"
        assert categorize({"amenity": "pub"}) == "pub"
        assert categorize({"amenity": "hospital"}) == "hospital"
        assert categorize({"amenity": "restaurant"}) == "restaurant"
        assert categorize({"amenity": "cafe"}) == "cafe"
        assert categorize({"amenity": "pharmacy"}) == "pharmacy"
        assert categorize({"amenity": "kindergarten"}) == "nursery"
        assert categorize({"amenity": "doctors"}) == "doctors"

    def test_leisure_and_convenience(self):
        assert categorize({"leisure": "fitness_centre"}) == "fitness"
        assert categorize({"leisure": "park"}) == "park"
        assert categorize({"shop": "convenience"}) == "convenience"

    def test_subtypes(self):
        from app.poi.osm_extract import subtype

        assert subtype({"leisure": "fitness_centre"}) == "gym"
        assert subtype({"leisure": "sports_centre"}) == "sports_centre"
        assert subtype({"amenity": "gym"}) == "gym"
        assert subtype({"amenity": "school"}) is None

    def test_shops_and_stations(self):
        assert categorize({"shop": "supermarket"}) == "supermarket"
        assert categorize({"railway": "station"}) == "station"

    def test_ignores_unrelated_tags(self):
        assert categorize({"highway": "residential"}) is None
        assert categorize({"shop": "bakery"}) is None


class TestGeometry:
    def test_bbox_is_inclusive(self):
        bbox = (53.0, -2.5, 53.2, -2.3)
        assert in_bbox(53.0, -2.5, bbox)
        assert in_bbox(53.1, -2.4, bbox)
        assert not in_bbox(53.3, -2.4, bbox)
        assert not in_bbox(53.1, -2.6, bbox)

    def test_centroid(self):
        assert centroid([]) is None
        assert centroid([(53.0, -2.0), (53.2, -2.4)]) == pytest.approx((53.1, -2.2))

    def test_dedupe(self):
        pois = [
            {"osm_id": 1, "category": "school"},
            {"osm_id": 1, "category": "school"},
            {"osm_id": 1, "category": "pub"},
        ]
        assert len(dedupe(pois)) == 2


@pytest.mark.asyncio
async def test_reads_a_real_pbf(tmp_path):
    """Build a tiny .osm.pbf with pyosmium and read it back."""
    osmium = pytest.importorskip("osmium")

    path = tmp_path / "tiny.osm.pbf"
    writer = osmium.SimpleWriter(str(path))

    def node(osm_id: int, lat: float, lon: float, tags: dict) -> None:
        writer.add_node(
            osmium.osm.mutable.Node(id=osm_id, location=(lon, lat), tags=tags)
        )

    node(1, 53.10, -2.40, {"amenity": "school", "name": "Inside School"})
    node(2, 54.00, -2.40, {"amenity": "school", "name": "Outside School"})
    node(3, 53.11, -2.41, {"shop": "supermarket"})
    node(4, 53.12, -2.42, {"highway": "crossing"})
    writer.close()

    pois = build_pois_from_pbf(str(path), (53.0, -2.5, 53.2, -2.3))

    names = {poi["name"] for poi in pois}
    assert "Inside School" in names
    assert "Outside School" not in names
    assert any(poi["category"] == "supermarket" for poi in pois)
    assert all(poi["category"] != "crossing" for poi in pois)
