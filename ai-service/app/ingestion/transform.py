"""Transform listings into a standardised property representation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .schemas import CsvListing
from ..schemas import PropertyType


# House-type keywords that need normalisation.
HOUSE_TYPE_MAP: dict[str, str] = {
    "flat": PropertyType.FLAT.value,
    "bungalow": PropertyType.BUNGALOW.value,
    "terraced": PropertyType.TERRACED.value,
    "semi-detached": PropertyType.SEMI_DETACHED.value,
    "detached": PropertyType.DETACHED.value,
    "maisonette": PropertyType.MAISONETTE.value,
}


def transform_listing(data: dict[str, Any]) -> dict[str, Any]:
    """Transform a raw listing into a standardised property dict."""
    address = _normalise_address(data.get("address", ""))
    beds = _extract_beds(data.get("beds"))
    price = _extract_price(data.get("price"))
    prop_type = _map_property_type(data.get("property_type"))

    return {
        "address_line1": address,
        "town": data.get("town"),
        "postcode": _normalise_postcode(data.get("postcode")),
        "property_type": prop_type,
        "num_beds": beds,
        "price_paid": price,
        "source": data.get("source", "csv"),
    }


def transform_sold_record(data: dict[str, Any]) -> dict[str, Any]:
    """Transform a sold-price record into standard format."""
    date_raw = data.get("date_sold") or data.get("date_of_transfer", "")
    return {
        "property_address": data.get("property_address", data.get("address", "")),
        "property_town": data.get("property_town", data.get("town")),
        "postcode": _normalise_postcode(data.get("postcode")),
        "price_paid": float(data.get("price_paid", 0)),
        "date_sold": _parse_date(date_raw) if date_raw else None,
        "property_type": data.get("property_type", ""),
    }


def transform_house_metric_row(row: dict[str, Any]) -> dict[str, Any]:
    """Transform a HouseMetric CSV row, handling missing fields gracefully."""
    return {
        **transform_listing(row),
        "latitude": float(row.get("latitude", 0)) if row.get("latitude") else None,
        "longitude": float(row.get("longitude", 0)) if row.get("longitude") else None,
        "embedding": None,  # filled later by embedding worker
    }


def _normalise_address(addr: str) -> str:
    """Normalise address — trim whitespace, collapse spaces."""
    return re.sub(r"\s+", " ", addr.strip()) if addr else ""


def _extract_beds(value) -> int | None:
    if value is None or (isinstance(value, float) and (value != value)):  # NaN check
        return None
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        return int(m.group()) if m else None
    return int(value)


def _extract_price(value) -> float | None:
    if value is None or (isinstance(value, float) and (value != value)):
        return None
    s = str(value).replace("£", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _map_property_type(raw: str | None) -> str | None:
    if not raw:
        return None
    lower = raw.lower().strip()
    for key, val in HOUSE_TYPE_MAP.items():
        if key in lower:
            return val
    return lower


def _normalise_postcode(pc: str | None) -> str | None:
    if not pc:
        return None
    return re.sub(r"\s+", "", pc.strip()).upper()


def _parse_date(raw: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except (ValueError, TypeError):
            continue
    return None
