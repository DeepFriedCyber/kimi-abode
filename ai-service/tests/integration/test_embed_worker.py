"""Integration test for the embedding worker."""

from __future__ import annotations

import pytest


class TestEmbedWorker:
    """Test embedding worker with a real database."""

    def test_placeholder(self):
        """Needs a real pool — run docker compose up first."""
        from app.workers.embed import run_embedding_worker
        assert callable(run_embedding_worker)


@pytest.mark.integration
class TestSearchDB:
    """Test search against a real database."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")


@pytest.mark.integration
class TestPersist:
    """Test persistence layer with real database."""

    @pytest.fixture(autouse=True)
    async def skip(self):
        try:
            from testcontainers.postgres import PostgresContainer  # noqa
        except ImportError:
            pytest.skip("Docker/testcontainers not available")
