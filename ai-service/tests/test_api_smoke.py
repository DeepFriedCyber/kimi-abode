"""Parser edge cases and API smoke tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.parser import _deterministic_parse


class TestParserEdges:
    def test_location_keyword_needs_a_word_boundary(self):
        # "within" must not be treated as the keyword "in".
        result = _deterministic_parse("3 bed within Sandbach")
        assert result.location == "Sandbach"

    def test_location_before_filters(self):
        result = _deterministic_parse("in Sandbach 3 bed under 300k")
        assert result.location == "Sandbach"
        assert result.min_beds == 3
        assert result.max_price == 300000

    def test_keyword_does_not_pull_in_price_words(self):
        result = _deterministic_parse("2 bed flat in Crewe under £150k")
        assert result.location == "Crewe"
        assert result.max_price == 150000

    def test_bed_range_sets_min_and_max(self):
        result = _deterministic_parse("1-4 bedroom apartments")
        assert (result.min_beds, result.max_beds) == (1, 4)

    def test_bare_price_is_a_budget(self):
        result = _deterministic_parse("detached £250k")
        assert result.max_price == 250000
        assert result.has_price is True

    def test_implausible_price_is_ignored(self):
        result = _deterministic_parse("under £5")
        assert result.max_price is None

    def test_outcode_falls_back_to_gazetteer(self):
        result = _deterministic_parse("3 bed CW11 1JD")
        assert result.outcode == "CW11"
        assert result.location == "Sandbach"

    def test_semi_detached_is_not_also_detached(self):
        result = _deterministic_parse("semi-detached house")
        values = [t.value for t in result.property_types]
        assert values == ["semi-detached"]

    def test_empty_query_has_no_filters(self):
        result = _deterministic_parse("")
        assert result.min_beds is None and result.max_price is None
        assert result.location is None


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module", autouse=True)
def isolated_agent_store(tmp_path_factory):
    """Keep agent uploads from local runs out of these assertions."""
    import app.ingestion.agent_store as store_module
    from app.routers import listings as listings_router

    store = store_module.ListingStore(
        tmp_path_factory.mktemp("agent-store") / "agent_listings.json"
    )
    original_module_store = store_module.listing_store
    original_router_store = listings_router.listing_store

    store_module.listing_store = store
    listings_router.listing_store = store
    try:
        yield store
    finally:
        store_module.listing_store = original_module_store
        listings_router.listing_store = original_router_store


class TestApiSmoke:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "db" in body

    def test_parse_endpoint(self, client):
        response = client.post("/parse", json={"query": "3 bed semi in Sandbach under £250k"})
        assert response.status_code == 200
        body = response.json()
        assert body["min_beds"] == 3
        assert body["max_price"] == 250000
        assert body["location"] == "Sandbach"

    def test_parse_rejects_empty_query(self, client):
        assert client.post("/parse", json={"query": ""}).status_code == 422

    def test_search_without_database_serves_demo_fixture(self, client):
        response = client.get("/search", params={"query": "3 bed in Sandbach"})
        assert response.status_code == 200
        body = response.json()
        assert body["tier_used"] == "deterministic-demo"
        assert body["properties"]
        assert body["total_matches"] >= len(body["properties"])
        first = body["properties"][0]
        assert "embedding" not in first
        assert first["floor_area_sqm"] is not None
        assert first["latitude"] is not None

    def test_filter_by_property_type(self, client):
        # The AI service takes `property_types` (repeatable); the gateway maps
        # the public `property_type` parameter onto it.
        response = client.get(
            "/search", params={"query": "in Sandbach", "property_types": ["bungalow"]}
        )
        assert response.status_code == 200
        assert all(p["property_type"] == "bungalow" for p in response.json()["properties"])

    def test_filter_by_max_price(self, client):
        response = client.get(
            "/search", params={"query": "in Crewe", "max_price": 150000, "limit": 10}
        )
        assert response.status_code == 200
        assert all(p["price_paid"] <= 150000 for p in response.json()["properties"])

    def test_search_rejects_inverted_bed_range(self, client):
        response = client.get("/search", params={"query": "house", "min_beds": 5, "max_beds": 2})
        assert response.status_code == 400

    def test_search_accepts_filters_without_a_query(self, client):
        # A filter-only browse is legitimate: the UI chips send no free text.
        response = client.get("/search", params={"location": "Sandbach", "min_beds": 3})
        assert response.status_code == 200
        assert response.json()["properties"]

    def test_property_always_includes_a_photos_list(self, client):
        # Sold records have no photos, but the response shape must not change.
        body = client.get("/property", params={"id": 1}).json()
        assert body["photos"] == []

    def test_property_served_from_fixture_without_database(self, client):
        response = client.get("/property", params={"id": 1})
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 1
        assert body["postcode"]
        assert body["latitude"] is not None
        assert body["floor_area_sqm"] is not None

    def test_property_not_found_in_fixture(self, client):
        assert client.get("/property", params={"id": 999_999}).status_code == 404

    def test_merge_results_prefers_live_and_dedupes(self):
        from app.main import _merge_results

        live = [{"id": 1, "address_line1": "A Road", "postcode": "CW1 1AA", "asking_price": 1}]
        sold = [
            {"id": 2, "address_line1": "A Road", "postcode": "CW1 1AA", "price_paid": 2},
            {"id": 3, "address_line1": "B Road", "postcode": "CW1 1AB", "price_paid": 3},
        ]

        merged = _merge_results(live, sold, limit=10)
        assert [row["id"] for row in merged] == [1, 3]
    def test_property_rejects_invalid_id(self, client):
        assert client.get("/property", params={"id": 0}).status_code == 422

    def test_poi_nearby_uses_the_loaded_extract_cache(self, client):
        response = client.get(
            "/poi/nearby", params={"lat": 53.097675, "lon": -2.405048, "n": 5}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["nearby"], "expected amenities from data/poi_cache.json"
        first = body["nearby"][0]
        assert first["distance_m"] <= 5_000
        assert first["walk_time_min"] >= 1
        assert isinstance(body["category_scores"], dict)

    def test_poi_nearby_outside_the_loaded_area_is_empty(self, client):
        response = client.get("/poi/nearby", params={"lat": 0, "lon": 0})
        assert response.status_code == 200
        assert response.json()["nearby"] == []

    def test_poi_radius_is_respected(self, client):
        tight = client.get(
            "/poi/nearby",
            params={"lat": 53.097675, "lon": -2.405048, "radius": 100, "n": 50},
        )
        wide = client.get(
            "/poi/nearby",
            params={"lat": 53.097675, "lon": -2.405048, "radius": 5_000, "n": 50},
        )
        assert len(tight.json()["nearby"]) <= len(wide.json()["nearby"])
        assert all(p["distance_m"] <= 100 for p in tight.json()["nearby"])

    def test_poi_rejects_out_of_range_coordinates(self, client):
        assert client.get("/poi/nearby", params={"lat": 95, "lon": 0}).status_code == 422

    def test_chat_falls_back_without_api_key(self, client):
        response = client.post(
            "/chat/chat", json={"messages": [{"role": "user", "content": "hello"}]}
        )
        assert response.status_code == 200
        assert response.json()["has_llm"] is False

    def test_chat_stream_emits_sse_frames(self, client):
        response = client.post(
            "/chat/chat/stream",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "data: " in response.text
        assert "[DONE]" in response.text

    def test_chat_rejects_empty_messages(self, client):
        assert client.post("/chat/chat", json={"messages": []}).status_code == 422


class TestAreaQuestions:
    def test_nearest_supermarket(self, client):
        response = client.get("/property/1/nearby", params={"q": "nearest supermarket"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["property_id"] == 1
        assert body["results"], "expected amenities from data/poi_cache.json"
        assert body["results"][0]["distance_m"] > 0
        assert body["results"][0]["walk_time_min"] >= 1
        assert "m" in body["answer"]
        assert body["attribution"].startswith("© OpenStreetMap")
        assert body["distance_type"] == "straight_line"

    def test_brand_question(self, client):
        body = client.get(
            "/property/1/nearby", params={"q": "how far is the nearest Tesco?"}
        ).json()

        assert body["intent"]["brand"] == "tesco"
        assert body["results"]
        assert body["results"][0]["map_url"].startswith("https://www.openstreetmap.org/")

    def test_gym_question(self, client):
        body = client.get(
            "/property/1/nearby", params={"q": "what gyms are nearby?"}
        ).json()

        assert body["results"]
        assert all(item["category"] == "fitness" for item in body["results"])

    def test_primary_school_question(self, client):
        body = client.get(
            "/property/1/nearby", params={"q": "primary schools within 3 km"}
        ).json()

        assert body["results"]
        assert all(item["category"] == "school" for item in body["results"])

    def test_non_amenity_question(self, client):
        response = client.get("/property/1/nearby", params={"q": "what is stamp duty?"})

        assert response.status_code == 422
        assert "examples" in response.json()

    def test_unknown_property(self, client):
        response = client.get("/property/999999/nearby", params={"q": "nearest park"})
        assert response.status_code == 404

    def test_property_without_coordinates(self, client, isolated_agent_store):
        isolated_agent_store.upsert_many(
            [
                {
                    "address_line1": "No Coords Road",
                    "postcode": "CW11 1JD",
                    "asking_price": 200000,
                }
            ],
            "acme",
        )
        listing_id = isolated_agent_store.all_listings()[0]["id"]

        response = client.get(f"/property/{listing_id}/nearby", params={"q": "nearest park"})
        assert response.status_code == 422
        assert "coordinates" in response.json()["error"]

    def test_chat_answers_amenity_question_without_llm(self, client):
        response = client.post(
            "/chat/chat",
            json={
                "messages": [
                    {"role": "user", "content": "how far is the nearest supermarket?"}
                ],
                "property_id": 1,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["has_llm"] is False
        assert "supermarket" in body["response"].lower()
