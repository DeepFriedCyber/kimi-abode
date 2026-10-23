"""Provider routing — strategy selection for query execution.

Providers are tried in order. The deterministic/demo provider exists so the
product can be explored without a database; it reads a fixture file rather than
embedding 500 records in Python source, and is disabled when DEMO_DATA is off.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_listings.json"

# Fixture property types are abbreviated ("semi_d", "terrace", ...).
_TYPE_ALIASES = {
    "semi_d": "semi-detached",
    "semi": "semi-detached",
    "semi-detached": "semi-detached",
    "terrace": "terraced",
    "terraced": "terraced",
    "detached": "detached",
    "flat": "flat",
    "bungalow": "bungalow",
    "maisonette": "maisonette",
}


def normalise_type(raw: str | None) -> str:
    """Map fixture/agent property-type spellings onto canonical values."""
    if not raw:
        return "unknown"
    lowered = raw.strip().lower().replace("-", "_")
    if lowered in _TYPE_ALIASES:
        return _TYPE_ALIASES[lowered]
    # Compound values such as "detached_bungalow" / "semi_d_bungalow".
    for token, canonical in _TYPE_ALIASES.items():
        if token in lowered:
            return canonical
    return lowered.replace("_", "-")


SEARCH_STOPWORDS = {
    "the", "and", "with", "for", "from", "house", "home", "property",
    "properties", "bed", "beds", "bedroom", "bedrooms", "a", "an", "of",
    "to", "in", "near", "under", "over", "best", "nice", "good", "great",
    "area", "areas",
}


def _search_blob(property_row: dict[str, Any]) -> str:
    """Lower-cased text used for demo keyword matching (address + description)."""
    features = property_row.get("features") or []
    if isinstance(features, list):
        features = " ".join(str(feature) for feature in features)

    return " ".join(
        str(part)
        for part in (
            property_row.get("address_line1"),
            property_row.get("address_line2"),
            property_row.get("town"),
            property_row.get("ward"),
            property_row.get("postcode"),
            property_row.get("property_type"),
            property_row.get("description"),
            features,
        )
        if part
    ).lower()


@dataclass
class ProviderResult:
    """Container for a single provider's output."""

    tier: str
    results: list = field(default_factory=list)
    message: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result: dict = {"tier": self.tier, **self.extra}
        if self.results:
            result["results"] = self.results
        if self.message:
            result["message"] = self.message
        return result


class SearchProvider:
    """Provider that delegates to the pgvector-backed search function."""

    name = "pgvector-search"

    def __init__(self, pool, embedder=None):
        self.pool = pool
        self.embedder = embedder

    async def execute(self, query: str) -> dict[str, Any] | None:
        """Execute a search, or return None when no pool is configured."""
        if not self.pool:
            return None

        try:
            from .search import search

            return await search(query, pool=self.pool, embedder=self.embedder)
        except Exception as exc:  # noqa: BLE001 - fall through to next provider
            logger.warning("[SearchProvider] pgvector search failed: %s", exc)
            return None


@lru_cache(maxsize=1)
def load_fixture() -> list[dict[str, Any]]:
    """Load the demo property fixture once per process."""
    if not FIXTURE_PATH.exists():
        logger.warning("[Demo] fixture not found at %s", FIXTURE_PATH)
        return []

    try:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("[Demo] failed to load fixture: %s", exc)
        return []

    # Support both the wrapped format written by scripts/import_listings.py and
    # a bare list for backwards compatibility.
    records = payload.get("records", []) if isinstance(payload, dict) else payload

    for record in records:
        record["property_type"] = normalise_type(record.get("property_type"))
    return records


