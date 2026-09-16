"""Integration test fixtures using testcontainers for PostgreSQL."""

from __future__ import annotations

import pytest


# conftest.py — shared fixtures for integration tests


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
