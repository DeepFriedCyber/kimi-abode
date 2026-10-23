"""Property lookup shared by the REST API, area Q&A and chat."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def resolve_property(
    pool, property_id: int
) -> tuple[dict[str, Any] | None, bool]:
    """Return (record, is_live_listing) from the demo store or Postgres."""
    if pool is None:
        from .ingestion.agent_store import listing_store
        from .router import load_fixture

        record = next((row for row in load_fixture() if row.get("id") == property_id), None)
        if record is None:
            record = listing_store.get_by_id(property_id)
        return record, bool(record and record.get("asking_price") is not None)

    from .repository import fetch_listing_by_id, fetch_property_by_id

    row = None
    is_listing = False
    try:
        row = await fetch_listing_by_id(pool, property_id)
        is_listing = row is not None
    except Exception as exc:  # noqa: BLE001 - table may not exist yet
        logger.warning("[Property] live listing lookup unavailable: %s", exc)

    if row is None:
        try:
            row = await fetch_property_by_id(pool, property_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("[Property] lookup failed for %s: %s", property_id, exc, exc_info=True)
            raise

    return (dict(row) if row is not None else None), is_listing
