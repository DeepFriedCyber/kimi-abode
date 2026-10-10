"""Semantic search — hybrid retrieval with pgvector fallback."""

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
        # No database pool - return deterministic fallback results
        print(f"[Search] Running in fallback mode (no PostgreSQL pool). Query: {query}")
        return {
            "properties": [],
            "tier_used": "deterministic-fallback",
            "total_matches": 0,
            "message": "Running in dev mode without database. Configure DATABASE_URL for full search.",
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


async def count_properties(
    pool=None,
) -> dict[str, Any]:
    """Count total properties."""
    if not pool:
        return {"count": 0, "message": "No database connection available"}

    from .repository import count_properties as repo_count
    count = await repo_count(pool)
    
    return {
        "count": count,
        "tier_used": "deterministic" if not hasattr(repo_count, 'pool') else "pgvector",
        "message": f"Database contains {count} properties",
    }


async def health_check(
    pool=None,
) -> dict[str, Any]:
    """Health check for search service."""
    if not pool:
        return {
            "status": "healthy",
            "mode": "fallback",
            "message": "Running without database (dev mode)",
        }

    try:
        count = await count_properties(pool)
        return {
            "status": "healthy",
            "count": count.get("count", 0),
            "mode": "production",
            "message": f"Database connected. Found {count.get('count', 0)} properties",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "mode": "fallback",
            "message": f"Database connection failed: {e}",
        }