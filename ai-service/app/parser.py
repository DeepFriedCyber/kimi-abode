"""Natural-language query parser with tiered failover."""

from __future__ import annotations

import re
from enum import IntEnum, auto

from .schemas import ParsedQuery, PropertyType


# ---------- Bed types ---------------------------------------------------
BED_PATTERNS = [
    (re.compile(r"\b(\d+)[\s-]+\d+(?:[\s-]+(?:to|-|–)?)?\s*bed(?:room)?s?\b", re.I), "range_beds"),
    (re.compile(r"\b(\d+)\s*bed(?:room)?s?\b", re.I), "min_beds"),
]

# ---------- Price patterns -----------------------------------------------
PRICE_PATTERN = re.compile(
    r"(?:under|below|less than|max\s+£|up\s+to)\s*£?([\d,.]+)[kKmM]?"
)

# ---------- Location keywords ---------------------------------------------
LOCATION_KEYWORDS = {
    "in", "near", "around", "close to", "within", "south", "north",
    "east", "west", "southwest", "southeast", "northwest", "northeast",
}

# ---------- Type patterns (sorted longest-first so compound matches win) ---
TYPE_PATTERNS: list[tuple[re.Pattern, PropertyType]] = [
    (re.compile(r"semi[-\s]detached", re.I), PropertyType.SEMI_DETACHED),
    (re.compile(r"m\s?a\s?i\s?s\s?o\s?n\s?e\s?t\s?t\s?", re.I), PropertyType.MAISONETTE),
    (re.compile(r"\bbungalow\b", re.I), PropertyType.BUNGALOW),
    (re.compile(r"\bflats?\b", re.I), PropertyType.FLAT),
    (re.compile(r"\bdetached\b", re.I), PropertyType.DETACHED),
    (re.compile(r"\bterraced\b|\bterrace\b", re.I), PropertyType.TERRACED),
]


class Tier(IntEnum):
    DETERMINISTIC = auto()  # high-confidence structured parse
    LLM_1 = auto()           # primary provider
    LLM_2 = auto()           # failover provider
    SEMANTIC_CACHE = auto()  # cached result
    FORCED_DETERMINISTIC = auto()  # total LLM outage fallback


async def parse_query(query: str, *, llm_parse=None) -> ParsedQuery:
    """Parse a natural-language query. Returns result even when price found."""
    result = _deterministic_parse(query)

    # Fall back to LLM for complex queries (no location or price detected)
    if not result.has_location and not result.has_price and llm_parse:
        try:
            llm_result = await llm_parse(query)
            return ParsedQuery(
                **{**llm_result, "tier": Tier.LLM_1.name},
                raw=query,
            )
        except Exception:
            pass

    return ParsedQuery(**{**result.model_dump(), "tier": Tier.DETERMINISTIC.name})


def _deterministic_parse(query: str) -> ParsedQuery:
    """Extract structured fields from natural language using regex heuristics."""
    q_lower = query.lower()

    # --- beds ---------------------------------------------------------------
    min_beds: int | None = None
    for pattern, field in BED_PATTERNS:
        m = pattern.search(query)
        if m:
            val = m.group(1).replace(",", "")
            min_beds = int(val)
            break

    # --- price --------------------------------------------------------------
    max_price: float | None = None
    pm = PRICE_PATTERN.search(q_lower)
    has_price = False
    if pm:
        raw_val = pm.group(1).replace(",", "")
        k_or_m = q_lower[pm.start():pm.end()].lower()
        if "k" in k_or_m or "m" in k_or_m:
            max_price = float(raw_val.replace("k", "").replace("K", "")) * 1000
        else:
            max_price = float(raw_val)
        has_price = True

    # --- property types (compound-aware; longest match wins, skip subsumed) --
    found_types: list[PropertyType] = []
    matched_spans: list[tuple[int, int]] = []
    for pattern, ptype in TYPE_PATTERNS:
        m = pattern.search(query)
        if m:
            overlaps = any(not (m.end() <= s or m.start() >= e) for s, e in matched_spans)
            if not overlaps:
                found_types.append(ptype)
                matched_spans.append((m.start(), m.end()))

    # --- location -----------------------------------------------------------
    location: str | None = None
    district: str | None = None
    outcode: str | None = None
    has_location = False

    # Find position boundaries for beds and price patterns
    bed_end = 0
    for pattern, field in BED_PATTERNS:
        m = pattern.search(query)
        if m and m.end() > bed_end:
            bed_end = m.end()
    price_start = len(q_lower)  # default: no price found
    pm_price = PRICE_PATTERN.search(q_lower)
    if pm_price:
        price_start = pm_price.start()

    # Look for LOCATION_KEYWORDS between bed_end and price_start
    best_loc_end = 0
    PRICE_WORDS = {"under", "below", "max", "up", "to", "about", "approx", "around"}
    for kw in LOCATION_KEYWORDS:
        idx = q_lower.find(kw, bed_end)
        if idx == -1 or idx + len(kw) > price_start:
            continue
        after = query[idx + len(kw):].strip().split()
        filtered = [w for w in after if not re.match(r"^[\d£$€]", w) and len(w) > 2 and w.lower() not in LOCATION_KEYWORDS and w.lower() not in PRICE_WORDS]
        candidate = " ".join(filtered[:3])
        if candidate and len(candidate) > 2 and (idx + len(kw)) > best_loc_end:
            best_loc_end = idx + len(kw)
            location = candidate.title()
            has_location = True

    # Check for UK postcode outcode
    pc_match = re.search(r"\b([A-Z]{1,2}\d[A-Z]?)\s*\d", query, re.I)
    if pc_match:
        outcode = pc_match.group(1).upper()
        # If location wasn't found but we have an outcode that maps to a town, use gazetteer
        from .gazetteer import outcode_to_town
        town_from_outcode = outcode_to_town(outcode)
        if town_from_outcode and not has_location:
            location = town_from_outcode
            has_location = True

    return ParsedQuery(
        raw=query,
        tier="",  # filled by caller with tier name
        min_beds=min_beds,
        max_price=max_price,
        property_types=found_types,
        location=location,
        district=district,
        outcode=outcode,
        has_location=has_location,
        has_price=has_price,
    )