class DeterministicSearchProvider:
    """Filter-only provider backed by a fixture. Never used in production."""

    name = "deterministic-search"

    def __init__(self) -> None:
        self.properties = load_fixture()

    async def execute(self, query: str, parsed=None) -> dict[str, Any] | None:
        from .ingestion.agent_store import listing_store
        from .parser import _deterministic_parse

        # Fixture data plus anything agents have uploaded.
        properties = list(self.properties) + listing_store.all_listings()
        if not properties:
            return None

        # Callers may pass filters parsed from explicit query parameters; they
        # take precedence over re-parsing the free-text query.
        parsed = parsed or _deterministic_parse(query)
        matches = properties

        def price_of(property_row: dict) -> float:
            # Live listings carry an asking price; sold records carry price_paid.
            return float(
                property_row.get("asking_price")
                or property_row.get("price_paid")
                or 0
            )

        if parsed.min_beds is not None:
            matches = [p for p in matches if (p.get("num_beds") or 0) >= parsed.min_beds]
        if parsed.max_beds is not None:
            matches = [p for p in matches if (p.get("num_beds") or 0) <= parsed.max_beds]
        if parsed.max_price is not None:
            matches = [p for p in matches if price_of(p) <= parsed.max_price]
        if parsed.location:
            location = parsed.location.lower()
            matches = [p for p in matches if location in (p.get("town") or "").lower()]
        if parsed.outcode:
            outcode = parsed.outcode.upper()
            matches = [p for p in matches if (p.get("outcode") or "").upper() == outcode]
        if parsed.property_types:
            wanted = {t.value for t in parsed.property_types}
            matches = [p for p in matches if p.get("property_type") in wanted]

        # When the query carried no structured filters, fall back to a simple
        # token match over address/town/description. This is what makes a
        # freshly uploaded listing findable by name in demo mode.
        if not any(
            (
                parsed.min_beds is not None,
                parsed.max_beds is not None,
                parsed.max_price is not None,
                parsed.location,
                parsed.outcode,
                parsed.property_types,
            )
        ):
            tokens = [
                token
                for token in re.findall(r"[a-z0-9]{3,}", query.lower())
                if token not in SEARCH_STOPWORDS
            ]
            if tokens:
                matches = [
                    p for p in matches
                    if all(token in _search_blob(p) for token in tokens)
                ]

        return {
            "tier": self.name,
            "properties": matches[:50],
            "total_matches": len(matches),
            "message": f"Found {len(matches)} demo properties (fixture data)",
        }


class QueryRouter:
    """Try providers in order, caching successful results."""

    def __init__(self, cache=None) -> None:
        self.providers: list = []
        self.cache = cache

    def add_provider(self, provider) -> None:
        self.providers.append(provider)

    async def route(self, query: str) -> dict:
        if self.cache:
            cached = await self.cache.get(query)
            if cached:
                return {**cached, "tier": "semantic-cache"}

        for provider in self.providers:
            try:
                result = await provider.execute(query)
            except Exception as exc:  # noqa: BLE001 - keep the chain alive
                logger.warning("[QueryRouter] provider %r failed: %s", provider, exc)
                continue

            if not result:
                continue

            # A provider that returns zero rows is a valid answer when it has a
            # database; only treat "no payload" as a miss.
            if self.cache:
                await self.cache.put(query, result)
            return {**result, "tier": getattr(provider, "name", "unknown")}

        return {
            "tier": "no-provider",
            "results": [],
            "properties": [],
            "total_matches": 0,
            "message": "No search providers available. Configure DATABASE_URL.",
        }


def demo_data_enabled() -> bool:
    """Demo fixture data is opt-in and never enabled in production."""
    if os.getenv("NODE_ENV") == "production":
        return False
    return os.getenv("DEMO_DATA", "true").strip().lower() in {"1", "true", "yes"}


def build_providers(pool=None, embedder=None) -> list:
    """Build the provider chain for this process."""
    providers: list = []

    if pool is not None:
        providers.append(SearchProvider(pool=pool, embedder=embedder))

    if demo_data_enabled():
        providers.append(DeterministicSearchProvider())

    return providers
