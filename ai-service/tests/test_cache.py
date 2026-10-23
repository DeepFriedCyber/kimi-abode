"""Semantic cache tests — context isolation and defensive copies."""

from __future__ import annotations

import pytest

from app.cache import InMemorySemanticCache


class TestCache:
    @pytest.mark.asyncio
    async def test_context_separates_entries(self):
        cache = InMemorySemanticCache()
        await cache.put("is it noisy?", {"response": "for property 1"}, context="property:1")
        await cache.put("is it noisy?", {"response": "for property 2"}, context="property:2")

        assert (await cache.get("is it noisy?", context="property:1"))["response"] == "for property 1"
        assert (await cache.get("is it noisy?", context="property:2"))["response"] == "for property 2"
        assert await cache.get("is it noisy?", context="property:3") is None

    @pytest.mark.asyncio
    async def test_returns_a_copy(self):
        cache = InMemorySemanticCache()
        await cache.put("q", {"results": [1]})

        first = await cache.get("q")
        first["results"].append(2)

        second = await cache.get("q")
        assert second["results"] == [1]

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        cache = InMemorySemanticCache(ttl_seconds=0)
        await cache.put("q", {"a": 1})
        assert await cache.get("q") is None

    @pytest.mark.asyncio
    async def test_capacity_is_bounded(self):
        cache = InMemorySemanticCache(max_size=3)
        for index in range(10):
            await cache.put(f"q{index}", {"index": index})

        assert len(cache) == 3
        assert await cache.get("q0") is None
        assert await cache.get("q9") == {"index": 9}

    @pytest.mark.asyncio
    async def test_exact_match_is_case_insensitive(self):
        cache = InMemorySemanticCache()
        await cache.put("3 Bed House", {"ok": True})
        assert await cache.get("3 bed house") == {"ok": True}
