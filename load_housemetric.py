"""Load HouseMetric CSV data into the Abode database."""

import asyncio
import csv
import io
import re
from pathlib import Path


async def main():
    # Find the CSV file
    csv_files = list(Path(".").glob("search_results*.csv"))
    if not csv_files:
        print("No search_results*.csv found in current directory.")
        return

    csv_path = csv_files[0]
    print(f"Loading: {csv_path}")
    raw = csv_path.read_text(encoding="utf-8-sig")  # handles BOM
    lines = raw.strip().split("\n")
    total_rows = len(lines) - 1  # minus header
    print(f"Total rows in CSV: {total_rows}")

    # Parse CSV
    reader = csv.DictReader(io.StringIO(raw))
    parsed = []
    for row in reader:
        address = row.get("Address", "").strip().strip('"')
        price_str = row.get("Price paid", "").strip()
        beds_raw = row.get("Beds", "").strip()
        type_raw = row.get("Type", "").strip()

        # Parse price (handle empty strings)
        price_paid = None
        if price_str:
            try:
                price_paid = float(price_str)
            except ValueError:
                pass

        # Parse beds
        num_beds = None
        if beds_raw:
            m = re.search(r"\d+", beds_raw)
            if m:
                num_beds = int(m.group())

        # Map type
        property_type = None
        type_lower = type_raw.lower() if type_raw else ""
        if "flat" in type_lower:
            property_type = "flat"
        elif "bungalow" in type_lower:
            property_type = "bungalow"
        elif "semi" in type_lower:
            property_type = "semi-detached"
        elif "terraced" in type_lower or "terrace" in type_lower:
            property_type = "terraced"
        elif "detached" in type_lower:
            property_type = "detached"

        # Extract outcode from postcode (column doesn't exist, but address has it embedded)
        # Postcodes are in URLs like CW1-5AL → CW1 5AL
        url = row.get("URL", "")
        outcode = None
        if "housemetric.co.uk/" in url:
            pc_part = url.split("/")[2].replace("-", " ").upper() if "/" in url else ""
            parts = pc_part.split()
            if len(parts) >= 1:
                outcode = parts[0]

        parsed.append({
            "address_line1": address,
            "outcode": outcode,
            "property_type": property_type,
            "num_beds": num_beds,
            "price_paid": price_paid,
            "source": "housemetric",
        })

    print(f"Parsed {len(parsed)} listings")

    # Connect to database and upsert
    import os
    db_url = os.getenv("DATABASE_URL", "postgresql://abode:dev@localhost:5432/abode")
    print(f"\nConnecting to: {db_url}")

    try:
        import asyncpg
        pool = await asyncpg.create_pool(db_url)
    except Exception as e:
        print(f"Database connection failed: {e}")
        print("Make sure docker compose up -d postgres is running.")
        return

    try:
        sql = """
            INSERT INTO properties (address_line1, outcode, property_type, num_beds, price_paid, source)
            VALUES ($1, $2, $3, $4, $5, 'housemetric')
            ON CONFLICT (address_line1)
            DO UPDATE SET outcode = EXCLUDED.outcode,
                          property_type = EXCLUDED.property_type,
                          num_beds = EXCLUDED.num_beds,
                          price_paid = EXCLUDED.price_paid,
                          source = EXCLUDED.source,
                          updated_at = NOW()
        """

        inserted = 0
        updated = 0
        errors = 0

        async with pool.acquire() as conn:
            for item in parsed:
                try:
                    result = await conn.execute(
                        sql,
                        item["address_line1"],
                        item.get("outcode"),
                        item.get("property_type"),
                        item.get("num_beds"),
                        item.get("price_paid"),
                    )
                    if "INSERT" in result:
                        inserted += 1
                    else:
                        updated += 1
                except Exception as e:
                    errors += 1
                    print(f"  Error inserting '{item['address_line1']}': {e}")

        print(f"\n✅ Load complete:")
        print(f"   Inserted: {inserted}")
        print(f"   Updated:  {updated}")
        print(f"   Errors:   {errors}")

        # Show summary stats
        total = await pool.fetchval("SELECT count(*) FROM properties WHERE source = 'housemetric'")
        avg_price = await pool.fetchval(
            "SELECT round(avg(price_paid)) FROM properties WHERE source = 'housemetric' AND price_paid IS NOT NULL"
        )
        types = await pool.fetch("""
            SELECT property_type, count(*) as cnt
            FROM properties WHERE source = 'housemetric'
            GROUP BY property_type ORDER BY cnt DESC
        """)

        print(f"\n   Total housemetric properties: {total}")
        print(f"   Average price paid: £{avg_price:,}" if avg_price else "   Average price: N/A")
        print(f"\n   Type breakdown:")
        for t in types:
            print(f"     {t['property_type']:20s}: {t['cnt']}")

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
