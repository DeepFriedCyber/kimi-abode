"""Column mapping resolver — dynamically maps incoming CSV columns."""

from __future__ import annotations

import re


# Fuzzy-match patterns for common column names → standard field names.
COLUMN_ALIASES: dict[str, list[str]] = {
    "address": ["address", "full_address", "property_address", "addr", "location"],
    "town": ["town", "city", "locality", "settlement"],
    "postcode": ["postcode", "post_code", "outward_code", "inward_code", "postal_code"],
    "price": ["price", "asking_price", "sale_price", "amount", "value"],
    "beds": ["beds", "bedrooms", "num_bedrooms", "bed_count", "bedroom_count"],
    "property_type": [
        "property_type", "prop_type", "subtype", "house_type", "property_subtype",
    ],
}


def resolve_columns(headers: list[str]) -> dict[str, str]:
    """Map CSV headers to standard field names."""
    mapping = {}
    for std_field, aliases in COLUMN_ALIASES.items():
        for header in headers:
            clean = header.strip().lower().replace(" ", "_")
            if clean in aliases or any(alias in clean for alias in aliases):
                mapping[std_field] = header
                break
    return mapping


def fuzzy_match_columns(headers: list[str], tolerance: float = 0.6) -> dict[str, str]:
    """Use fuzzy matching to resolve ambiguous column names."""
    mapping = {}
    for std_field, aliases in COLUMN_ALIASES.items():
        best_score = 0
        best_header = None
        for header in headers:
            clean = header.strip().lower()
            for alias in aliases:
                score = _token_overlap(clean, alias)
                if score > best_score:
                    best_score = score
                    best_header = header
        if best_score >= tolerance and best_header:
            mapping[std_field] = best_header
    return mapping


def _token_overlap(a: str, b: str) -> float:
    """Token-based similarity between two strings."""
    tokens_a = set(re.findall(r"\w+", a))
    tokens_b = set(re.findall(r"\w+", b))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / max(len(tokens_a), len(tokens_b))
