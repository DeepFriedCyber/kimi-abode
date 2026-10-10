"""Review report — verify enrichment/ingestion against expected counts."""

from __future__ import annotations

import asyncio
import os


def build_summary(
    total_properties: int,
    with_town: int,
    with_geo: int,
    unique_towns: int,
    total_sales: int,
    with_price: int,
    trapped_pairs: list[tuple[str, str, str]],
) -> dict:
    """Build a structured summary from raw DB stats (testable without a database).

    Returns a dict conforming to the EnrichmentReview schema.
    """
    pct = lambda got, total: round(got / max(total, 1) * 100, 1)
    return {
        "total_properties": total_properties,
        "total_sales": total_sales,
        "trapped_pairs": trapped_pairs,
        "town_coverage_pct": pct(with_town, total_properties),
        "geo_coverage_pct": pct(with_geo, total_properties),
        "unique_towns": unique_towns,
        "sales_with_price_pct": pct(with_price, total_sales),
    }


async def main():
    """Generate and print a review report of the current database state."""
    import asyncpg

    url = os.getenv("DATABASE_URL", "postgresql://abode:dev@localhost:5432/abode")
    pool = await asyncpg.create_pool(url)

    try:
        prop_stats = await pool.fetchrow("""
            SELECT
                count(*) as total,
                count(town) as with_town,
                count(latitude) as with_geo,
                count(DISTINCT town) as unique_towns
            FROM properties
        """)

        sales_stats = await pool.fetchrow(
            "SELECT count(*) as total, count(price_paid) as with_price FROM sales"
        )

        trap_pairs = await pool.fetch("""
            SELECT property_address, town, postcode
            FROM sales
            GROUP BY property_address, town, postcode
            HAVING count(*) > 1
        """)

        type_dist = await pool.fetch("""
            SELECT property_type, count(*) as cnt
            FROM properties
            WHERE property_type IS NOT NULL
            GROUP BY property_type
            ORDER BY cnt DESC
        """)

        summary = build_summary(
            total_properties=prop_stats["total"],
            with_town=prop_stats["with_town"],
            with_geo=prop_stats["with_geo"],
            unique_towns=prop_stats["unique_towns"],
            total_sales=sales_stats["total"],
            with_price=sales_stats["with_price"],
            trapped_pairs=[(t["property_address"], t["town"], t["postcode"]) for t in trap_pairs],
        )

        print("\n=== Enrichment Review Report ===\n")
        print(
            f"Properties: {summary['total_properties']} total, "
            f"{summary['town_coverage_pct']}% with town, "
            f"{summary['geo_coverage_pct']}% with geo, "
            f"{summary['unique_towns']} unique towns"
        )
        print(f"\nSales: {summary['total_sales']} total, {summary['sales_with_price_pct']}% with price")
        print(f"Trapped pairs (multiple entries same address): {len(summary['trapped_pairs'])}")
        for t in summary["trapped_pairs"][:10]:
            print(f"  → {t[0]}, {t[1]}, {t[2]}")

        print("\nProperty type distribution:")
        for td in type_dist:
            print(f"  {td['property_type']}: {td['cnt']}")

        print("\n=== Done ===\n")

    finally:
        await pool.close()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
