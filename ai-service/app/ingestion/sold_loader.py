"""Load Land Registry sold-price data into the database."""

from __future__ import annotations

import io
import csv
from typing import Any

from .formats import parse_sold_data
from .transform import transform_sold_record
from .validate import validate_sold_record


async def load_sold_csv(pool, raw_csv: str) -> dict[str, Any]:
    """Load a Land Registry CSV and upsert sold-price records.

    Returns summary stats.
    """
    from .persist import batch_upsert_sales

    records = parse_sold_data(raw_csv)
    valid_records = []
    total = len(records)
    skipped = 0
    errors: list[str] = []

    for rec in records:
        data = rec.model_dump()
        ok, errs = validate_sold_record(data)
        if ok:
            transformed = transform_sold_record(data)
            valid_records.append(transformed)
        else:
            skipped += 1
            errors.extend(errs)

    inserted = await batch_upsert_sales(pool, valid_records)

    return {
        "total": total,
        "inserted": inserted,
        "skipped": skipped,
        "errors_count": len(errors),
        "top_errors": dict(_top_n(errors, 5)),
    }


def load_sold_data(raw_csv: str) -> dict[str, Any]:
    """Parse and validate sold data without a database (for testing/dev)."""
    records = parse_sold_data(raw_csv)
    total = len(records)
    valid = []
    skipped = 0

    for rec in records:
        data = rec.model_dump()
        ok, errs = validate_sold_record(data)
        if ok:
            transformed = transform_sold_record(data)
            valid.append(transformed)
        else:
            skipped += 1

    return {
        "total": total,
        "valid": len(valid),
        "skipped": skipped,
        "errors_count": 0,
    }


def _top_n(errors: list[str], n: int) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for e in errors:
        counts[e] = counts.get(e, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])[:n]
