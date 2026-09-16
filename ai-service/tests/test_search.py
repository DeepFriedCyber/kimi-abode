"""Tests for the search module — hybrid search, location queries."""

from __future__ import annotations

import pytest


class TestSearchLocation:
    """Tests for location-based search."""

    @pytest.mark.asyncio
    async def test_search_location_no_pool(self):
        from app.search import search_location

        result = await search_location("Sandbach")
        assert "total_matches" in result
        assert result["properties"] == []


class TestSearchQuery:
    """Tests for query-based search."""

    @pytest.mark.asyncio
    async def test_search_basic(self):
        from app.search import search

        result = await search("3 bed detached under £300k")
        assert "tier_used" in result
        assert "message" in result


@pytest.mark.asyncio
class TestParserAndSearchIntegration:
    """Integration: parse → search flow."""

    async def test_parse_returns_valid_result(self):
        from app.parser import parse_query

        result = await parse_query("2 bed flat in Manchester under £100k")
        assert result.min_beds == 2
        assert "flat" in [t.value for t in result.property_types]
        assert result.location is not None or result.has_location is True


@pytest.mark.asyncio
class TestSearchEdgeCases:
    """Tests for edge cases in search."""

    async def test_empty_query(self):
        from app.parser import parse_query

        result = await parse_query("")
        assert result.min_beds is None
        assert result.max_price is None

    async def test_price_including_k_suffix(self):
        from app.parser import parse_query

        result = await parse_query("under £150k")
        assert result.max_price == 150000.0

    async def test_price_without_suffix(self):
        from app.parser import parse_query

        result = await parse_query("under £150000")
        assert result.max_price == 150000.0
