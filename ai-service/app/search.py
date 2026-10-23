"""Semantic search — hybrid retrieval with pgvector fallback."""

from __future__ import annotations

import logging
from typing import Any

from .parser import ParsedQuery, parse_query

logger = logging.getLogger(__name__)


async def search(
    query: str,
    pool=None,
    embedder=None,
    limit: int = 50,
) -> dict[str, Any]:
    """Execute a property search.

    Failover chain: semantic (vector + filters) → filter-only → empty result.
    """
    parsed = await parse_query(query)

    if not pool:
        logger.info("[Search] no database pool; returning empty result")
        return {
            "properties": [],
            "tier_used": "deterministic-fallback",
            "total_matches": 0,
            "message": "Running without a database. Configure DATABASE_URL for search.",
        }

    embedding: list[float] | None = None
    if embedder is not None:
        try:
            embedding = await embedder.embed(query)
        except Exception as exc:  # noqa: BLE001 - degrade to keyword search
            logger.warning("[Search] embedding failed, using filters only: %s", exc)

    from .repository import execute_search_pg

    rows, total = await execute_search_pg(pool, parsed, query, embedding, None, limit)

    return {
        "properties": [dict(row) for row in rows],
        "tier_used": "semantic" if embedding else (parsed.tier or "deterministic"),
        "total_matches": total,
        "message": f"Found {total} properties matching “{query[:50]}”",
    }


async def search_location(
    location: str,
    pool=None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search by town/district name."""
    if not pool:
        return {
            "properties": [],
            "total_matches": 0,
            "message": f"No database configured (location={location})",
        }

    from .repository import execute_search_pg

    parsed = ParsedQuery(
        raw=f"properties in {location}",
        tier="deterministic",
        location=location,
        has_location=True,
    )
    rows, total = await execute_search_pg(
        pool, parsed, f"in {location}", None, None, limit
    )

    return {
        "properties": [dict(row) for row in rows],
        "total_matches": total,
        "message": f"Found {total} properties near {location}",
    }


async def count_properties(pool=None) -> dict[str, Any]:
    """Count properties in the database."""
    if not pool:
        return {"count": 0, "message": "No database connection available"}

    from .repository import count_properties as repository_count

    count = await repository_count(pool)
    return {"count": count, "message": f"Database contains {count} properties"}


async def health_check(pool=None) -> dict[str, Any]:
    """Health probe for the search subsystem."""
    if not pool:
        return {
            "status": "degraded",
            "mode": "fallback",
            "message": "Running without a database",
        }

    try:
        result = await count_properties(pool)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unhealthy", "error": str(exc), "mode": "fallback"}

    return {
        "status": "healthy",
        "count": result["count"],
        "mode": "production",
        "message": f"Database connected ({result['count']} properties)",
    }
