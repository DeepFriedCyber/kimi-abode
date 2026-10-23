"""Deduplication — group listings that refer to the same property.

Two properties with different house numbers are never merged: a previous
heuristic treated numbers within 5 of each other as the same address, which
silently dropped real listings.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

_ABBREVIATIONS = {
    "rd": "road", "st": "street", "ave": "avenue", "av": "avenue",
    "ln": "lane", "dr": "drive", "ct": "court", "cl": "close",
    "cres": "crescent", "gdns": "gardens", "pl": "place", "sq": "square",
    "ter": "terrace", "wy": "way", "blvd": "boulevard",
}

# "Flat 2, 23 Station Road" -> the property number is 23, not 2.
_UNIT_PREFIX = re.compile(
    r"^\s*(?:flat|apartment|apt|unit|suite)\s*[a-z0-9]+\s*[,/\-]?\s*", re.I
)
_NUMBER_RE = re.compile(r"\d+")


def normalise_address(address: str) -> str:
    """Lower-case, expand abbreviations, and strip punctuation."""
    text = (address or "").lower().strip()
    # Drop a leading unit prefix but keep the building number.
    text = _UNIT_PREFIX.sub("", text)
    text = re.sub(r"[.,;:!?&/\\]", " ", text)
    tokens = [
        _ABBREVIATIONS.get(token, token)
        for token in text.split()
    ]
    return " ".join(tokens)


def _house_number(address: str) -> int | None:
    cleaned = _UNIT_PREFIX.sub("", address or "")
    match = _NUMBER_RE.search(cleaned)
    return int(match.group()) if match else None


def _number_conflict(left: str, right: str) -> bool:
    """True when both addresses have house numbers and they differ."""
    left_number = _house_number(left)
    right_number = _house_number(right)
    return (
        left_number is not None
        and right_number is not None
        and left_number != right_number
    )


def _postcode_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Two records in different postcodes are different properties.

    Without this, "23 Station Road" in CW11 and in CW1 would be merged.
    """
    left_postcode = (left.get("postcode") or "").replace(" ", "").upper()
    right_postcode = (right.get("postcode") or "").replace(" ", "").upper()
    return bool(left_postcode and right_postcode and left_postcode != right_postcode)


def _address_similarity(left: str, right: str) -> float:
    """Similarity in [0, 1] using token overlap plus sequence ratio."""
    a = normalise_address(left)
    b = normalise_address(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    tokens_a, tokens_b = set(a.split()), set(b.split())
    union = tokens_a | tokens_b
    jaccard = len(tokens_a & tokens_b) / len(union) if union else 0.0
    if jaccard == 0.0:
        return 0.0

    # SequenceMatcher is O(n*m) but with a tiny constant compared with the
    # hand-rolled DP matrix this replaced, and needs no allocation per pair.
    ratio = SequenceMatcher(None, a, b).ratio()
    return max(jaccard, ratio)


def _completeness_score(item: dict[str, Any]) -> int:
    fields = ("address_line1", "town", "postcode", "num_beds", "price_paid", "property_type")
    return sum(1 for field in fields if item.get(field))


def deduplicate_listings(
    listings: list[dict[str, Any]],
    *,
    threshold: float = 0.9,
) -> list[dict[str, Any]]:
    """Group duplicate addresses, keeping the most complete record.

    Missing fields from lower-ranked duplicates are copied onto the survivor so
    merging does not lose data.
    """
    groups: list[list[dict[str, Any]]] = []

    for listing in listings:
        address = listing.get("address_line1", "")
        if not address:
            continue

        target: list[dict[str, Any]] | None = None
        for group in groups:
            representative = group[0]
            if _postcode_conflict(listing, representative):
                continue
            if _number_conflict(address, representative.get("address_line1", "")):
                continue
            if _address_similarity(address, representative.get("address_line1", "")) >= threshold:
                target = group
                break

        if target is None:
            groups.append([listing])
        else:
            target.append(listing)

    results: list[dict[str, Any]] = []
    for group in groups:
        best = max(group, key=_completeness_score).copy()
        for member in group:
            for key, value in member.items():
                if not best.get(key) and value:
                    best[key] = value
        results.append(best)

    return results


def addresses_match(left: str, right: str, *, threshold: float = 0.9) -> bool:
    """Public helper used by ingestion QA."""
    if _number_conflict(left, right):
        return False
    return _address_similarity(left, right) >= threshold
