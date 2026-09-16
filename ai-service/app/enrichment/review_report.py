"""Review report — verify enrichment/ingestion against expected counts."""

from __future__ import annotations

import asyncio
import os


async def main():
    """Generate and print a review report of the current database state."""
    import asyncpg

    url = os.getenv("DATABASE_URL", "postgresql://abode:dev@localhost:5432/abode")
    pool = await asyncpg.create_pool(url)

    try:
        # Properties summary
        prop_stats = await pool.fetchrow("""
            SELECT
                count(*) as total,
                count(town) as with_town,
                count(latitude) as with_geo,
                count(DISTINCT town) as unique_towns
            FROM properties
        """)

        # Sales summary
        sales_stats = await pool.fetchrow("SELECT count(*) as total, count(price_paid) as with_price FROM sales")

        # Duplicate sale pairs (potential traps)
        trap_pairs = await pool.fetch("""
            SELECT property_address, town, postcode
            FROM sales
            GROUP BY property_address, town, postcode
            HAVING count(*) > 1
        """)

        # Property type distribution
        type_dist = await pool.fetch("""
            SELECT property_type, count(*) as cnt
            FROM properties
            WHERE property_type IS NOT NULL
            GROUP BY property_type
            ORDER BY cnt DESC
        """)

        print("\n=== Enrichment Review Report ===\n")
        print(f"Properties: {prop_stats['total']} total, "
              f"{prop_stats['with_town']} with town ({round(prop_stats['with_town']/max(prop_stats['total'],1)*100,1)}%), "
              f"{prop_stats['with_geo']} with geo ({round(prop_stats['with_geo']/max(prop_stats['total'],1)*100,1)}%), "
              f"{prop_stats['unique_towns']} unique towns")

        print(f"\nSales: {sales_stats['total']} total, {sales_stats['with_price']} with price")
        print(f"Trapped pairs (multiple entries same address): {len(trap_pairs)}")
        for t in trap_pairs[:10]:
            print(f"  → {t['property_address']}, {t['town']}, {t['postcode']}")

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
