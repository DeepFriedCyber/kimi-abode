"""SQL builder regression tests — parameter indexes, filters, totals.

These cover the bug where `LIMIT ${embed_limit}` emitted `LIMIT $60` (a number
used as a parameter index), which made every vector search raise.
"""

from __future__ import annotations

import pytest

from app.repository import _build_where_clause, execute_search_pg
from app.schemas import ParsedQuery, PropertyType


class FakeConnection:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.fetchval_calls: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *params):
        self.fetch_calls.append((sql, params))
        return []

    async def fetchval(self, sql: str, *params):
        self.fetchval_calls.append((sql, params))
        return 7


class FakeAcquire:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *args) -> None:
        return None


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.connection)


def query(**kwargs) -> ParsedQuery:
    return ParsedQuery(raw="test", tier="deterministic", **kwargs)


class TestWhereClause:
    def test_no_filters_is_true(self):
        where, params = _build_where_clause(query(), None)
        assert where == "TRUE"
        assert params == []

    def test_outcode_only_does_not_match_everything(self):
        where, params = _build_where_clause(query(outcode="CW11"), None)
        assert "town" not in where
        assert "outcode ILIKE" in where
        assert params == ["%CW11%"]

    def test_property_types_become_an_array_parameter(self):
        where, params = _build_where_clause(
            query(property_types=[PropertyType.DETACHED, PropertyType.FLAT]), None
        )
        assert "property_type = ANY($1::text[])" in where
        assert params == [["detached", "flat"]]

    def test_wildcards_in_input_are_escaped(self):
        where, params = _build_where_clause(query(location="100%_safe"), None)
        assert "ESCAPE" in where
        assert params == ["%100\\%\\_safe%"]

    def test_bed_range(self):
        where, params = _build_where_clause(query(min_beds=2, max_beds=4), None)
        assert "num_beds >= $1" in where
        assert "num_beds <= $2" in where
        assert params == [2, 4]


class TestExecuteSearchPg:
    @pytest.mark.asyncio
    async def test_limit_and_offset_use_their_own_parameters(self):
        pool = FakePool()
        await execute_search_pg(pool, query(), "test", None, limit=10, offset=20)

        sql, params = pool.connection.fetch_calls[0]
        assert "LIMIT $1 OFFSET $2" in sql
        assert params == (10, 20)

    @pytest.mark.asyncio
    async def test_filters_shift_limit_indexes_correctly(self):
        pool = FakePool()
        await execute_search_pg(
            pool, query(min_beds=3, location="Sandbach"), "test", None, limit=25
        )

        sql, params = pool.connection.fetch_calls[0]
        assert "num_beds >= $1" in sql
        assert "town ILIKE $2" in sql
        assert "LIMIT $3 OFFSET $4" in sql
        assert params == (3, "%Sandbach%", 25, 0)

    @pytest.mark.asyncio
    async def test_embedding_parameter_is_after_filters(self):
        pool = FakePool()
        await execute_search_pg(
            pool, query(min_beds=2), "test", [0.1, 0.2, 0.3], limit=5
        )

        sql, params = pool.connection.fetch_calls[0]
        assert "embedding <=> $2::vector" in sql
        assert "LIMIT $3 OFFSET $4" in sql
        assert params[1].startswith("[0.100000,0.200000,0.300000]")

    @pytest.mark.asyncio
    async def test_total_comes_from_count_not_page_length(self):
        pool = FakePool()
        _, total = await execute_search_pg(pool, query(), "test", None, limit=10)

        assert total == 7
        assert pool.connection.fetchval_calls[0][0].startswith("SELECT count(*)")
        # The count query must not receive limit/offset.
        assert pool.connection.fetchval_calls[0][1] == ()

    @pytest.mark.asyncio
    async def test_embedding_is_not_selected(self):
        pool = FakePool()
        await execute_search_pg(pool, query(), "test", None)
        sql, _ = pool.connection.fetch_calls[0]
        assert "has_embedding" in sql
        assert "SELECT *" not in sql


class TestUpsertProperty:
    @pytest.mark.asyncio
    async def test_writes_rich_listing_attributes(self):
        from app.repository import upsert_property

        pool = FakePool()
        await upsert_property(
            pool,
            {
                "address_line1": "51 Cloverfields",
                "town": "Haslington",
                "postcode": "CW1 5AL",
                "outcode": "CW1",
                "property_type": "detached",
                "num_beds": 4,
                "price_paid": 387000,
                "date_sold": "2025-03-01",
                "latitude": 53.09,
                "longitude": -2.4,
                "floor_area_sqm": 131,
                "plot_size_sqm": 333,
                "price_per_sqm": 2954.2,
                "tenure": "Freehold",
                "ward": "Haslington",
                "district": "Cheshire East",
                "source_url": "https://example.test/1",
                "embedding": [0.1, 0.2],
                "source": "housemetric",
            },
        )

        sql, params = pool.connection.fetchval_calls[0]
        assert "floor_area_sqm" in sql
        assert "price_per_sqm" in sql
        assert "district" in sql
        assert "$19::vector" in sql
        assert len(params) == 20
        assert params[11] == 131
        assert params[13] == 2954.2
        assert params[16] == "Cheshire East"
        assert params[18].startswith("[0.100000,0.200000]")
        assert params[19] == "housemetric"


class TestLiveListingSearch:
    @pytest.mark.asyncio
    async def test_filters_use_asking_price_and_active_status(self):
        from app.repository import search_live_listings

        pool = FakePool()
        await search_live_listings(
            pool,
            query(min_beds=3, max_price=400000, location="Sandbach"),
            "3 bed in Sandbach",
            limit=10,
        )

        sql, params = pool.connection.fetch_calls[0]
        assert "listing_status IN ('available', 'under_offer')" in sql
        assert "num_beds >= $1" in sql
        assert "asking_price <= $2" in sql
        assert "town ILIKE $3" in sql
        assert "LIMIT $4 OFFSET $5" in sql
        assert params == (3, 400000.0, "%Sandbach%", 10, 0)
        assert "embedding" not in sql

    @pytest.mark.asyncio
    async def test_free_text_fallback_matches_address_town_description(self):
        from app.repository import search_live_listings

        pool = FakePool()
        await search_live_listings(pool, query(), "demo upload road", limit=5)

        sql, params = pool.connection.fetch_calls[0]
        assert "address_line1 ILIKE $1" in sql
        assert "description ILIKE $1" in sql
        assert "LIMIT $2 OFFSET $3" in sql
        assert params == ("%demo upload road%", 5, 0)

    @pytest.mark.asyncio
    async def test_count_query_has_no_pagination(self):
        from app.repository import search_live_listings

        pool = FakePool()
        _, total = await search_live_listings(pool, query(min_beds=2), "x", limit=5)

        assert total == 7
        count_sql, count_params = pool.connection.fetchval_calls[0]
        assert count_sql.startswith("SELECT count(*) FROM listings")
        assert count_params == (2,)
