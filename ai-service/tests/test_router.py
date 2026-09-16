"""Tests for the search router — provider chain, caching."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestQueryRouter:
    """Tests for the query routing logic."""

    @pytest.mark.asyncio
    async def test_router_falls_through_providers(self):
        from app.router import QueryRouter
        from app.cache import InMemorySemanticCache
        from app.llm import HashEmbedder

        embedder = HashEmbedder()
        cache = InMemorySemanticCache(embedder)
        router = QueryRouter(cache=cache)

        result = await router.route("3 bed in Sandbach")
        assert "tier" in result

    @pytest.mark.asyncio
    async def test_cache_stores_and_retrieves(self):
        from app.cache import InMemorySemanticCache
        from app.llm import HashEmbedder

        embedder = HashEmbedder(dim=10)
        cache = InMemorySemanticCache(embedder, threshold=0.999)

        await cache.put("3 bed house", {"results": [1, 2], "tier": "detached"})
        result = await cache.get("3 bed house")
        assert result is not None
        assert result["tier"] == "detached"


class TestEmbeddingCache:
    """Tests for the semantic cache with cosine similarity."""

    @pytest.mark.asyncio
    async def test_exact_match(self):
        from app.cache import InMemorySemanticCache

        cache = InMemorySemanticCache()
        await cache.put("query 1", {"result": "a"})
        result = await cache.get("query 1")
        assert result["result"] == "a"

    @pytest.mark.asyncio
    async def test_no_match(self):
        from app.cache import InMemorySemanticCache

        cache = InMemorySemanticCache()
        await cache.put("query 1", {"result": "a"})
        result = await cache.get("completely different")
        assert result is None


class TestSearch:
    """Tests for the search module."""

    @pytest.mark.asyncio
    async def test_search_no_pool(self):
        from app.search import search

        result = await search("3 bed in Sandbach")
        assert "tier_used" in result
        assert result["properties"] == []


class TestRouterHealth:
    """Tests for the router health check endpoint."""

    def test_health_returns_ok(self):
        # Verify the app has a health route defined
        from app.main import app
        assert any("health" in str(r.path).lower() for r in app.routes)


class TestParseEndpoint:
    """Tests for the /parse endpoint."""

    def test_parse_endpoint(self):
        from app.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.post("/parse", json={"query": "3 bed house in Sandbach under £200k"})
        assert response.status_code == 200
        data = response.json()
        assert data["min_beds"] == 3
        assert data["has_price"] is True
