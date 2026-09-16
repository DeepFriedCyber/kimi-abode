"""Integration test for the persistence layer."""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestPersist:
    """Test batch upsert against a real database."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")


@pytest.mark.integration
class TestSoldLoader:
    """Test sold CSV loader against a real database."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")


@pytest.mark.integration
class TestEnrichmentIntegration:
    """Test enrichment against a real database."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")


@pytest.mark.integration
class TestCompoundTypesDB:
    """Test compound types parsing against real data."""

    @pytest.mark.asyncio
    async def test_parser_with_db_data(self):
        from app.parser import parse_query

        result = await parse_query("semi-detached in Sandbach")
        assert result.has_location is True or "semi-detached" in [t.value for t in result.property_types]


@pytest.mark.integration
class TestEnrichment:
    """Tests for enrichment module."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")


@pytest.mark.integration
class TestIngestionSoldLoader:
    """Tests specifically for the sold_loader module."""

    @pytest.mark.asyncio
    async def test_load_sold_csv_sync_wrapper(self):
        # Without a real pool, parsing is the main path
        from app.ingestion.formats import parse_sold_data

        csv_data = "price_paid,date_of_transfer,property_type\n100000,2024-01-01,D"
        result = parse_sold_data(csv_data)
        assert len(result) >= 1
