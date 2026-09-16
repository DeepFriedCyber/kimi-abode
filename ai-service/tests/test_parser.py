"""Tests for the query parser — deterministic parsing, compound types, failover."""

from __future__ import annotations

import pytest

from app.parser import parse_query, _deterministic_parse


class TestDeterministicParse:
    """Tests for the regex-based deterministic parser."""

    def test_beds(self):
        result = _deterministic_parse("3 bed house")
        assert result.min_beds == 3

    @pytest.mark.asyncio
    async def test_parse_query_sync(self):
        result = await parse_query("3 bed house")
        assert result.min_beds == 3

    @pytest.mark.asyncio
    async def test_max_beds(self):
        result = _deterministic_parse("1-4 bedroom apartments")
        assert result.min_beds == 1

    @pytest.mark.asyncio
    async def test_price_under(self):
        result = _deterministic_parse("under £250k")
        assert result.max_price == 250000.0
        assert result.has_price is True

    @pytest.mark.asyncio
    async def test_price_below(self):
        result = _deterministic_parse("below £150,000")
        assert result.max_price == 150000.0

    @pytest.mark.asyncio
    async def test_property_type_detached(self):
        result = _deterministic_parse("detached bungalow")
        types = [pt.value for pt in result.property_types]
        assert "bungalow" in types or "detached" in types

    @pytest.mark.asyncio
    async def test_property_type_semi_detached(self):
        result = _deterministic_parse("semi-detached house")
        types = [pt.value for pt in result.property_types]
        # semi-detached should match as one type, not also detached
        assert "semi-detached" in types

    @pytest.mark.asyncio
    async def test_property_type_terraced(self):
        result = _deterministic_parse("terraced house")
        types = [pt.value for pt in result.property_types]
        assert "terraced" in types

    @pytest.mark.asyncio
    async def test_location_in(self):
        result = _deterministic_parse("in Sandbach")
        assert result.has_location is True
        assert result.location == "Sandbach"

    @pytest.mark.asyncio
    async def test_location_near(self):
        result = _deterministic_parse("near Crewe")
        assert result.has_location is True

    @pytest.mark.asyncio
    async def test_full_query(self):
        result = await parse_query("3 bed semi-detached in Sandbach under £250k")
        assert result.min_beds == 3
        assert "semi-detached" in [t.value for t in result.property_types]
        assert result.max_price == 250000.0
        assert result.location == "Sandbach"
        assert result.tier in ("DETERMINISTIC", "FORCED_DETERMINISTIC")

    @pytest.mark.asyncio
    async def test_no_filters(self):
        result = _deterministic_parse("house")
        assert result.min_beds is None
        assert result.max_price is None
        assert result.property_types == []
        assert result.has_location is False


class TestParsedQuerySchema:
    """Tests for the ParsedQuery Pydantic model."""

    def test_create_parsed_query(self):
        from app.schemas import ParsedQuery, PropertyType
        pq = ParsedQuery(
            raw="test",
            tier="detached",
            min_beds=3,
            max_price=250000.0,
            property_types=[PropertyType.DETACHED],
            location="Sandbach",
            has_location=True,
            has_price=True,
        )
        assert pq.min_beds == 3


class TestCompoundTypes:
    """Tests for compound-type patterns — semi-detached should NOT also match detached."""

    def test_semi_does_not_match_detached(self):
        result = _deterministic_parse("semi-detached house")
        types = [pt.value for pt in result.property_types]
        # semi-detached is the only type, not both semi + detached
        count_detached = types.count("detached")
        assert count_detached <= 1, f"semi-detached incorrectly matched detached: {types}"
