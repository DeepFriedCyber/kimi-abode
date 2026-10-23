"""Transform listings into a standardised property representation."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from ..schemas import PropertyType
from .schemas import CsvListing  # noqa: F401 - re-exported for callers

# Canonical postcode: outward code + 3-character inward code.
POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2}$")

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
    return {
        "address_line1": _normalise_address(data.get("address", "")),
        "town": _clean_text(data.get("town")),
        "postcode": _normalise_postcode(data.get("postcode")),
        "property_type": _map_property_type(data.get("property_type")),
        "num_beds": _extract_beds(data.get("beds")),
        "price_paid": _extract_price(data.get("price")),
        "source": data.get("source", "csv"),
    }


def transform_sold_record(data: dict[str, Any]) -> dict[str, Any]:
    """Transform a sold-price record into standard format."""
    date_raw = data.get("date_sold") or data.get("date_of_transfer", "")
    return {
        "property_address": data.get("property_address", data.get("address", "")),
        "property_town": data.get("property_town", data.get("town")),
        "postcode": _normalise_postcode(data.get("postcode")),
        "price_paid": _extract_price(data.get("price_paid")) or 0.0,
        "date_sold": _parse_date(date_raw) if date_raw else None,
        "property_type": data.get("property_type", ""),
    }


def transform_house_metric_row(row: dict[str, Any]) -> dict[str, Any]:
    """Transform a HouseMetric CSV row, handling missing fields gracefully."""
    latitude = _extract_coordinate(row.get("latitude"), limit=90)
    longitude = _extract_coordinate(row.get("longitude"), limit=180)

    return {
        **transform_listing(row),
        "latitude": latitude,
        "longitude": longitude,
        "embedding": None,  # filled later by the embedding worker
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalise_address(addr: Any) -> str:
    """Collapse whitespace in an address."""
    if not addr:
        return ""
    return re.sub(r"\s+", " ", str(addr).strip())


def _extract_beds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        return int(match.group()) if match else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None

    text = str(value).replace("£", "").replace(",", "").strip()
    if not text:
        return None
    try:
        price = float(text)
    except ValueError:
        return None
    return price if price > 0 else None


def _extract_coordinate(value: Any, *, limit: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(coordinate) or not -limit <= coordinate <= limit:
        return None
    # (0, 0) is a common CSV placeholder for "unknown".
    return coordinate or None


def _map_property_type(raw: str | None) -> str | None:
    if not raw:
        return None
    lowered = str(raw).lower().strip()
    for key, value in HOUSE_TYPE_MAP.items():
        if key in lowered:
            return value
    return lowered


def _normalise_postcode(pc: str | None) -> str | None:
    """Return a canonical UK postcode ("cw111jd" -> "CW11 1JD").

    The space matters: postcodes.io and the Land Registry key on the spaced
    form, so stripping it silently breaks geo-enrichment.
    """
    if not pc:
        return None

    cleaned = re.sub(r"\s+", "", str(pc)).upper()
    if len(cleaned) < 5:
        return cleaned  # outcode only — nothing to split

    candidate = f"{cleaned[:-3]} {cleaned[-3:]}"
    return candidate if POSTCODE_RE.match(candidate) else cleaned


def _parse_date(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if not raw:
        return None

    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%b %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


# Public alias used by the universal importer.
normalise_postcode = _normalise_postcode

