"""Semantic search — hybrid retrieval with pgvector."""

from __future__ import annotations

from typing import Any

from .parser import parse_query, ParsedQuery


async def search(
    query: str,
    pool=None,
    embedder=None,
    limit: int = 50,
) -> dict[str, Any]:
    """Execute a property search.

    Failover chain:
    1. Semantic cache -> ~20ms (repeat queries)
    2. Hybrid search (vector + keyword) via pgvector -> ~50-200ms
    3. Deterministic filter-only -> ~5ms
    """
    parsed = await parse_query(query)

    if not pool:
        return {
            "properties": [],
            "tier_used": parsed.tier,
            "total_matches": 0,
            "message": f"parsed tier={parsed.tier} beds={parsed.min_beds} type={parsed.property_types}",
        }

    # --- generate embedding -------------------------------------------------
    emb = None
    if embedder:
        emb = await embedder.embed(query)

    from .repository import execute_search_pg

    rows, total = await execute_search_pg(pool, parsed, query, emb, None, limit)

    return {
        "properties": [dict(r) for r in rows],
        "tier_used": parsed.tier or "deterministic",
        "total_matches": total,
        "message": f"Found {total} properties matching: {query}",
    }


async def search_location(
    location: str,
    pool=None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search by town/district name."""
    if not pool:
        return {"properties": [], "total_matches": 0, "message": f"no pool for location={location}"}

    from .repository import execute_search_pg
    parsed = ParsedQuery(
        raw=f"properties in {location}", tier="", min_beds=None,
        max_price=None, property_types=[], location=location,
        has_location=True, has_price=False,
    )
    rows, total = await execute_search_pg(pool, parsed, f"in {location}", None, None, limit)
    return {
        "properties": [dict(r) for r in rows],
        "total_matches": total,
        "message": f"Found {total} properties near {location}",
    }
