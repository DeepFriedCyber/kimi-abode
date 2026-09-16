"""Persistence helpers — batch upserts via asyncpg."""

from __future__ import annotations

from typing import Any

import asyncpg


async def batch_upsert_properties(
    pool: asyncpg.Pool,
    listings: list[dict[str, Any]],
) -> int:
    """Batch-insert properties using asyncpg's EXECUTED command count.

    Each listing must have: address_line1, town, postcode, property_type, num_beds, price_paid
    Optional: latitude, longitude, embedding
    """
    if not listings:
        return 0

    sql = """
        INSERT INTO properties (address_line1, town, postcode, property_type,
                                num_beds, price_paid, latitude, longitude)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (address_line1, postcode)
        DO UPDATE SET property_type = EXCLUDED.property_type,
                      num_beds = EXCLUDED.num_beds,
                      price_paid = EXCLUDED.price_paid
    """

    count = 0
    async with pool.acquire() as conn:
        for item in listings:
            await conn.execute(
                sql,
                item["address_line1"],
                item.get("town"),
                item.get("postcode"),
                item.get("property_type"),
                item.get("num_beds"),
                item.get("price_paid"),
                item.get("latitude"),
                item.get("longitude"),
            )
            count += 1

    return count


async def batch_upsert_sales(
    pool: asyncpg.Pool,
    sales: list[dict[str, Any]],
) -> int:
    """Batch-insert sold-price records."""
    if not sales:
        return 0

    sql = """
        INSERT INTO sales (property_address, property_town, postcode, price_paid, date_sold, property_type)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """

    count = 0
    async with pool.acquire() as conn:
        for sale in sales:
            await conn.execute(
                sql,
                sale["property_address"],
                sale.get("property_town"),
                sale.get("postcode"),
                float(sale["price_paid"]),
                sale.get("date_sold"),
                sale.get("property_type"),
            )
            count += 1

    return count
