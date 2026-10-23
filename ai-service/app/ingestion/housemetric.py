"""HouseMetric CSV ingestion.

The source CSV has one row per historical sale:

    Address, URL, Last sold, Price paid, Floor area, £ per square metre,
    Type, Beds, Tenure, Plot size

Addresses embed the postcode ("51, Cloverfields, CW1 5AL"). This module splits
it out, canonicalises values, optionally geo-enriches via postcodes.io (free,
no key), and returns records shaped like the `properties` table.

Enrichment is injectable so tests never hit the network.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable

# ------------------------------------------------------------------ constants
POSTCODE_AT_END = re.compile(
    r"([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\s*$", re.IGNORECASE
)

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Rightmove-style taxonomy: a bungalow is its own type, not a detached house.
TYPE_MAP = {
    "detached": "detached",
    "semi-d": "semi-detached",
    "semi-detached": "semi-detached",
    "semi detached": "semi-detached",
    "terrace": "terraced",
    "terraced": "terraced",
    "flat": "flat",
    "maisonette": "maisonette",
    "other": "other",
}

KNOWN_TOWNS = [
    "Sandbach", "Crewe", "Middlewich", "Alsager", "Congleton", "Nantwich",
    "Haslington", "Holmes Chapel", "Kidsgrove", "Winsford", "Northwich",
    "Knutsford", "Macclesfield", "Wilmslow", "Audlem", "Goostrey",
]

POSTCODES_IO_BULK = "https://api.postcodes.io/postcodes"
POSTCODES_IO_OUTCODES = "https://api.postcodes.io/outcodes"
USER_AGENT = "AbodeAI/0.1 (demo dataset enrichment)"
BULK_SIZE = 100


@dataclass
class ImportReport:
    """Summary of what the import did, for CI logs and the reviewer."""

    input_rows: int = 0
    parsed: int = 0
    invalid: int = 0
    duplicates: int = 0
    postcodes_resolved: int = 0
    outcodes_resolved: int = 0
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_rows": self.input_rows,
            "parsed": self.parsed,
            "invalid": self.invalid,
            "duplicates": self.duplicates,
            "postcodes_resolved": self.postcodes_resolved,
            "outcodes_resolved": self.outcodes_resolved,
            "issues": self.issues[:20],
        }


# ------------------------------------------------------------------ parsing
def split_postcode(address: str) -> tuple[str, str | None]:
    """Split "51, Cloverfields, CW1 5AL" into ("51 Cloverfields", "CW1 5AL")."""
    cleaned = re.sub(r"\s+", " ", (address or "").strip())
    match = POSTCODE_AT_END.search(cleaned)
    if not match:
        return cleaned.strip(" ,"), None

    postcode = f"{match.group(1).upper()} {match.group(2).upper()}"
    street = cleaned[: match.start()].strip(" ,")
    street = re.sub(r",\s*", " ", street)
    street = re.sub(r"\s+", " ", street).strip()
    return street, postcode


def outcode_of(postcode: str | None) -> str | None:
    if not postcode:
        return None
    return postcode.split(" ")[0].upper()


def canonical_type(raw: str | None) -> str:
    """Map the CSV's Type column onto the search taxonomy."""
    if not raw:
        return "other"
    value = raw.strip().lower()
    if "bungalow" in value:
        return "bungalow"
    return TYPE_MAP.get(value, value)


