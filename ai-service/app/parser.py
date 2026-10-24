"""Natural-language query parser with tiered failover.

The deterministic tier handles the common cases ("3 bed semi in Sandbach under
£250k") without an LLM. Extraction is ordered and allocation-free so the same
query always produces the same filters.
"""

from __future__ import annotations

import re
from enum import IntEnum, auto

from .schemas import ParsedQuery, PropertyType

# ---------- Numeric filters ----------------------------------------------
BED_RANGE_PATTERN = re.compile(
    r"\b(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*-?\s*bed(?:room)?s?\b", re.I
)
BED_PATTERN = re.compile(r"\b(\d{1,2})\s*\+?\s*-?\s*bed(?:room)?s?\b", re.I)
MIN_BED_PATTERN = re.compile(r"\d\s*\+|\bat\s+least\b|\bover\b|\bminimum\b|\bplus\b", re.I)

# "under £250k", "up to 300,000", "budget of £1.2m"
PRICE_PATTERN = re.compile(
    r"(?:under|below|less\s+than|up\s+to|max(?:imum)?|budget(?:\s+of)?)"
    r"\s*£?\s*([\d][\d,]*(?:\.\d+)?)\s*([kKmM])?",
    re.I,
)

# A bare "£250k" is treated as a budget.
BARE_PRICE_PATTERN = re.compile(r"£\s*([\d][\d,]*(?:\.\d+)?)\s*([kKmM])?", re.I)

# ---------- Location keywords (longest first — order is significant) ------
LOCATION_KEYWORDS = [
    "close to", "southwest", "southeast", "northwest", "northeast",
    "within", "around", "near", "south", "north", "east", "west", "in",
]
LOCATION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in LOCATION_KEYWORDS) + r")\b", re.I
)

# Words that should never become part of a town name.
NON_LOCATION_WORDS = {
    "under", "below", "less", "than", "up", "to", "max", "maximum", "budget",
    "about", "approx", "approximately", "and", "with", "for", "the", "a", "an",
    "bed", "beds", "bedroom", "bedrooms", "house", "home", "property",
    "properties", "flat", "apartment", "apartments", "detached", "semi",
    "terraced", "terrace", "bungalow", "maisonette", "good", "great", "nice",
    "area", "areas", "town", "village", "city", "centre", "center",
}

# ---------- Type patterns (compound matches are listed first) -------------
TYPE_PATTERNS: list[tuple[re.Pattern[str], PropertyType]] = [
    (re.compile(r"semi[-\s]?detached", re.I), PropertyType.SEMI_DETACHED),
    (re.compile(r"\bsemi\b", re.I), PropertyType.SEMI_DETACHED),
    (re.compile(r"maisonette", re.I), PropertyType.MAISONETTE),
    (re.compile(r"\bbungalows?\b", re.I), PropertyType.BUNGALOW),
    (re.compile(r"\bflats?\b|\bapartments?\b", re.I), PropertyType.FLAT),
    (re.compile(r"\bdetached\b", re.I), PropertyType.DETACHED),
    (re.compile(r"\bterraced\b|\bterrace\b", re.I), PropertyType.TERRACED),
]

FULL_POSTCODE_PATTERN = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}\b", re.I)
OUTCODE_PATTERN = FULL_POSTCODE_PATTERN
# A standalone outcode ("CW11", "in ST7"). Case-insensitive, then validated.
BARE_OUTCODE_PATTERN = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\b", re.I)
LOCATION_TAIL_PATTERN = re.compile(
    r"\b(?:in|near|around|within|close\s+to)\s+(?:the\s+)?$", re.I
)

# "between 150k and 250k", "from 150000 to 250000", "150000-250000"
PRICE_RANGE_PATTERN = re.compile(
    r"(?:between\s+|from\s+)?£?\s*([\d][\d,]*(?:\.\d+)?)\s*([kKmM])?"
    r"\s*(?:-|–|to|and)\s*£?\s*([\d][\d,]*(?:\.\d+)?)\s*([kKmM])?",
    re.I,
)

MIN_PRICE = 1_000
MAX_PRICE = 50_000_000
MAX_BEDS = 20


class Tier(IntEnum):
    DETERMINISTIC = auto()
    LLM_1 = auto()
    LLM_2 = auto()
    SEMANTIC_CACHE = auto()
    FORCED_DETERMINISTIC = auto()


async def parse_query(query: str, *, llm_parse=None) -> ParsedQuery:
    """Parse a query deterministically, falling back to an LLM only when the
    deterministic tier finds no structured signal."""
    result = _deterministic_parse(query)

    if not result.has_location and not result.has_price and llm_parse:
        try:
            llm_result = await llm_parse(query)
            return ParsedQuery(**{**llm_result, "tier": Tier.LLM_1.name}, raw=query)
        except Exception:  # noqa: BLE001 - fall back to deterministic result
            pass

    return ParsedQuery(**{**result.model_dump(), "tier": Tier.DETERMINISTIC.name})


def _parse_number(raw: str, suffix: str | None) -> float:
    """Convert '250,000' + 'k' into a float, rejecting implausible values."""
    value = float(raw.replace(",", ""))
    if suffix:
        if suffix.lower() == "k":
            value *= 1_000
        elif suffix.lower() == "m":
            value *= 1_000_000
    return value


def _extract_beds(query: str) -> tuple[int | None, int | None]:
    """Return (min_beds, max_beds) from '3 bed' or '1-4 bedroom'."""
    range_match = BED_RANGE_PATTERN.search(query)
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        low, high = min(low, high), max(low, high)
        if 0 <= low <= MAX_BEDS and 0 <= high <= MAX_BEDS:
            return low, high
        return None, None

    single = BED_PATTERN.search(query)
    if single:
        value = int(single.group(1))
        if 0 <= value <= MAX_BEDS:
            # "2 bed" means exactly two, as it does on the portals. "2+ bed"
            # or "at least 2 bed" is a floor, not an exact count.
            if MIN_BED_PATTERN.search(query):
                return value, None
            return value, value

    return None, None


