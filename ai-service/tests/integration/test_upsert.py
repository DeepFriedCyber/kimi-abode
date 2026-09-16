"""Integration tests for property upsert via repository layer."""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestUpsert:
    """Test property upsert operations with a real (test) database."""

    @pytest.fixture(autouse=True)
    async def skip_if_no_docker(self):
        try:
            from testcontainers.postgres import PostgresContainer
        except ImportError:
            pytest.skip("Docker/testcontainers not available")


@pytest.mark.integration
class TestUpsertBasic:
    """Placeholder integration tests — require Docker + running postgres."""

    @pytest.mark.asyncio
    async def test_placeholder(self):
        """Integration tests need docker-compose up first."""
        from app.ingestion.pipeline import IngestionPipeline
        p = IngestionPipeline()
        assert isinstance(p, IngestionPipeline)


@pytest.mark.integration
class TestUpsertWithPool:
    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")