def parse_number(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).replace(",", "").replace("£", "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 else None


def parse_month(raw: str | None) -> str | None:
    """Convert "Mar 2025" to an ISO date (first of the month)."""
    if not raw:
        return None
    match = re.match(r"^\s*([A-Za-z]{3})[a-z]*\s+(\d{4})\s*$", raw)
    if not match:
        return None

    month = MONTHS.get(match.group(1).lower())
    if not month:
        return None

    try:
        return date(int(match.group(2)), month, 1).isoformat()
    except ValueError:
        return None


def derive_town(ward: str | None, parish: str | None, district: str | None) -> str | None:
    """Prefer a recognisable town name over a full ward label."""
    for candidate in (ward, parish):
        if not candidate:
            continue
        lowered = candidate.lower()
        for town in KNOWN_TOWNS:
            if lowered.startswith(town.lower()):
                return town
    if ward:
        # Keep the full ward ("Odd Rode", "Dane Valley") rather than truncating
        # to a meaningless first token.
        return ward
    return district


def build_record(row: dict[str, str], geo: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert one CSV row into a canonical property record."""
    address, postcode = split_postcode(row.get("Address", ""))
    floor_area = parse_number(row.get("Floor area"))
    price = parse_number(row.get("Price paid"))
    plot_size = parse_number(row.get("Plot size"))
    beds = parse_number(row.get("Beds"))

    price_per_sqm = None
    if price and floor_area and floor_area > 0:
        price_per_sqm = round(price / floor_area, 2)

    geo = geo or {}
    ward = geo.get("admin_ward")
    parish = geo.get("parish")
    district = geo.get("admin_district")

    return {
        "address_line1": address,
        "town": derive_town(ward, parish, district),
        "postcode": postcode,
        "outcode": outcode_of(postcode),
        "property_type": canonical_type(row.get("Type")),
        "num_beds": int(beds) if beds is not None else None,
        "price_paid": price,
        "date_sold": parse_month(row.get("Last sold")),
        # Month precision only — the source does not publish the exact day.
        "sold_precision": "month",
        "floor_area_sqm": floor_area,
        "plot_size_sqm": plot_size,
        "price_per_sqm": price_per_sqm,
        "tenure": (row.get("Tenure") or "").strip() or None,
        "ward": ward,
        "district": district,
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "source": "housemetric",
        "source_url": (row.get("URL") or "").strip() or None,
    }


# ------------------------------------------------------------------ enrichment
def _post_json(url: str, payload: dict, timeout: int = 20) -> dict | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 2:
                return None
            time.sleep(0.5 * (attempt + 1))
    return None


def enrich_postcodes(postcodes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Bulk-resolve postcodes via postcodes.io.

    Returns {postcode: geo}. Unresolved postcodes are absent from the result so
    callers can fall back to an outcode centroid.
    """
    unique = sorted({postcode for postcode in postcodes if postcode})
    resolved: dict[str, dict[str, Any]] = {}

    for start in range(0, len(unique), BULK_SIZE):
        batch = unique[start : start + BULK_SIZE]
        payload = _post_json(POSTCODES_IO_BULK, {"postcodes": batch})
        if not payload:
            continue

        for item in payload.get("result", []):
            result = item.get("result")
            if not result:
                continue
            resolved[item["query"].upper()] = {
                "admin_district": result.get("admin_district"),
                "admin_ward": result.get("admin_ward"),
                "parish": result.get("parish"),
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
            }
        time.sleep(0.2)  # be polite to a free service

    return resolved


def enrich_outcodes(outcodes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Fallback: geographic centroid for an outcode (e.g. CW11)."""
    unique = sorted({outcode for outcode in outcodes if outcode})
    resolved: dict[str, dict[str, Any]] = {}

    for start in range(0, len(unique), BULK_SIZE):
        batch = unique[start : start + BULK_SIZE]
        payload = _post_json(POSTCODES_IO_OUTCODES, {"outcodes": batch})
        if not payload:
            continue
        for item in payload.get("result", []):
            result = item.get("result")
            if not result:
                continue
            resolved[item["outcode"].upper()] = {
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
            }
        time.sleep(0.2)

    return resolved


# ------------------------------------------------------------------ pipeline
def read_csv(path: str) -> list[dict[str, str]]:
    raw = open(path, "rb").read()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        raise RuntimeError(f"Could not decode {path}")

    return list(csv.DictReader(io.StringIO(text)))


def import_csv(
    path: str,
    *,
    enrich: bool = True,
    limit: int | None = None,
    postcode_fetcher: Callable[[Iterable[str]], dict[str, dict]] | None = None,
    outcode_fetcher: Callable[[Iterable[str]], dict[str, dict]] | None = None,
) -> tuple[list[dict[str, Any]], ImportReport]:
    """Parse, validate, geo-enrich and deduplicate a HouseMetric CSV."""
    from .dedup import deduplicate_listings
    from .validate import validate_listing

    rows = read_csv(path)
    if limit is not None:
        rows = rows[:limit]

    report = ImportReport(input_rows=len(rows))

    geo: dict[str, dict[str, Any]] = {}
    outcode_geo: dict[str, dict[str, Any]] = {}

    if enrich and rows:
        parsed_pairs = [split_postcode(row.get("Address", "")) for row in rows]
        postcodes = [postcode for _, postcode in parsed_pairs if postcode]
        getter = postcode_fetcher or enrich_postcodes
        try:
            geo = getter(postcodes)
        except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
            report.issues.append(f"postcode enrichment failed: {exc}")
            geo = {}

        unresolved_outcodes = {
            outcode_of(postcode)
            for _, postcode in parsed_pairs
            if postcode and postcode.upper() not in geo
        }
        if unresolved_outcodes:
            getter_out = outcode_fetcher or enrich_outcodes
            try:
                outcode_geo = getter_out(sorted(o for o in unresolved_outcodes if o))
            except Exception as exc:  # noqa: BLE001
                report.issues.append(f"outcode enrichment failed: {exc}")

    records: list[dict[str, Any]] = []
    for row in rows:
        _, postcode = split_postcode(row.get("Address", ""))
        record = build_record(row, geo.get((postcode or "").upper()))

        if record["latitude"] is None and record["outcode"] in outcode_geo:
            record["latitude"] = outcode_geo[record["outcode"]]["latitude"]
            record["longitude"] = outcode_geo[record["outcode"]]["longitude"]
            record["geo_precision"] = "outcode"
        elif record["latitude"] is not None:
            record["geo_precision"] = "postcode"

        valid, errors = validate_listing(record)
        if not valid:
            report.invalid += 1
            report.issues.append(f"{record.get('address_line1')}: {errors}")
            continue

        records.append(record)

    deduped = deduplicate_listings(records)
    report.duplicates = len(records) - len(deduped)
    report.parsed = len(deduped)

    # Count after deduplication so the report describes the final dataset.
    report.postcodes_resolved = sum(
        1 for record in deduped if record.get("geo_precision") == "postcode"
    )
    report.outcodes_resolved = sum(
        1 for record in deduped if record.get("geo_precision") == "outcode"
    )

    return deduped, report
