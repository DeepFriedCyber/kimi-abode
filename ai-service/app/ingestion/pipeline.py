"""Pipeline — orchestrates ingestion from CSV → transform → validate → dedup → persist."""

from __future__ import annotations

from typing import Any

from .formats import parse_blm_csv, parse_csv
from .transform import transform_listing
from .validate import ValidationReport, validate_listing
from .dedup import deduplicate_listings


class IngestionPipeline:
    """End-to-end ingestion pipeline.

    Phases:
    1. Parse (format-specific)
    2. Transform (standardise)
    3. Validate (quality check)
    4. Deduplicate
    5. Persist (via repository — caller-provided)
    """

    def __init__(self):
        self.validation_report = ValidationReport()

    def run(self, raw: str, source: str = "csv", column_map: dict | None = None) -> list[dict[str, Any]]:
        """Execute the full pipeline on a raw CSV string. Returns deduplicated listings."""

        # Phase 1: Parse
        if source == "blm":
            parsed = parse_blm_csv(raw)
        else:
            parsed = parse_csv(raw, column_map)

        listings = [p.model_dump() for p in parsed]
        self.validation_report.total += len(listings)

        # Phase 2: Transform
        transformed = []
        for item in listings:
            try:
                t = transform_listing(item)
                t["source"] = item.get("source", source)
                transformed.append(t)
            except (ValueError, TypeError) as e:
                self.validation_report.record(False, item, [f"transform-error: {e}"])

        # Phase 3: Validate
        valid_listings = []
        for item in transformed:
            ok, errors = validate_listing(item)
            if ok:
                valid_listings.append(item)
            else:
                self.validation_report.record(False, item, errors)

        # Phase 4: Deduplicate
        deduped = deduplicate_listings(valid_listings)

        return deduped

    def get_report(self) -> dict[str, Any]:
        return self.validation_report.summary()


async def persist_listings(
    listings: list[dict[str, Any]],
    upsert_fn,
    batch_size: int = 100,
) -> int:
    """Persist listings in batches. Caller provides the async upsert function."""
    count = 0
    for i in range(0, len(listings), batch_size):
        batch = listings[i : i + batch_size]
        for listing in batch:
            await upsert_fn(listing)
            count += 1
    return count
