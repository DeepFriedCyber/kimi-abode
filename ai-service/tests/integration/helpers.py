"""Integration test helpers."""

from __future__ import annotations

import asyncio


async def create_test_pool():
    """Create a test database pool using testcontainers."""
    try:
        from testcontainers.postgres import PostgresContainer
        container = PostgresContainer("postgres:16")
        container.start()
        url = container.get_connection_url()
        import asyncpg
        pool = await asyncpg.create_pool(url)
        return pool, container
    except ImportError:
        # testcontainers not installed — skip
        return None, None


def skip_if_no_docker():
    """Skip marker if Docker/testcontainers unavailable."""
    try:
        from testcontainers.core.container import DockerContainer
        return True
    except (ImportError, OSError):
        return False
