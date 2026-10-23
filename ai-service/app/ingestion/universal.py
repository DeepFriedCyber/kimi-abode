"""Universal listing import — one contract for many agent upload formats.

Agents upload whatever their CRM produces (CSV/TSV, Excel, JSON, XML/BLM) or
paste an email. This module detects the format and columns, normalises values,
validates rows, and reports exactly what would happen before anything is stored.

Design rules:
  * never write during a dry run;
  * report the spreadsheet row number (header = row 1);
  * partial import is allowed — one bad row must not reject a file;
  * unknown columns are reported, not silently dropped;
  * every parser is bounded (rows, field length, upload size).
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from html import unescape
from typing import Any, Callable, Iterable, Sequence

from .housemetric import canonical_type, parse_month, split_postcode
from .transform import normalise_postcode

MAX_ROWS = 5_000
MAX_DESCRIPTION = 5_000
MAX_ERRORS_REPORTED = 100
SQFT_TO_SQM = 1 / 10.7639

SUPPORTED_FORMATS = ("csv", "tsv", "xlsx", "json", "jsonl", "xml", "text")

# canonical field -> accepted header spellings (normalised: lower, alnum only)
COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "address": (
        "address", "full address", "property address", "display address",
        "street address", "addr", "location",
    ),
    "address_line1": ("address line 1", "address 1", "address1", "line 1", "street"),
    "address_line2": ("address line 2", "address 2", "address2", "line 2"),
    "town": ("town", "town city", "city", "locality", "village", "suburb", "area"),
    "postcode": ("postcode", "post code", "postal code", "pcode", "zip", "postcode full"),
    "outcode": ("outcode", "outward code"),
    "price": (
        "price", "asking price", "guide price", "sale price", "selling price",
        "price gbp", "asking", "value", "price guide",
    ),
    "price_paid": ("price paid", "sold price", "last sold price", "achieved price"),
    "price_qualifier": ("price qualifier", "qualifier", "price type"),
    "property_type": (
        "type", "property type", "prop type", "property subtype", "house type",
        "style", "property style",
    ),
    "beds": (
        "beds", "bedrooms", "bedroom count", "num bedrooms", "number of bedrooms",
        "no of bedrooms", "beds count", "num beds",
    ),
    "baths": (
        "baths", "bathrooms", "bathroom count", "num bathrooms",
        "number of bathrooms", "num baths",
    ),
    "tenure": ("tenure", "ownership", "tenure type"),
    "floor_area_sqm": (
        "floor area", "floor area sqm", "internal area", "area sqm", "sqm",
        "square metres", "floor size", "size",
    ),
    "plot_size_sqm": ("plot size", "plot area", "land area", "garden size"),
    "description": (
        "description", "property description", "summary", "details",
        "marketing description", "comments", "full description", "blurb",
    ),
    "features": ("features", "key features", "highlights", "bullet points", "selling points"),
    "status": ("status", "listing status", "availability", "state", "sale status"),
    "agent_ref": (
        "ref", "reference", "agent ref", "property ref", "property reference",
        "id", "property id", "branch ref", "our ref",
    ),
    "listed_at": ("listed", "listed date", "date listed", "instruction date", "date added"),
    "date_sold": ("date sold", "sold date", "date of transfer", "completion date", "sale date"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng", "long"),
    "source_url": ("url", "link", "property url", "listing url", "website", "source url"),
}

# Keys used by canonical JSON payloads that differ from the CSV field names.
LOOKUP_ALIASES: dict[str, tuple[str, ...]] = {
    "price": ("asking_price",),
    "beds": ("num_beds",),
    "baths": ("num_bathrooms", "bathrooms"),
}

STATUS_MAP = {    "available": "available", "for sale": "available", "active": "available",
    "live": "available", "on market": "available", "new": "available",
    "new instruction": "available", "available now": "available",
    "under offer": "under_offer", "sstc": "under_offer",
    "sold stc": "under_offer", "sold subject to contract": "under_offer",
    "reserved": "under_offer", "let agreed": "let_agreed",
    "sold": "sold", "completed": "sold", "exchanged": "sold",
    "let": "let", "withdrawn": "withdrawn", "off market": "withdrawn",
}

PRICE_QUALIFIERS = (
    ("guide price", "guide"),
    ("offers in excess of", "offers_over"),
    ("offers over", "offers_over"),
    ("oiro", "offers_over"),
    ("oieo", "offers_over"),
    ("offers in the region of", "offers_around"),
    ("fixed price", "fixed"),
    ("offers around", "offers_around"),
)

MONEY_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?")
PERIOD_RE = re.compile(r"\b(pcm|pcm\.|per month|per calendar month|pw|per week)\b", re.I)
SQFT_RE = re.compile(r"(sq\.?\s*ft|sqft|ft2|ft²)", re.I)
SQM_RE = re.compile(r"(sq\.?\s*m|sqm|m2|m²)", re.I)
POSTCODE_LOOSE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$")


# ------------------------------------------------------------------ dataclasses
@dataclass
class Issue:
    row: int
    message: str
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"row": self.row, "message": self.message}
        if self.field:
            payload["field"] = self.field
        return payload


@dataclass
class ImportReport:
    dry_run: bool = True
    format: str = "csv"
    encoding: str | None = None
    delimiter: str | None = None
    received: int = 0
    valid: int = 0
    invalid: int = 0
    duplicates: int = 0
    imported: int = 0
    imported_ids: list[int] = field(default_factory=list)
    geocoded: int = 0
    columns: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    unmapped_columns: list[str] = field(default_factory=list)
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    preview: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "format": self.format,
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "received": self.received,
            "valid": self.valid,
            "invalid": self.invalid,
            "duplicates": self.duplicates,
            "imported": self.imported,
            "imported_ids": self.imported_ids,
            "geocoded": self.geocoded,
            "columns": self.columns,
            "confidence": self.confidence,
            "unmapped_columns": self.unmapped_columns,
            "errors": [issue.as_dict() for issue in self.errors[:MAX_ERRORS_REPORTED]],
            "warnings": [issue.as_dict() for issue in self.warnings[:MAX_ERRORS_REPORTED]],
            "preview": self.preview,
        }


# ------------------------------------------------------------------ helpers
def normalise_header(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean_text(value: Any, *, limit: int = 1_000) -> str:
    """Strip HTML, control characters and excess whitespace."""
    if value is None:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def parse_money(value: Any) -> float | None:
    text = clean_text(value, limit=100).replace("£", "").replace("GBP", "")
    if not text or text.strip().lower() in {"poa", "tbc", "n/a", "-"}:
        return None
    match = MONEY_RE.search(text)
    if not match:
        return None
    try:
        amount = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        amount *= 1_000
    elif suffix == "m":
        amount *= 1_000_000
    return amount if amount > 0 else None


def parse_period(value: Any) -> str | None:
    text = clean_text(value, limit=100)
    match = PERIOD_RE.search(text)
    if not match:
        return None
    token = match.group(1).lower()
    return "pcm" if "month" in token or token.startswith("pcm") else "pw"


def parse_int(value: Any) -> int | None:
    text = clean_text(value, limit=40)
    if not text:
        return None
    match = re.search(r"\d{1,3}", text)
    return int(match.group()) if match else None


def parse_area(value: Any, header: str = "") -> float | None:
    text = clean_text(value, limit=60)
    if not text:
        return None
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        amount = float(match.group(1).replace(",", ""))
    except ValueError:
        return None

    is_sqft = bool(SQFT_RE.search(text) or SQFT_RE.search(header or ""))
    is_sqm = bool(SQM_RE.search(text) or SQM_RE.search(header or ""))
    if is_sqft and not is_sqm:
        amount *= SQFT_TO_SQM
    return round(amount, 2) if amount > 0 else None


def parse_date_value(value: Any) -> tuple[str | None, str | None]:
    """Return (iso_date, precision). Handles Excel dates and month precision."""
    if value in (None, ""):
        return None, None
    if isinstance(value, datetime):
        return value.date().isoformat(), "day"
    if isinstance(value, date):
        return value.isoformat(), "day"

    text = clean_text(value, limit=40)
    if not text:
        return None, None

    month_precision = parse_month(text)
    if month_precision:
        return month_precision, "month"

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat(), "day"
        except ValueError:
            continue

    # Ambiguous slash dates default to UK order unless the day cannot be first.
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if match:
        first, second, year = map(int, match.groups())
        if first > 12:
            day, month = first, second
        elif second > 12:
            day, month = second, first
        else:
            day, month = first, second  # UK default: dd/mm/yyyy
        try:
            return date(year, month, day).isoformat(), "day"
        except ValueError:
            return None, None

    return None, None


def parse_features(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        parts = [clean_text(item, limit=120) for item in value]
    else:
        text = clean_text(value, limit=2_000)
        if not text:
            return []
        parts = [part.strip(" -•") for part in re.split(r"[;|•\n\r]+", text)]

    seen: set[str] = set()
    unique: list[str] = []
    for feature in parts:
        feature = feature.strip(" -•")
        key = feature.lower()
        if feature and key not in seen:
            seen.add(key)
            unique.append(feature[:120])
    return unique[:20]


def parse_status(value: Any, *, has_sold_price: bool) -> str:
    text = clean_text(value, limit=60).lower()
    if text:
        for key, status in STATUS_MAP.items():
            if key in text:
                return status
    return "sold" if has_sold_price else "available"


def parse_qualifier(*values: Any) -> str | None:
    text = " ".join(clean_text(value, limit=120).lower() for value in values if value)
    for phrase, qualifier in PRICE_QUALIFIERS:
        if phrase in text:
            return qualifier
    return None


def canonical_property_type(value: Any) -> str | None:
    text = clean_text(value, limit=80)
    if not text:
        return None
    lowered = text.lower()
    if "end of terrace" in lowered or "end terrace" in lowered:
        return "terraced"
    if "link detached" in lowered:
        return "semi-detached"
    return canonical_type(text)


# ------------------------------------------------------------------ mapping
def detect_mapping(headers: Sequence[str]) -> tuple[dict[str, str], dict[str, float], list[str]]:
    """Match headers to canonical fields. Exact matches win over fuzzy ones."""
    normalised = {header: normalise_header(header) for header in headers if header}
    mapping: dict[str, str] = {}
    confidence: dict[str, float] = {}
    used: set[str] = set()

    # Pass 0: JSON payloads often use the canonical snake_case keys.
    for canonical in COLUMN_SYNONYMS:
        normalised_canonical = normalise_header(canonical)
        for header, normalised_header in normalised.items():
            if header in used:
                continue
            if normalised_header == normalised_canonical:
                mapping[canonical] = header
                confidence[canonical] = 1.0
                used.add(header)
                break

    # Pass 1: exact alias matches.
    for canonical, aliases in COLUMN_SYNONYMS.items():
        for header, normalised_header in normalised.items():
            if header in used:
                continue
            if normalised_header in aliases:
                mapping[canonical] = header
                confidence[canonical] = 1.0
                used.add(header)
                break

    # Pass 2: containment, longest alias first (avoids "bed" matching "bedrooms").
    ordered = sorted(
        ((canonical, alias) for canonical, aliases in COLUMN_SYNONYMS.items() for alias in aliases),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for canonical, alias in ordered:
        if canonical in mapping or len(alias) < 4:
            continue
        for header, normalised_header in normalised.items():
            if header in used:
                continue
            if alias in normalised_header:
                mapping[canonical] = header
                confidence[canonical] = 0.6
                used.add(header)
                break

    unmapped = [header for header in headers if header and header not in used]
    return mapping, confidence, unmapped


# ------------------------------------------------------------------ readers
def detect_format(filename: str, content: bytes) -> str:
    suffix = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if suffix in {"xlsx", "xlsm"}:
        return "xlsx"
    if suffix == "jsonl":
        return "jsonl"
    if suffix == "json":
        return "json"
    if suffix in {"xml", "blm", "reso"}:
        return "xml"
    if suffix in {"tsv", "tab"}:
        return "tsv"
    if suffix in {"csv", "txt"} and suffix == "csv":
        return "csv"
    if suffix == "txt":
        return "text"

    head = content[:2_000].lstrip()
    if head.startswith(b"PK"):
        return "xlsx"
    if head.startswith((b"{", b"[")):
        return "json"
    if head.startswith(b"<"):
        return "xml"
    return "csv"


def decode_bytes(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace"), "utf-8"


def sniff_delimiter(sample: str, default: str = ",") -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return default


def read_csv_rows(content: bytes, delimiter: str | None = None) -> tuple[list[dict[str, str]], str, str]:
    text, encoding = decode_bytes(content)
    chosen = delimiter or sniff_delimiter(text[:4_096])
    reader = csv.DictReader(io.StringIO(text), delimiter=chosen)
    rows: list[dict[str, str]] = []
    for index, row in enumerate(reader):
        if index >= MAX_ROWS:
            break
        rows.append({(key or "").strip(): (value or "") for key, value in row.items()})
    return rows, encoding, chosen


def read_xlsx_rows(content: bytes) -> tuple[list[dict[str, Any]], str]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    iterator = sheet.iter_rows(values_only=True)
    headers = next(iterator, None)
    if not headers:
        return [], "xlsx"

    cleaned_headers = [str(value).strip() if value is not None else "" for value in headers]
    rows: list[dict[str, Any]] = []
    for index, values in enumerate(iterator):
        if index >= MAX_ROWS:
            break
        if not any(value is not None and str(value).strip() for value in values):
            continue
        rows.append(
            {
                header: value
                for header, value in zip(cleaned_headers, values)
                if header
            }
        )
    workbook.close()
    return rows, "xlsx"


def read_json_rows(content: bytes) -> tuple[list[dict[str, Any]], str]:
    text, encoding = decode_bytes(content)
    payload = json.loads(text)
    if isinstance(payload, dict):
        for key in ("listings", "properties", "records", "data", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON must be an object or a list of objects")

    rows = [row for row in payload if isinstance(row, dict)][:MAX_ROWS]
    return rows, encoding


def read_jsonl_rows(content: bytes) -> tuple[list[dict[str, Any]], str]:
    text, encoding = decode_bytes(content)
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
        if len(rows) >= MAX_ROWS:
            break
    return rows, encoding


def read_xml_rows(content: bytes) -> tuple[list[dict[str, Any]], str]:
    """Flatten repeated XML elements (BLM/RESO/portal feeds) into rows."""
    from defusedxml import ElementTree

    root = ElementTree.fromstring(content)

    def local(tag: str) -> str:
        return tag.split("}")[-1].lower()

    # Choose the repeated container with the most instances.
    candidates: dict[str, list[Any]] = {}
    for element in root.iter():
        candidates.setdefault(local(element.tag), []).append(element)

    container = None
    for name in ("property", "listing", "item", "record", "entry", "propertydetails"):
        matches = candidates.get(name, [])
        if len(matches) > 1:
            container = name
            break

    elements = candidates.get(container, []) if container else list(root)
    rows: list[dict[str, Any]] = []
    for element in elements[:MAX_ROWS]:
        row: dict[str, Any] = {}
        for child in element.iter():
            if child is element:
                continue
            key = local(child.tag)
            text = (child.text or "").strip()
            if text and key not in row:
                row[key] = text
            for attr, value in child.attrib.items():
                attr_key = local(attr)
                if attr_key not in row and str(value).strip():
                    row[attr_key] = str(value).strip()
        if row:
            rows.append(row)
    return rows, "xml"


def row_from_text(text: str) -> list[dict[str, Any]]:
    """Turn a pasted email/description into a single draft listing."""
    from ..parser import _deterministic_parse

    cleaned = clean_text(text, limit=MAX_DESCRIPTION)
    if not cleaned:
        return []

    parsed = _deterministic_parse(cleaned)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    address = ""
    for line in lines:
        if len(line) > 160:
            continue
        if re.search(r"\d", line) and not line.strip().lower().startswith(("price", "£")):
            address = line
            break
    if not address and lines:
        address = lines[0][:160]

    row: dict[str, Any] = {
        "address": address,
        "description": cleaned,
        "postcode": parsed.outcode,
    }
    if parsed.max_price:
        row["price"] = parsed.max_price
    if parsed.min_beds is not None:
        row["beds"] = parsed.min_beds
    if parsed.property_types:
        row["property_type"] = parsed.property_types[0].value
    row = {key: value for key, value in row.items() if value not in (None, "")}
    return [row]


# ------------------------------------------------------------------ normalisation
def _lookup(row: dict[str, Any], mapping: dict[str, str], canonical: str) -> Any:
    source = mapping.get(canonical)
    if source and source in row:
        return row[source]
    if canonical in row:
        return row[canonical]

    # Canonical JSON payloads use slightly different key names.
    for alias in LOOKUP_ALIASES.get(canonical, ()):
        if alias in row:
            return row[alias]
        mapped = mapping.get(alias)
        if mapped and mapped in row:
            return row[mapped]

    return None


def normalise_row(
    row: dict[str, Any],
    mapping: dict[str, str],
    *,
    row_number: int,
    source: str = "agent",
) -> tuple[dict[str, Any] | None, list[Issue], list[Issue]]:
    """Convert a source row into a canonical listing, or explain why not."""
    errors: list[Issue] = []
    warnings: list[Issue] = []

    raw_address = clean_text(_lookup(row, mapping, "address"), limit=300)
    line1 = clean_text(_lookup(row, mapping, "address_line1"), limit=200)
    line2 = clean_text(_lookup(row, mapping, "address_line2"), limit=200)
    postcode = normalise_postcode(_lookup(row, mapping, "postcode"))
    town = clean_text(_lookup(row, mapping, "town"), limit=100) or None

    address = raw_address or " ".join(part for part in (line1, line2) if part)
    if not postcode:
        address, embedded = split_postcode(address)
        postcode = normalise_postcode(embedded)
    elif address:
        address, _ = split_postcode(address)

    if not address or len(address) < 3:
        errors.append(Issue(row_number, "address is required", "address"))

    if postcode and not POSTCODE_LOOSE.match(postcode):
        warnings.append(Issue(row_number, f"postcode looks unusual: {postcode}", "postcode"))

    price_source = _lookup(row, mapping, "price")
    price_paid_source = _lookup(row, mapping, "price_paid")
    price = parse_money(price_source)
    price_paid = parse_money(price_paid_source)
    period = parse_period(price_source)

    if price is None and price_paid is None:
        errors.append(Issue(row_number, "price is required", "price"))

    for label, amount in (("price", price), ("price_paid", price_paid)):
        if amount is not None and amount < 50:
            errors.append(Issue(row_number, f"{label} looks invalid: {amount}", label))
        elif amount is not None and amount < 10_000 and period is None:
            warnings.append(
                Issue(row_number, f"{label} is unusually low: £{amount:,.0f}", label)
            )

    beds = parse_int(_lookup(row, mapping, "beds"))
    if beds is not None and beds > 20:
        warnings.append(Issue(row_number, f"unusual bedroom count: {beds}", "beds"))

    baths = parse_int(_lookup(row, mapping, "baths"))

    area_header = mapping.get("floor_area_sqm", "floor area")
    plot_header = mapping.get("plot_size_sqm", "plot size")
    floor_area = parse_area(_lookup(row, mapping, "floor_area_sqm"), area_header)
    plot_size = parse_area(_lookup(row, mapping, "plot_size_sqm"), plot_header)

    description = clean_text(_lookup(row, mapping, "description"), limit=MAX_DESCRIPTION)
    if len(description) >= MAX_DESCRIPTION:
        warnings.append(
            Issue(row_number, f"description truncated to {MAX_DESCRIPTION} characters", "description")
        )

    listed_at, _ = parse_date_value(_lookup(row, mapping, "listed_at"))
    date_sold, sold_precision = parse_date_value(_lookup(row, mapping, "date_sold"))

    latitude = _parse_coordinate(_lookup(row, mapping, "latitude"), 90)
    longitude = _parse_coordinate(_lookup(row, mapping, "longitude"), 180)

    record: dict[str, Any] = {
        "address_line1": address,
        "address_line2": line2 or None,
        "town": town,
        "postcode": postcode,
        "outcode": postcode.split(" ")[0] if postcode and " " in postcode else postcode,
        "property_type": canonical_property_type(_lookup(row, mapping, "property_type")),
        "num_beds": beds,
        "num_bathrooms": baths,
        "asking_price": price,
        "price_qualifier": parse_qualifier(
            _lookup(row, mapping, "price_qualifier"),
            price_source,
            mapping.get("price", ""),  # the header can carry "Guide Price"
        ),
        "price_period": period,
        "price_paid": price_paid,
        "date_sold": date_sold,
        "sold_precision": sold_precision,
        "listing_status": parse_status(
            _lookup(row, mapping, "status"), has_sold_price=price_paid is not None
        ),
        "tenure": clean_text(_lookup(row, mapping, "tenure"), limit=40) or None,
        "floor_area_sqm": floor_area,
        "plot_size_sqm": plot_size,
        "description": description or None,
        "features": parse_features(_lookup(row, mapping, "features")),
        "agent_ref": clean_text(_lookup(row, mapping, "agent_ref"), limit=64) or None,
        "listed_at": listed_at,
        "latitude": latitude,
        "longitude": longitude,
        "source_url": clean_text(_lookup(row, mapping, "source_url"), limit=500) or None,
        "source": source,
    }

    return (record if not errors else None), errors, warnings


def _parse_coordinate(value: Any, limit: float) -> float | None:
    text = clean_text(value, limit=40)
    if not text:
        return None
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        number = float(match.group())
    return number if math.isfinite(number) and abs(number) <= limit else None


# ------------------------------------------------------------------ pipeline
def import_bytes(
    content: bytes,
    filename: str,
    *,
    mapping_override: dict[str, str] | None = None,
    source: str | None = None,
    max_rows: int = MAX_ROWS,
) -> tuple[list[dict[str, Any]], ImportReport]:
    """Parse and validate an upload without writing anything."""
    if len(content) == 0:
        raise ValueError("Uploaded file is empty")

    detected = detect_format(filename, content)
    report = ImportReport(format=detected, dry_run=True)

    if detected == "xlsx":
        rows, report.encoding = read_xlsx_rows(content)
    elif detected == "json":
        rows, report.encoding = read_json_rows(content)
    elif detected == "jsonl":
        rows, report.encoding = read_jsonl_rows(content)
    elif detected == "xml":
        rows, report.encoding = read_xml_rows(content)
    elif detected == "text":
        rows = row_from_text(decode_bytes(content)[0])
        report.encoding = "utf-8"
    else:
        delimiter = "\t" if detected == "tsv" else None
        rows, report.encoding, chosen = read_csv_rows(content, delimiter)
        report.delimiter = chosen
        report.format = detected

    if len(rows) > max_rows:
        raise ValueError(f"Too many rows ({len(rows)}); limit is {max_rows}")
    if not rows:
        raise ValueError("No data rows found in the upload")

    headers = list(rows[0].keys())
    mapping, confidence, unmapped = detect_mapping(headers)

    if mapping_override:
        for canonical, column in mapping_override.items():
            if canonical not in COLUMN_SYNONYMS:
                report.warnings.append(Issue(0, f"unknown target column: {canonical}"))
                continue
            if isinstance(column, list):
                column = column[0] if column else None
            if column and column in headers:
                # Release any column previously assigned to this canonical field.
                if canonical in mapping and mapping[canonical] != column:
                    released = mapping[canonical]
                    if released not in unmapped:
                        unmapped.append(released)
                mapping[canonical] = column
                confidence[canonical] = 1.0
                if column in unmapped:
                    unmapped.remove(column)
            elif column:
                report.warnings.append(Issue(0, f"column not found: {column}", canonical))

    report.columns = mapping
    report.confidence = confidence
    report.unmapped_columns = unmapped
    report.received = len(rows)

    records: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], int] = {}
    source_name = source or (filename.rsplit(".", 1)[0] if filename else "agent")

    for index, row in enumerate(rows):
        # Header is row 1, so the first data row is row 2 (matches Excel).
        row_number = index + 2
        record, errors, warnings = normalise_row(
            row, mapping, row_number=row_number, source=source_name
        )

        report.errors.extend(errors)
        report.warnings.extend(warnings)

        if record is None:
            report.invalid += 1
            continue

        key = (record["address_line1"].lower(), (record["postcode"] or "").lower())
        if key in seen:
            report.duplicates += 1
            report.warnings.append(
                Issue(
                    row_number,
                    f"duplicate of row {seen[key]} (same address and postcode)",
                )
            )
            continue
        seen[key] = row_number

        record["source_row"] = row_number
        records.append(record)

    report.valid = len(records)
    report.preview = [_preview(record) for record in records[:5]]
    return records, report


def _preview(record: dict[str, Any]) -> dict[str, Any]:
    preview = dict(record)
    if preview.get("description"):
        preview["description"] = preview["description"][:200]
    return preview


# ------------------------------------------------------------------ templates
TEMPLATE_COLUMNS = [
    "Address", "Town", "Postcode", "Price", "Property Type", "Bedrooms",
    "Bathrooms", "Tenure", "Floor Area", "Plot Size", "Status",
    "Description", "Features", "Agent Ref", "URL",
]

TEMPLATE_ROW = [
    "51 Cloverfields", "Haslington", "CW1 5AL", "387000", "Detached", "4",
    "2", "Freehold", "131", "333", "available",
    "A four-bedroom detached house...", "Garden; Garage; Driveway", "ABC-001", "",
]


def build_template_csv() -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow(TEMPLATE_ROW)
    return buffer.getvalue()


def build_template_xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Listings"
    sheet.append(TEMPLATE_COLUMNS)
    sheet.append(TEMPLATE_ROW)
    sheet.freeze_panes = "A2"
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 22

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def column_catalogue() -> dict[str, Any]:
    """Describe the accepted columns for a mapping UI."""
    return {
        "canonical": list(COLUMN_SYNONYMS),
        "synonyms": {key: list(value) for key, value in COLUMN_SYNONYMS.items()},
        "required": ["address", "price (or price_paid)"],
        "formats": list(SUPPORTED_FORMATS),
    }
