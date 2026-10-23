"""Load the demo fixture (ai-service/data/demo_listings.json) into PostgreSQL.

    python scripts/load_demo_to_postgres.py
    python scripts/load_demo_to_postgres.py --dsn postgresql://abode:...@localhost:5544/abode
    python scripts/load_demo_to_postgres.py --dry-run

Idempotent: rows are upserted on (address_line1, postcode), so re-running does
not duplicate anything.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-service"))

import asyncpg  # noqa: E402

from app.repository import upsert_property  # noqa: E402

FIXTURE = Path(__file__).resolve().parent.parent / "ai-service" / "data" / "demo_listings.json"

# Columns upsert_property writes; anything else in the fixture is dropped and
# reported so an unexpected field never passes silently.
WRITABLE = {
    "address_line1",
    "address_line2",
    "town",
    "postcode",
    "outcode",
    "property_type",
    "num_beds",
    "price_paid",
    "date_sold",
    "latitude",
    "longitude",
    "floor_area_sqm",
    "plot_size_sqm",
    "price_per_sqm",
    "tenure",
    "ward",
    "district",
    "source_url",
    "source",
}


def normalise(record: dict) -> dict:
    row = {key: value for key, value in record.items() if key in WRITABLE}
    row.setdefault("source", "demo")
    return row


async def load(dsn: str, dry_run: bool) -> int:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not records:
        print(f"no records in {FIXTURE}")
        return 2

    dropped = sorted({key for record in records for key in record} - WRITABLE)
    print(f"fixture: {len(records)} records, generated {payload.get('generated_at')}")
    if dropped:
        print(f"dropped fields (not writable): {', '.join(dropped)}")
    if dry_run:
        print("dry run: nothing written")
        return 0

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    try:
        started = time.perf_counter()
        ids: list[int] = []
        for record in records:
            ids.append(await upsert_property(pool, normalise(record)))
        elapsed = time.perf_counter() - started

        row = await pool.fetchrow(
            """
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE latitude IS NOT NULL) AS with_geo,
                   count(*) FILTER (WHERE price_paid IS NOT NULL) AS with_price,
                   count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded,
                   min(date_sold) AS first_sale,
                   max(date_sold) AS last_sale
            FROM properties
            """
        )
        print(
            f"upserted {len(ids)} rows in {elapsed:.2f}s "
            f"({len(ids) / elapsed:,.0f}/s)"
        )
        print(
            f"table now: total={row['total']} with_geo={row['with_geo']} "
            f"with_price={row['with_price']} embedded={row['embedded']} "
            f"date_sold {row['first_sale']}..{row['last_sale']}"
        )
        if row["total"] != len(records):
            print(
                f"warning: table holds {row['total']} rows for {len(records)} records "
                "(pre-existing rows or duplicate addresses)"
            )
    finally:
        await pool.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dsn or not args.dsn.startswith("postgres"):
        print("DATABASE_URL must be a postgres:// or postgresql:// URL")
        return 2
    return asyncio.run(load(args.dsn, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
