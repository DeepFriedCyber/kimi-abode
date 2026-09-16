"""Format-specific parsing for estate-agent listing inputs."""

from __future__ import annotations

import csv
import io
from typing import Optional

from .schemas import BlmListing, CsvListing, SoldListing


def parse_blm_csv(raw: str) -> list[BlmListing]:
    """Parse Rightmove/Zoopla BLM-style CSV into structured listings."""
    reader = csv.DictReader(io.StringIO(raw))
    results = []
    for row in reader:
        # BLM columns may vary — try common names
        price = float(row.get("price", row.get("sale_price", 0)))
        beds = _parse_beds(row.get("bedrooms", row.get("num_beds")))
        address = f"{row.get('address', '')} {row.get('town', '')}".strip()
        results.append(BlmListing(
            address=address,
            town=row.get("town"),
            postcode=row.get("postcode"),
            price=price,
            beds=beds,
            property_type=row.get("property_type"),
            tenure=row.get("tenure"),
        ))
    return results


def parse_csv(raw: str, column_map: dict[str, str] | None = None) -> list[CsvListing]:
    """Parse a generic CSV with optional custom column mapping."""
    encoding = getattr(column_map, "encoding", "utf-8-sig") if isinstance(column_map, dict) else "utf-8-sig"
    reader = csv.DictReader(io.StringIO(raw))
    results = []
    for row in reader:
        mapped = {}
        for key, target in (column_map or {}).items():
            mapped[key] = row.get(target, row.get(key))

        price_str = mapped.get("price") or ""
        beds_raw = mapped.get("beds") or mapped.get("bedrooms")

        results.append(CsvListing(
            address=mapped.get("address", ""),
            town=mapped.get("town"),
            postcode=mapped.get("postcode"),
            price=float(price_str.replace(",", "").replace("£", "")) if price_str else 0,
            beds=int(beds_raw) if beds_raw and beds_raw.isdigit() else None,
            property_type=mapped.get("property_type"),
        ))
    return results


def parse_sold_data(raw: str) -> list[SoldListing]:
    """Parse Land Registry CSV sold data."""
    reader = csv.DictReader(io.StringIO(raw))
    results = []
    for row in reader:
        price_str = row.get("price_paid", "0").replace("£", "").replace(",", "")
        date_str = row.get("date_of_transfer", "")
        results.append(SoldListing(
            price_paid=float(price_str) if price_str else 0,
            date_sold=date_str[:10] if date_str else None,
            property_type=row.get("property_type", ""),
            is_multi_property=row.get("is_multi_property_allocation", "F") == "T",
        ))
    return results


def _parse_beds(value: str | None) -> int | None:
    if not value:
        return None
    for c in str(value):
        if c.isdigit():
            return int(c)
    return None