def _extract_price(query: str) -> tuple[float | None, float | None, bool]:
    """Return (min_price, max_price, has_price)."""
    range_match = PRICE_RANGE_PATTERN.search(query)
    if range_match and not _inside_span(range_match.start(), _bed_spans(query)):
        low = _parse_number(range_match.group(1), range_match.group(2))
        high = _parse_number(range_match.group(3), range_match.group(4))
        low, high = min(low, high), max(low, high)
        if _plausible_price(low) and _plausible_price(high):
            return low, high, True

    match = PRICE_PATTERN.search(query)
    if not match:
        bare = BARE_PRICE_PATTERN.search(query)
        if not bare:
            return None, None, False
        value = _parse_number(bare.group(1), bare.group(2))
        return None, value, _plausible_price(value)

    value = _parse_number(match.group(1), match.group(2))
    if not _plausible_price(value):
        return None, None, False
    return None, value, True


def _plausible_price(value: float) -> bool:
    return MIN_PRICE <= value <= MAX_PRICE


def _extract_types(query: str) -> list[PropertyType]:
    """Match property types, preferring the longest non-overlapping match."""
    found: list[PropertyType] = []
    spans: list[tuple[int, int]] = []

    for pattern, property_type in TYPE_PATTERNS:
        for match in pattern.finditer(query):
            if any(not (match.end() <= start or match.start() >= end) for start, end in spans):
                continue
            found.append(property_type)
            spans.append((match.start(), match.end()))
            break  # one match per pattern is enough

    return found


def _bed_spans(query: str) -> list[tuple[int, int]]:
    return [match.span() for match in (BED_RANGE_PATTERN, BED_PATTERN) for match in match.finditer(query)]


def _extract_outcode(query: str) -> str | None:
    """Return an outcode from a full postcode or a standalone token.

    "in CW11" is a postcode search, not a town called Cw11. A lowercase token
    is only accepted straight after a location keyword, so ordinary words and
    model numbers do not become filters.
    """
    full = FULL_POSTCODE_PATTERN.search(query)
    if full:
        return full.group(1).upper()

    excluded = _excluded_spans(query)
    for match in BARE_OUTCODE_PATTERN.finditer(query):
        if _inside_span(match.start(), excluded):
            continue
        token = match.group(1)
        if token.isupper() or LOCATION_TAIL_PATTERN.search(query[: match.start()]):
            return token.upper()
    return None


def _excluded_spans(query: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in (BED_RANGE_PATTERN, BED_PATTERN, PRICE_PATTERN):
        spans.extend((m.start(), m.end()) for m in pattern.finditer(query))
    return spans


def _inside_span(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _candidate_words(query: str, start: int, limit: int = 3) -> list[str]:
    """Collect up to `limit` usable words following a location keyword."""
    tail = query[start:].strip()
    words: list[str] = []

    for raw in tail.split():
        word = raw.strip(".,;:!?()\"'")
        if not word:
            continue
        lowered = word.lower()
        if (
            len(word) <= 2
            or lowered in NON_LOCATION_WORDS
            or lowered in LOCATION_KEYWORDS
            or re.match(r"^[\d£$€]", word)
        ):
            # Stop at the first non-location token; continuing would pull in
            # unrelated text ("in Sandbach under 300k").
            break
        words.append(word)
        if len(words) >= limit:
            break

    return words


def _extract_location(query: str) -> str | None:
    """Pick the location keyword whose candidate town ends latest in the query."""
    excluded = _excluded_spans(query)
    best: tuple[int, str] | None = None

    for match in LOCATION_PATTERN.finditer(query):
        if _inside_span(match.start(), excluded):
            continue
        words = _candidate_words(query, match.end())
        if not words:
            continue
        candidate = " ".join(words)
        if best is None or match.end() > best[0]:
            best = (match.end(), candidate.title())

    return best[1] if best else None


def _deterministic_parse(query: str) -> ParsedQuery:
    """Extract structured fields from natural language using regex heuristics."""
    query = (query or "").strip()

    min_beds, max_beds = _extract_beds(query)
    min_price, max_price, has_price = _extract_price(query)
    property_types = _extract_types(query)

    location = _extract_location(query)
    district = None
    outcode = _extract_outcode(query)

    # "in CW11" yields candidate "Cw11" from the keyword scan; that is a
    # postcode, not a town, and filtering town ILIKE '%Cw11%' matches nothing.
    if location and outcode and location.replace(" ", "").upper() == outcode:
        location = None
    if location and re.fullmatch(r"[A-Za-z]{1,2}\d[A-Za-z\d]?", location.replace(" ", "")):
        location = None

    # Deliberately no outcode -> town inference: an outcode spans several towns
    # (CW1 covers both Crewe and Haslington), so adding a town filter would
    # exclude the property the user asked for.

    if not location and not outcode:
        # "Crewe between 150k and 250k" has no preposition; fall back to a
        # gazetteer scan so the town is not silently dropped.
        from .gazetteer import match_towns

        towns = match_towns(query)
        if towns:
            location = max(towns, key=len)

    return ParsedQuery(
        raw=query,
        tier="",
        min_beds=min_beds,
        max_beds=max_beds,
        min_price=min_price,
        max_price=max_price,
        property_types=property_types,
        location=location,
        district=district,
        outcode=outcode,
        has_location=bool(location or outcode),
        has_price=has_price,
    )
