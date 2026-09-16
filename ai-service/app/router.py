"""Provider routing — query execution strategy selection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProviderResult:
    """Container for a single provider's output."""
    tier: str
    results: list = field(default_factory=list)
    message: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result: dict = {"tier": self.tier, **self.extra}
        if self.results:
            result["results"] = self.results
        if self.message:
            result["message"] = self.message
        return result


class QueryRouter:
    """Route queries through a chain of providers with degradation.

    Providers are called in order; the first to return a non-empty result wins.
    On complete failure, returns a forced-deterministic fallback.
    """

    def __init__(self, cache=None) -> None:
        self.providers: list = []
        self.cache = cache

    def add_provider(self, provider) -> None:
        """Register a search provider."""
        self.providers.append(provider)

    async def route(self, query: str) -> dict:
        """Run the provider chain and return the best result."""
        # Check semantic cache first (~20ms)
        cached = await self.cache.get(query) if self.cache else None
        if cached:
            return {**cached, "tier": "semantic-cache"}

        for provider in self.providers:
            try:
                result = await provider.execute(query)
                if result:
                    if self.cache:
                        await self.cache.put(query, result)
                    return {**result, "tier": getattr(provider, "name", "unknown")}
            except Exception:
                continue

        # Fallback: nothing worked
        return {"tier": "forced-deterministic", "results": [], "message": "no-provider-healthy"}


def build_providers() -> list:
    """Build the default provider list.

    In production this would be a real search provider backed by pgvector.
    For now we provide a minimal placeholder that integrates with the cache.
    """
    from .cache import InMemorySemanticCache
    from .llm import HashEmbedder

    embedder = HashEmbedder()
    return [type("PlaceholderProvider", (), {
        "name": "placeholder",
        "execute": lambda q: None,  # real impl wired in main.py lifespan
    })()]


def search_fn(parsed, message, pool=None):
    """Search entry point — uses repository layer."""
    import asyncio
    from .repository import execute_search_pg

    async def _search():
        if not pool:
            return [], 0
        emb = None
        # embedding handled in main.py via embedder
        rows, total = await execute_search_pg(pool, parsed, message, emb)
        return [dict(r) for r in rows], total

    # This module is used synchronously; the actual async path is in main.py
    raise NotImplementedError("Use from main.py lifespan context")
