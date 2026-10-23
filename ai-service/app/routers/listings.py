"""Listing upload API — multi-format, dry-run first, partial import allowed.

Auth: `X-API-Key` (AGENT_API_KEY). Identity: `X-Agent-Id` header. In
development, a missing key is allowed with a warning; production fails closed.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from ..ingestion.agent_store import listing_store
from ..ingestion.housemetric import derive_town, enrich_postcodes
from ..ingestion.universal import (
    MAX_ROWS,
    build_template_csv,
    build_template_xlsx,
    column_catalogue,
    import_bytes,
    normalise_row,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
MAX_TEXT_CHARS = 20_000
MAX_GEOCODE_POSTCODES = 2_000
AGENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


# ------------------------------------------------------------------ auth
def _expected_key() -> str:
    return os.getenv("AGENT_API_KEY", "").strip()


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "")).strip().lower() == "production"


def _require_key(request: Request) -> None:
    expected = _expected_key()
    if not expected:
        if _is_production():
            raise HTTPException(status_code=503, detail="Listing uploads are not configured")
        logger.warning("Listing upload auth is DISABLED (set AGENT_API_KEY). Local only.")
        return

    provided = request.headers.get("x-api-key", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Authentication required")


def _agent_id(request: Request) -> str:
    raw = request.headers.get("x-agent-id", "anonymous").strip()
    return raw if AGENT_ID_RE.match(raw) else "anonymous"


# ------------------------------------------------------------------ rate limit
RATE_MAX = 100 if os.getenv("PYTEST_CURRENT_TEST") else 20
RATE_WINDOW = 3_600


class _Limiter:
    def __init__(self, limit: int, window: int) -> None:
        self.limit = limit
        self.window = window
        self._buckets: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        bucket = [stamp for stamp in self._buckets.get(key, []) if stamp > now - self.window]
        if len(bucket) >= self.limit:
            self._buckets[key] = bucket
            return False
        bucket.append(now)
        self._buckets[key] = bucket
        return True


_limiter = _Limiter(RATE_MAX, RATE_WINDOW)


def _check_rate(agent_id: str) -> None:
    if not _limiter.allow(agent_id):
        raise HTTPException(status_code=429, detail="Too many imports; try again later")


# ------------------------------------------------------------------ persistence
def _geocode_records(records: list[dict[str, Any]]) -> int:
    """Fill coordinates from postcodes.io; best-effort and never fatal."""
    pending = {
        record["postcode"]
        for record in records
        if record.get("postcode") and record.get("latitude") is None
    }
    if not pending:
        return 0

    if len(pending) > MAX_GEOCODE_POSTCODES:
        logger.warning(
            "[Listings] %s unique postcodes exceeds the geocoding cap (%s); "
            "the remainder keep no coordinates",
            len(pending),
            MAX_GEOCODE_POSTCODES,
        )
        pending = set(sorted(pending)[:MAX_GEOCODE_POSTCODES])

    try:
        resolved = enrich_postcodes(pending)
    except Exception as exc:  # noqa: BLE001 - enrichment is optional
        logger.warning("[Listings] geocoding failed: %s", exc)
        return 0

    geocoded = 0
    for record in records:
        if record.get("latitude") is not None:
            continue
        geo = resolved.get((record.get("postcode") or "").upper())
        if geo:
            record["latitude"] = geo.get("latitude")
            record["longitude"] = geo.get("longitude")
            record["ward"] = geo.get("admin_ward")
            record["district"] = geo.get("admin_district")
            record["town"] = record.get("town") or derive_town(
                geo.get("admin_ward"), geo.get("parish"), geo.get("admin_district")
            )
            record["geo_precision"] = "postcode"
            geocoded += 1
    return geocoded


async def _persist(records: list[dict[str, Any]], agent_id: str, request: Request) -> list[int]:
    pool = getattr(request.app.state, "pool", None)

    if pool is None:
        result = listing_store.upsert_many(records, agent_id)
        return list(result.get("ids", []))

    from ..repository import upsert_listing

    ids: list[int] = []
    for record in records:
        try:
            ids.append(await upsert_listing(pool, {**record, "agent_id": agent_id}))
        except Exception as exc:  # noqa: BLE001 - report per row, keep going
            logger.error("[Listings] persist failed for %s: %s", record.get("address_line1"), exc)
    return ids


# ------------------------------------------------------------------ endpoints
@router.post("/import")
async def import_listings(
    request: Request,
    file: Annotated[UploadFile, File(description="CSV, TSV, XLSX, JSON, JSONL, XML or TXT")],
    dry_run: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form(description="JSON object: canonical -> column")] = None,
    source: Annotated[str | None, Form()] = None,
):
    """Upload listings. Use `dry_run=true` to preview without writing anything."""
    _require_key(request)
    agent_id = _agent_id(request)
    _check_rate(agent_id)

    filename = file.filename or "upload.csv"
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES // 1_048_576} MB")

    mapping_override = None
    if mapping:
        try:
            parsed = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="mapping must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="mapping must be an object")
        mapping_override = parsed

    try:
        records, report = import_bytes(
            content,
            filename,
            mapping_override=mapping_override,
            source=source or "upload",
            max_rows=MAX_ROWS,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    report.dry_run = dry_run
    if not dry_run and records:
        report.geocoded = _geocode_records(records)
        ids = await _persist(records, agent_id, request)
        report.imported = len(ids)
        report.imported_ids = ids
    elif dry_run:
        report.geocoded = 0

    payload = report.as_dict()
    payload["agent_id"] = agent_id
    payload["filename"] = filename
    return payload


@router.post("/import/text")
async def import_pasted_text(request: Request, payload: dict):
    """Create a draft from a pasted email/description."""
    _require_key(request)
    agent_id = _agent_id(request)
    _check_rate(agent_id)

    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=413, detail=f"text exceeds {MAX_TEXT_CHARS} characters")

    dry_run = bool(payload.get("dry_run", True))
    try:
        records, report = import_bytes(
            text.encode("utf-8"), "pasted.txt", source="paste"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    report.dry_run = dry_run
    if not dry_run and records:
        report.geocoded = _geocode_records(records)
        ids = await _persist(records, agent_id, request)
        report.imported = len(ids)
        report.imported_ids = ids

    result = report.as_dict()
    result["agent_id"] = agent_id
    return result


@router.post("/")
async def create_listing(request: Request, payload: dict):
    """Create a single listing from canonical JSON (CRM integrations)."""
    _require_key(request)
    agent_id = _agent_id(request)
    _check_rate(agent_id)

    record, errors, warnings = normalise_row(payload, {}, row_number=1, source="api")
    if record is None:
        raise HTTPException(
            status_code=422,
            detail={"errors": [issue.as_dict() for issue in errors]},
        )

    geocoded = _geocode_records([record])
    ids = await _persist([record], agent_id, request)
    listing = {**record, "id": ids[0]} if ids else record

    return {
        "listing": listing,
        "imported": len(ids),
        "geocoded": geocoded,
        "warnings": [issue.as_dict() for issue in warnings],
        "agent_id": agent_id,
    }


@router.get("/")
async def list_listings(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    agent_id: Annotated[str | None, Query(max_length=64)] = None,
):
    """List uploaded listings.

    When an API key is configured, callers are restricted to their own listings
    (identified by `X-Agent-Id`); without a key this is a local demo store.
    """
    if _expected_key():
        _require_key(request)
        caller = request.headers.get("x-agent-id", "").strip()
        if not caller or not AGENT_ID_RE.match(caller):
            raise HTTPException(status_code=400, detail="x-agent-id header is required")
        if agent_id and agent_id != caller:
            raise HTTPException(status_code=403, detail="Cannot list another agent's listings")
        agent_id = caller

    return listing_store.list(limit=limit, offset=offset, agent_id=agent_id)


@router.get("/import/columns")
async def import_columns():
    """Accepted canonical columns and their synonyms (for a mapping UI)."""
    return column_catalogue()


@router.get("/import/template")
async def import_template(format: str = Query("csv", pattern="^(csv|xlsx)$")):
    """Downloadable import template with one example row."""
    if format == "xlsx":
        return Response(
            content=build_template_xlsx(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="abode-listings-template.xlsx"'},
        )

    return Response(
        content=build_template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="abode-listings-template.csv"'},
    )
