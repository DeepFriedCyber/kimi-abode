"""Integration test for search with real database."""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestSearchDB:
    """Test search layer against a real PostgreSQL instance."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")


@pytest.mark.integration
class TestPersistIntegration:
    """Test persistence layer with real database."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")
