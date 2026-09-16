"""Enrich properties with town names, coordinates and postcode data."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from ..gazetteer import outcode_to_town


async def enrich_properties(
    pool,
    postcodes_io,
    batch: int = 300,
) -> int:
    """Enrich properties with town names and coordinates from postcodes.io.

    Runs in batches, returns count of enriched properties this call.
    """
    if not pool or not postcodes_io:
        return 0

    # Fetch properties needing enrichment (no town or no geo)
    sql = "SELECT id, postcode, town FROM properties WHERE town IS NULL OR latitude IS NULL LIMIT %s"
    enriched = 0

    while True:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, batch)
        if not rows:
            break

        # Batch lookup postcodes
        pcs = [r["postcode"] for r in rows if r["postcode"]]
        geo_lookup = await postcodes_io.batch_lookup(pcs) if pcs else {}

        update_sql = "UPDATE properties SET town = $1, latitude = $2, longitude = $3 WHERE id = $4"

        async with pool.acquire() as conn:
            for row in rows:
                pc = row["postcode"]
                geo = geo_lookup.get(pc) or {}
                lat = geo.get("latitude") or row["latitude"]
                lon = geo.get("longitude") or row["longitude"]
                town = row["town"] or outcode_to_town(pc.split()[0] if pc else "")

                # Fallback: check gazetteer for known outcode→town
                if not town and pc:
                    town = outcode_to_town(pc.split()[0])

                await conn.execute(update_sql, town, lat, lon, row["id"])
                enriched += 1

    return enriched


async def review_enrichment(pool) -> dict[str, Any]:
    """Review current enrichment status."""
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT count(*) FROM properties")
        with_town = await conn.fetchval("SELECT count(*) FROM properties WHERE town IS NOT NULL")
        with_geo = await conn.fetchval("SELECT count(*) FROM properties WHERE latitude IS NOT NULL")
        unique_towns = await conn.fetchval(
            "SELECT count(DISTINCT town) FROM properties WHERE town IS NOT NULL"
        )

    return {
        "total": total,
        "with_town": with_town,
        "town_coverage_pct": round(with_town / max(total, 1) * 100, 1),
        "with_geo": with_geo,
        "geo_coverage_pct": round(with_geo / max(total, 1) * 100, 1),
        "unique_towns": unique_towns,
    }
