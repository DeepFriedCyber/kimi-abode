"""Seed script — populates the database with sample data for development."""

from __future__ import annotations

import asyncio
import os

import asyncpg


SAMPLE_PROPERTIES = [
    {"address_line1": "1 High Street", "town": "Sandbach", "postcode": "CW11 1AA", "property_type": "semi-detached", "num_beds": 3, "price_paid": 245000},
    {"address_line1": "2 Oak Lane", "town": "Sandbach", "postcode": "CW11 1AB", "property_type": "detached", "num_beds": 4, "price_paid": 380000},
    {"address_line1": "15 Station Road", "town": "Crewe", "postcode": "CW1 2DE", "property_type": "terraced", "num_beds": 2, "price_paid": 145000},
    {"address_line1": "3 Bungalow Close", "town": "Macclesfield", "postcode": "SK10 1FG", "property_type": "bungalow", "num_beds": 2, "price_paid": 210000},
    {"address_line1": "Flat 4, Market Square", "town": "Wilmslow", "postcode": "SK9 3HI", "property_type": "flat", "num_beds": 1, "price_paid": 155000},
    {"address_line1": "22 Elm Avenue", "town": "Knutsford", "postcode": "WA8 4JK", "property_type": "detached", "num_beds": 5, "price_paid": 620000},
    {"address_line1": "7 Chapel Road", "town": "Nantwich", "postcode": "CW5 6LM", "property_type": "semi-detached", "num_beds": 3, "price_paid": 198000},
    {"address_line1": "12 Victoria Street", "town": "Eccleston", "postcode": "WA8 5NP", "property_type": "terraced", "num_beds": 2, "price_paid": 135000},
]


async def seed_database():
    """Insert sample properties into the database."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:pass@host:5432/dbname"
        )
    pool = await asyncpg.create_pool(url)

    try:
        # Clear existing sample data
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM properties WHERE source = 'seed'")

        sql = """
            INSERT INTO properties (address_line1, town, postcode, property_type,
                                    num_beds, price_paid, source)
            VALUES ($1, $2, $3, $4, $5, $6, 'seed')
            ON CONFLICT DO NOTHING
        """

        async with pool.acquire() as conn:
            for prop in SAMPLE_PROPERTIES:
                await conn.execute(
                    sql,
                    prop["address_line1"],
                    prop["town"],
                    prop["postcode"],
                    prop["property_type"],
                    prop["num_beds"],
                    prop["price_paid"],
                )

        count = await pool.fetchval("SELECT count(*) FROM properties WHERE source = 'seed'")
        print(f"Seeded {count} sample properties.")

    finally:
        await pool.close()


def main():
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
