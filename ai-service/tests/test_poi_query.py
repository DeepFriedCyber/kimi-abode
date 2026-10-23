"""Amenity question tests — intent parsing, brand matching, answers."""

from __future__ import annotations

import pytest

from app.poi.query import (
    answer_poi_question,
    detect_brand,
    format_distance,
    normalise,
    parse_poi_query,
    parse_radius,
)


def poi(name: str, category: str, lat: float, lon: float, **extra) -> dict:
    return {"name": name, "category": category, "lat": lat, "lon": lon, **extra}


# Coordinates roughly 100 m per 0.0009° latitude.
BASE_LAT, BASE_LON = 53.1000, -2.4000
POIS = [
    poi("Tesco Extra", "supermarket", 53.1200, -2.4000, brand="Tesco Extra", street="Vernon Way"),
    poi("Tesco Express", "convenience", 53.1020, -2.4000, brand="Tesco Express"),
    poi("ALDI", "supermarket", 53.1059, -2.4000, brand="ALDI", street="University Way"),
    poi("PureGym", "fitness", 53.1082, -2.4000, brand="PureGym", subtype="gym"),
    poi("Sandbach Cricket Club", "fitness", 53.1036, -2.4000, subtype="sports_centre"),
    poi("Haslington Primary Academy", "school", 53.1060, -2.4000, isced_level="1"),
    poi("Sir William Stanier School", "school", 53.1176, -2.4000, isced_level="2"),
    poi("Rowlands Pharmacy", "pharmacy", 53.1061, -2.4000),
    poi("Queens Park", "park", 53.1025, -2.4000),
    poi("Crewe", "station", 53.1187, -2.4000, brand="Avanti West Coast", street="Nantwich Road"),
]


class TestFormatDistance:
    """UK imperial display: yards up close, then miles."""

    def test_short_distances_use_yards(self):
        assert format_distance(100) == "110 yards"
        assert format_distance(150) == "160 yards"

    def test_single_mile_is_not_pluralised(self):
        assert format_distance(1_609.344) == "1 mile"
        assert format_distance(1_650) == "1 mile"

    def test_miles_one_decimal_under_ten(self):
        assert format_distance(2_000) == "1.2 miles"
        assert format_distance(4_000) == "2.5 miles"

    def test_whole_miles_drop_the_decimal(self):
        assert format_distance(3_218.688) == "2 miles"
        assert format_distance(4_828.032) == "3 miles"

    def test_miles_whole_numbers_beyond_ten(self):
        assert format_distance(16_093.44) == "10 miles"
        assert format_distance(24_140) == "15 miles"

    def test_never_reports_metres_or_km(self):
        for metres in (50, 220, 655, 1_500, 5_000, 20_000):
            text = format_distance(metres)
            assert "km" not in text
            assert not text.endswith(" m")
            assert "metre" not in text


class TestParsing:
    def test_brand_and_category(self):
        query = parse_poi_query("How far is the nearest Tesco superstore?")
        assert query is not None
        assert query.brand == "tesco"
        assert query.category == "supermarket"
        assert query.limit == 1

    def test_plural_gyms(self):
        query = parse_poi_query("What gyms are nearby?")
        assert query is not None
        assert query.category == "fitness"
        assert query.limit == 5

    def test_radius(self):
        assert parse_radius(normalise("within 2 km")) == 2_000
        assert parse_radius(normalise("within 500 m")) == 500
        assert parse_radius(normalise("within 1 mile")) == 1_609
        assert parse_radius(normalise("nearby")) == 5_000

    def test_brand_aliases(self):
        assert detect_brand(normalise("sainsbury's local")) == "sainsburys"
        assert detect_brand(normalise("m&s food")) == "marksandspencer"
        assert detect_brand(normalise("the gym group")) == "gymgroup"

    def test_non_amenity_question(self):
        assert parse_poi_query("What is stamp duty on a £400,000 house?") is None
        assert answer_poi_question(POIS, BASE_LAT, BASE_LON, "Tell me about the seller") is None

    def test_primary_school_intent(self):
        query = parse_poi_query("Primary schools within 2 km")
        assert query is not None
        assert query.category == "school"
        assert query.radius_m == 2_000


class TestAnswers:
    def test_nearest_brand(self):
        result = answer_poi_question(POIS, BASE_LAT, BASE_LON, "How far is the nearest Tesco?")
        assert result is not None
        assert result["intent"]["brand"] == "tesco"
        assert result["results"][0]["name"] == "Tesco Express"  # ~220 m vs ~2.2 km
        assert "Tesco Express" in result["answer"]
        assert "0.1 miles" in result["answer"]
        assert result["attribution"] == "© OpenStreetMap contributors"
        assert result["distance_type"] == "straight_line"

    def test_superstore_prefers_full_supermarket(self):
        result = answer_poi_question(
            POIS, BASE_LAT, BASE_LON, "nearest Tesco superstore"
        )
        assert result is not None
        assert result["results"][0]["name"] == "Tesco Extra"

    def test_gyms_exclude_cricket_clubs(self):
        result = answer_poi_question(POIS, BASE_LAT, BASE_LON, "what gyms are nearby?")
        names = [item["name"] for item in result["results"]]
        assert names == ["PureGym"]

    def test_nearest_supermarket(self):
        result = answer_poi_question(POIS, BASE_LAT, BASE_LON, "nearest supermarket")
        assert result["results"][0]["name"] == "ALDI"
        assert "0.4 miles" in result["answer"]

    def test_brand_fallback_to_category(self):
        result = answer_poi_question(POIS, BASE_LAT, BASE_LON, "nearest Waitrose")
        assert result["fallback"] is not None
        assert "no Waitrose" in result["fallback"]
        assert result["results"][0]["name"] == "ALDI"
        assert "nearest supermarket is ALDI" in result["answer"]
        assert "nearest Waitrose is ALDI" not in result["answer"]

    def test_primary_filter_excludes_secondary(self):
        result = answer_poi_question(POIS, BASE_LAT, BASE_LON, "primary schools within 2 km")
        names = [item["name"] for item in result["results"]]
        assert "Haslington Primary Academy" in names
        assert "Sir William Stanier School" not in names

    def test_no_results(self):
        result = answer_poi_question(POIS, 51.5, -0.1, "nearest Tesco")
        assert result is not None
        assert result["results"] == []
        assert "couldn't find" in result["answer"]

    def test_plural_answer_lists_results(self):
        result = answer_poi_question(POIS, BASE_LAT, BASE_LON, "what supermarkets are nearby?")
        assert result["total_matches"] >= 2
        assert "I found" in result["answer"]

    def test_walk_time_and_map_link(self):
        result = answer_poi_question(POIS, BASE_LAT, BASE_LON, "nearest pharmacy")
        first = result["results"][0]
        assert first["walk_time_min"] >= 1
        assert first["map_url"].startswith("https://www.openstreetmap.org/")
