"""Natural-language amenity questions — brand-aware, deterministic answers.

The LLM is deliberately not used for "how far is the nearest Tesco?": the answer
must come from POI data and arithmetic, not generation. The same function is
used by the REST endpoint and by the chat service (before any LLM call).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .scorer import haversine_m

WALK_METRES_PER_MINUTE = 80.0
WALK_ASSUMPTION = "3 mph"
METRES_PER_MILE = 1_609.344
METRES_PER_YARD = 0.9144
DEFAULT_RADIUS_M = 5_000
MAX_RADIUS_M = 20_000
FALLBACK_RADIUS_M = 15_000
ATTRIBUTION = "© OpenStreetMap contributors"

# Query terms -> OSM-derived category. Longest term wins.
CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "supermarket": ("supermarket", "supermarkets", "superstore", "superstores", "grocery", "groceries", "food shop"),
    "convenience": ("convenience store", "convenience stores", "corner shop", "local shop", "mini market"),
    "fitness": ("gym", "gyms", "fitness", "leisure centre", "leisure center", "sports centre", "sports center", "workout"),
    "school": ("school", "schools", "primary school", "secondary school", "high school", "infant school", "junior school"),
    "nursery": ("nursery", "nurseries", "childcare", "preschool"),
    "pharmacy": ("pharmacy", "pharmacies", "chemist", "chemists"),
    "doctors": ("doctor", "doctors", "gp", "gps", "surgery", "medical centre", "medical center", "health centre"),
    "dentist": ("dentist", "dentists", "dental"),
    "hospital": ("hospital", "hospitals", "a and e", "casualty"),
    "park": ("park", "parks", "green space", "open space"),
    "playground": ("playground", "playgrounds", "play area"),
    "station": ("station", "stations", "train station", "railway station", "train", "rail"),
    "cafe": ("cafe", "cafes", "coffee shop", "coffee"),
    "restaurant": ("restaurant", "restaurants", "takeaway", "takeaways"),
    "pub": ("pub", "pubs"),
    "bar": ("bar", "bars"),
}

CATEGORY_LABELS: dict[str, str] = {
    "supermarket": "supermarket",
    "convenience": "convenience store",
    "fitness": "gym",
    "school": "school",
    "nursery": "nursery",
    "pharmacy": "pharmacy",
    "doctors": "GP surgery",
    "dentist": "dentist",
    "hospital": "hospital",
    "park": "park",
    "playground": "playground",
    "station": "train station",
    "cafe": "café",
    "restaurant": "restaurant",
    "pub": "pub",
    "bar": "bar",
}

PLURAL_LABELS: dict[str, str] = {
    "supermarket": "supermarkets",
    "convenience": "convenience stores",
    "fitness": "gyms",
    "school": "schools",
    "nursery": "nurseries",
    "pharmacy": "pharmacies",
    "doctors": "GP surgeries",
    "dentist": "dentists",
    "hospital": "hospitals",
    "park": "parks",
    "playground": "playgrounds",
    "station": "train stations",
    "cafe": "cafés",
    "restaurant": "restaurants",
    "pub": "pubs",
    "bar": "bars",
}

BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "tesco": ("tesco", "tesco express", "tesco extra", "tesco superstore"),
    "sainsburys": ("sainsbury s", "sainsburys", "sainsbury"),
    "asda": ("asda",),
    "aldi": ("aldi",),
    "lidl": ("lidl",),
    "morrisons": ("morrisons",),
    "coop": ("co op", "coop", "co operative"),
    "waitrose": ("waitrose",),
    "marksandspencer": ("m and s", "marks and spencer", "marks spencer"),
    "iceland": ("iceland",),
    "heronfoods": ("heron foods",),
    "puregym": ("puregym", "pure gym"),
    "jdgyms": ("jd gyms", "jd gym"),
    "gymgroup": ("the gym group", "the gym"),
    "davidlloyd": ("david lloyd",),
    "nuffield": ("nuffield", "nuffield health"),
    "anytimefitness": ("anytime fitness",),
    "boots": ("boots",),
    "well": ("well pharmacy",),
    "costa": ("costa",),
    "starbucks": ("starbucks",),
    "caffenero": ("caffe nero", "nero"),
    "greggs": ("greggs",),
}

BRAND_DISPLAY: dict[str, str] = {
    "tesco": "Tesco",
    "sainsburys": "Sainsbury's",
    "asda": "Asda",
    "aldi": "Aldi",
    "lidl": "Lidl",
    "morrisons": "Morrisons",
    "coop": "Co-op",
    "waitrose": "Waitrose",
    "marksandspencer": "M&S Food",
    "iceland": "Iceland",
    "heronfoods": "Heron Foods",
    "puregym": "PureGym",
    "jdgyms": "JD Gyms",
    "gymgroup": "The Gym Group",
    "davidlloyd": "David Lloyd",
    "nuffield": "Nuffield Health",
    "anytimefitness": "Anytime Fitness",
    "boots": "Boots",
    "well": "Well Pharmacy",
    "costa": "Costa",
    "starbucks": "Starbucks",
    "caffenero": "Caffè Nero",
    "greggs": "Greggs",
}

BRAND_CATEGORY: dict[str, str] = {
    **{brand: "supermarket" for brand in (
        "tesco", "sainsburys", "asda", "aldi", "lidl", "morrisons",
        "coop", "waitrose", "marksandspencer", "iceland", "heronfoods",
    )},
    **{brand: "fitness" for brand in (
        "puregym", "jdgyms", "gymgroup", "davidlloyd", "nuffield", "anytimefitness",
    )},
    "boots": "pharmacy",
    "well": "pharmacy",
    **{brand: "cafe" for brand in ("costa", "starbucks", "caffenero")},
    "greggs": "cafe",
}

RADIUS_RE = re.compile(
    r"(?:within|in|under|less than|about|around|inside)\s+"
    r"(\d+(?:\.\d+)?)\s*"
    r"(km|kilometres?|kilometers?|m|metres?|meters?|miles?|mi)\b",
    re.I,
)
PLURAL_HINTS = ("what", "which", "any", "list", "show", "are there", "all the")


@dataclass(frozen=True)
class PoiQuery:
    category: str | None
    brand: str | None
    radius_m: int
    limit: int


def normalise(text: str) -> str:
    text = (text or "").lower().replace("&", " and ")
    text = text.replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _contains_token(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


def detect_brand(normalised: str) -> str | None:
    for brand, aliases in BRAND_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if _contains_token(normalised, alias):
                return brand
    return None


def detect_category(normalised: str) -> str | None:
    terms = sorted(
        ((category, term) for category, values in CATEGORY_TERMS.items() for term in values),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for category, term in terms:
        if _contains_token(normalised, term):
            return category
    return None


def parse_radius(normalised: str) -> int:
    match = RADIUS_RE.search(normalised)
    if not match:
        return DEFAULT_RADIUS_M

    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("k"):
        metres = value * 1_000
    elif unit.startswith("mi"):
        metres = value * 1_609.344
    else:
        metres = value

    return max(200, min(int(metres), MAX_RADIUS_M))


def parse_poi_query(text: str) -> PoiQuery | None:
    normalised = normalise(text)
    if not normalised:
        return None

    brand = detect_brand(normalised)
    category = detect_category(normalised)

    if brand:
        brand_category = BRAND_CATEGORY.get(brand)
        # A format word ("superstore") narrows the search; otherwise keep all
        # formats for that brand so "nearest Tesco" can be an Express.
        if brand_category == "supermarket" and (
            "superstore" in normalised or "supermarket" in normalised
        ):
            category = "supermarket"

    if brand is None and category is None:
        return None

    radius = parse_radius(normalised)
    plural = _is_plural(normalised)
    return PoiQuery(category=category, brand=brand, radius_m=radius, limit=5 if plural else 1)


def _is_plural(normalised: str) -> bool:
    tokens = normalised.split()
    if any(hint in normalised for hint in PLURAL_HINTS):
        return True
    plural_terms = {term for values in CATEGORY_TERMS.values() for term in values if term.endswith("s")}
    return any(token in plural_terms for token in tokens)


def _matches_brand(poi: dict[str, Any], brand: str) -> bool:
    haystack = normalise(f"{poi.get('brand') or ''} {poi.get('name') or ''}")
    return any(_contains_token(haystack, alias) for alias in BRAND_ALIASES.get(brand, ()))


def format_distance(metres: float) -> str:
    """UK display format: yards under a tenth of a mile, then miles."""
    miles = metres / METRES_PER_MILE
    if miles < 0.1:
        yards = max(10, math.floor(metres / METRES_PER_YARD / 10 + 0.5) * 10)
        return f"{yards:,} yards"
    if miles < 10:
        # Half-up rounding, matching the frontend's Math.round exactly.
        rounded = math.floor(miles * 10 + 0.5) / 10
        if rounded == 1:
            return "1 mile"
        if rounded == int(rounded):
            return f"{int(rounded)} miles"
        return f"{rounded:.1f} miles"
    return f"{math.floor(miles + 0.5):.0f} miles"


def _walk_minutes(metres: float) -> int:
    return max(1, round(metres / WALK_METRES_PER_MINUTE))


def _map_url(poi: dict[str, Any]) -> str:
    lat, lon = poi["lat"], poi["lon"]
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"


SECONDARY_MARKERS = ("secondary", "high school", "sixth form", "college")
PRIMARY_MARKERS = ("primary", "infant", "junior", "first school")


def _school_phase(poi: dict[str, Any]) -> str | None:
    """Best-effort phase from ISCED tags, then the name."""
    isced = str(poi.get("isced_level") or "")
    levels = {level.strip() for level in isced.split(";")}
    if "1" in levels:
        return "primary"
    if levels & {"2", "3"}:
        return "secondary"

    name = normalise(poi.get("name") or "")
    if any(marker in name for marker in PRIMARY_MARKERS):
        return "primary"
    if any(marker in name for marker in SECONDARY_MARKERS):
        return "secondary"
    return None


def _collect(
    pois: Iterable[dict[str, Any]],
    lat: float,
    lon: float,
    *,
    category: str | None,
    brand: str | None,
    radius_m: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    for poi in pois:
        if category and poi.get("category") != category:
            continue
        if brand and not _matches_brand(poi, brand):
            continue
        if poi.get("lat") is None or poi.get("lon") is None:
            continue

        distance = haversine_m(lat, lon, poi["lat"], poi["lon"])
        if distance <= radius_m:
            matches.append({**poi, "distance_m": distance, "walk_time_min": _walk_minutes(distance)})

    # "Gyms" should not return cricket clubs when an actual gym exists.
    if category == "fitness":
        gyms = [poi for poi in matches if poi.get("subtype") == "gym"]
        if gyms:
            matches = gyms

    matches.sort(key=lambda item: item["distance_m"])
    return matches


def _result_payload(poi: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": poi.get("name"),
        "brand": poi.get("brand"),
        "category": poi.get("category"),
        "subtype": poi.get("subtype"),
        "street": poi.get("street"),
        "distance_m": round(poi["distance_m"], 1),
        "walk_time_min": poi["walk_time_min"],
        "opening_hours": poi.get("opening_hours"),
        "map_url": _map_url(poi),
    }


def _answer_text(
    query: PoiQuery,
    results: list[dict[str, Any]],
    total: int,
    radius_m: int,
    *,
    label_override: str | None = None,
) -> str:
    radius_label = format_distance(radius_m)
    label = label_override
    if label is None and query.brand:
        label = BRAND_DISPLAY.get(query.brand)
    if label is None and query.category:
        label = CATEGORY_LABELS.get(query.category, query.category)
    label = label or "amenity"

    if not results:
        article = "an" if label[0].lower() in "aeiou" else "a"
        return f"I couldn't find {article} {label} within {radius_label} of this property."

    closest = results[0]
    distance = format_distance(closest["distance_m"])
    walk = closest["walk_time_min"]
    where = f" on {closest['street']}" if closest.get("street") else ""

    if query.limit == 1:
        if normalise(closest["name"] or "") == normalise(label):
            return f"The nearest {label} is about {distance} away (roughly {walk} min walk)."
        return (
            f"The nearest {label} is {closest['name']}{where}, about {distance} away "
            f"(roughly {walk} min walk)."
        )

    plural = PLURAL_LABELS.get(query.category or "", f"{label}s")

    listed = ", ".join(
        f"{item['name']} ({format_distance(item['distance_m'])})" for item in results
    )
    return (
        f"I found {total} {plural} within {radius_label}: {listed}. "
        f"The closest is {closest['name']} at {distance}."
    )


def answer_poi_question(
    pois: list[dict[str, Any]],
    lat: float,
    lon: float,
    text: str,
    *,
    max_radius_m: int = FALLBACK_RADIUS_M,
) -> dict[str, Any] | None:
    """Answer a nearby-amenity question. Returns None when it is not one."""
    query = parse_poi_query(text)
    if query is None:
        return None

    fallback_note: str | None = None
    label_override: str | None = None
    radius = query.radius_m

    results = _collect(
        pois, lat, lon, category=query.category, brand=query.brand, radius_m=radius
    )

    # A brand match in any format is better than a category guess.
    if not results and query.brand and query.category:
        results = _collect(pois, lat, lon, category=None, brand=query.brand, radius_m=radius)
        if results:
            fallback_note = (
                f"There is no {BRAND_DISPLAY.get(query.brand, query.brand)} "
                f"{CATEGORY_LABELS.get(query.category, query.category)} within "
                f"{format_distance(radius)}; the nearest {BRAND_DISPLAY.get(query.brand, query.brand)} "
                f"is {CATEGORY_LABELS.get(results[0].get('category'), results[0].get('category'))}."
            )

    # No brand at all -> nearest same-category alternative.
    if not results and query.brand:
        category = query.category or BRAND_CATEGORY.get(query.brand)
        if category:
            results = _collect(pois, lat, lon, category=category, brand=None, radius_m=radius)
            if results:
                fallback_note = (
                    f"There is no {BRAND_DISPLAY.get(query.brand, query.brand)} "
                    f"within {format_distance(radius)}."
                )
                label_override = CATEGORY_LABELS.get(category, category)

    # Widen once when nothing is within the requested radius.
    if not results and radius < max_radius_m:
        radius = max_radius_m
        results = _collect(
            pois, lat, lon, category=query.category, brand=query.brand, radius_m=radius
        )

    normalised_text = normalise(text)
    if query.category == "school" and results:
        wants_primary = any(
            marker in normalised_text for marker in ("primary", "infant", "junior")
        )
        wants_secondary = any(
            marker in normalised_text for marker in ("secondary", "high school", "sixth form")
        )
        if wants_primary:
            results = [item for item in results if _school_phase(item) != "secondary"]
        elif wants_secondary:
            results = [item for item in results if _school_phase(item) != "primary"]

    total = len(results)
    limited = results[: query.limit]
    answer = _answer_text(query, limited, total, radius, label_override=label_override)
    if fallback_note:
        answer = f"{fallback_note} {answer}"

    return {
        "answer": answer,
        "intent": {
            "category": query.category,
            "brand": query.brand,
            "radius_m": radius,
            "limit": query.limit,
        },
        "results": [_result_payload(item) for item in limited],
        "total_matches": total,
        "fallback": fallback_note,
        "distance_type": "straight_line",
        "walk_assumption": WALK_ASSUMPTION,
        "attribution": ATTRIBUTION,
        "source": "openstreetmap",
    }

