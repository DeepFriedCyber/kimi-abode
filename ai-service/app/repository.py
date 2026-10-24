"""Repository layer — SQL operations for properties, sales and search.

All queries use positional, parameterised statements to prevent SQL injection.
The search builder computes parameter indexes explicitly; mixing literal values
into `$n` placeholders (a previous bug) is never done.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Columns returned to callers. `embedding` is deliberately excluded: it is 768
# floats per row and is never needed by the UI.
SEARCH_COLUMNS = (
    "id, address_line1, address_line2, town, postcode, outcode, property_type, "
    "num_beds, price_paid, date_sold, latitude, longitude, "
    "floor_area_sqm, plot_size_sqm, price_per_sqm, tenure, ward, district, source_url, "
    "(embedding IS NOT NULL)::int AS has_embedding"
)

MAX_LIMIT = 100

LISTING_COLUMNS = (
    "id, address_line1, address_line2, town, postcode, outcode, property_type, "
    "num_beds, num_bathrooms, asking_price, price_qualifier, price_period, "
    "listing_status, tenure, floor_area_sqm, plot_size_sqm, description, "
    "features, latitude, longitude, ward, district, source_url, listed_at, agent_id"
)


def _vector_literal(embedding: Any) -> str | None:
    """Serialise a list[float] to pgvector's text format."""
    if embedding is None:
        return None
    if isinstance(embedding, str):
        return embedding
    return "[" + ",".join(f"{float(value):.6f}" for value in embedding) + "]"


def _as_date(value: Any) -> date | None:
    """Coerce a DATE parameter.

    Importers hand us ISO strings; asyncpg requires a date object for a DATE
    column. Unparseable values become NULL rather than failing the whole row.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            logger.warning("dropping unparseable date_sold %r", value)
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:
    """Coerce a TIMESTAMPTZ parameter from ISO text or a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            logger.warning("dropping unparseable timestamp %r", value)
            return None
    return None



def _escape_like(value: str) -> str:
    """Escape ILIKE wildcards so user input cannot broaden the match."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ------------------------------------------------------------------ Upsert property
async def upsert_property(pool: asyncpg.Pool, prop: dict[str, Any]) -> int:
    """Insert or update a property and return its id.

    Requires a unique constraint on (address_line1, postcode).
    """
    sql = """
        INSERT INTO properties (address_line1, address_line2, town, postcode,
                                outcode, property_type, num_beds, price_paid,
                                date_sold, latitude, longitude,
                                floor_area_sqm, plot_size_sqm, price_per_sqm,
                                tenure, ward, district, source_url,
                                embedding, source)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                $12, $13, $14, $15, $16, $17, $18, $19::vector, $20)
        ON CONFLICT (address_line1, postcode)
        DO UPDATE SET price_paid = EXCLUDED.price_paid,
                      date_sold = EXCLUDED.date_sold,
                      num_beds = EXCLUDED.num_beds,
                      property_type = EXCLUDED.property_type,
                      latitude = EXCLUDED.latitude,
                      longitude = EXCLUDED.longitude,
                      floor_area_sqm = EXCLUDED.floor_area_sqm,
                      plot_size_sqm = EXCLUDED.plot_size_sqm,
                      price_per_sqm = EXCLUDED.price_per_sqm,
                      tenure = EXCLUDED.tenure,
                      ward = EXCLUDED.ward,
                      district = EXCLUDED.district,
                      source_url = EXCLUDED.source_url,
                      embedding = EXCLUDED.embedding,
                      source = EXCLUDED.source
        RETURNING id
    """
    async with pool.acquire() as conn:
        return await conn.fetchval(
            sql,
            prop["address_line1"], prop.get("address_line2"),
            prop.get("town"), prop.get("postcode"),
            prop.get("outcode"), prop.get("property_type"),
            prop.get("num_beds"), prop.get("price_paid"),
            _as_date(prop.get("date_sold")), prop.get("latitude"),
            prop.get("longitude"),
            prop.get("floor_area_sqm"), prop.get("plot_size_sqm"),
            prop.get("price_per_sqm"), prop.get("tenure"),
            prop.get("ward"), prop.get("district"),
            prop.get("source_url"), _vector_literal(prop.get("embedding")),
            prop.get("source", "land-registry"),
        )


async def upsert_sale(pool: asyncpg.Pool, sale: dict[str, Any]) -> int:
    """Insert a sold-price record. Returns the row id (0 when already present)."""
    sql = """
        INSERT INTO sales (property_address, property_town, postcode,
                           price_paid, date_sold, property_type)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT DO NOTHING
        RETURNING id
    """
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            sql,
            sale["property_address"], sale.get("property_town"),
            sale.get("postcode"), sale["price_paid"],
            _as_date(sale.get("date_sold")), sale.get("property_type"),
        )
    return int(row_id or 0)


async def upsert_listing(pool: asyncpg.Pool, listing: dict[str, Any]) -> int:
    """Insert or update an agent-uploaded listing.

    Deduplicates per agent on address + postcode (the generated `dedupe_key`
    column), so re-uploading a file updates rather than duplicates.
    """
    sql = """
        INSERT INTO listings (
            agent_id, agent_ref, address_line1, address_line2, town, postcode,
            outcode, property_type, num_beds, num_bathrooms, asking_price,
            price_qualifier, price_period, price_paid, date_sold, listing_status,
            tenure, floor_area_sqm, plot_size_sqm, description, features,
            latitude, longitude, ward, district, source, source_url, listed_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
            $15, $16, $17, $18, $19, $20, $21::jsonb, $22, $23, $24, $25,
            $26, $27, $28
        )
        ON CONFLICT (agent_id, dedupe_key) DO UPDATE SET
            agent_ref = EXCLUDED.agent_ref,
            address_line2 = EXCLUDED.address_line2,
            town = EXCLUDED.town,
            postcode = EXCLUDED.postcode,
            outcode = EXCLUDED.outcode,
            property_type = EXCLUDED.property_type,
            num_beds = EXCLUDED.num_beds,
            num_bathrooms = EXCLUDED.num_bathrooms,
            asking_price = EXCLUDED.asking_price,
            price_qualifier = EXCLUDED.price_qualifier,
            price_period = EXCLUDED.price_period,
            price_paid = EXCLUDED.price_paid,
            date_sold = EXCLUDED.date_sold,
            listing_status = EXCLUDED.listing_status,
            tenure = EXCLUDED.tenure,
            floor_area_sqm = EXCLUDED.floor_area_sqm,
            plot_size_sqm = EXCLUDED.plot_size_sqm,
            description = EXCLUDED.description,
            features = EXCLUDED.features,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            ward = EXCLUDED.ward,
            district = EXCLUDED.district,
            source = EXCLUDED.source,
            source_url = EXCLUDED.source_url,
            listed_at = EXCLUDED.listed_at,
            updated_at = NOW()
        RETURNING id
    """
    async with pool.acquire() as conn:
        return await conn.fetchval(
            sql,
            listing["agent_id"], listing.get("agent_ref"),
            listing["address_line1"], listing.get("address_line2"),
            listing.get("town"), listing.get("postcode"), listing.get("outcode"),
            listing.get("property_type"), listing.get("num_beds"),
            listing.get("num_bathrooms"), listing.get("asking_price"),
            listing.get("price_qualifier"), listing.get("price_period"),
            listing.get("price_paid"), _as_date(listing.get("date_sold")),
            listing.get("listing_status", "available"), listing.get("tenure"),
            listing.get("floor_area_sqm"), listing.get("plot_size_sqm"),
            listing.get("description"), json.dumps(listing.get("features") or []),
            listing.get("latitude"), listing.get("longitude"),
            listing.get("ward"), listing.get("district"),
            listing.get("source"), listing.get("source_url"),
            _as_datetime(listing.get("listed_at")),
        )


# ------------------------------------------------------------------ Search
def _build_where_clause(parsed: Any, district: str | None) -> tuple[str, list[Any]]:
    """Build a WHERE clause and its positional parameters.

    Each filter is added only when it has a value: an empty pattern would
    expand to `ILIKE '%'` and silently match every row.
    """
    clauses: list[str] = []
    params: list[Any] = []

    def push(value: Any) -> int:
        params.append(value)
        return len(params)

    min_beds = getattr(parsed, "min_beds", None)
    max_beds = getattr(parsed, "max_beds", None)
    min_price = getattr(parsed, "min_price", None)
    max_price = getattr(parsed, "max_price", None)

    if min_beds is not None:
        clauses.append(f"num_beds >= ${push(int(min_beds))}")
    if max_beds is not None:
        clauses.append(f"num_beds <= ${push(int(max_beds))}")
    if min_price is not None:
        clauses.append(f"price_paid >= ${push(float(min_price))}")
    if max_price is not None:
        clauses.append(f"price_paid <= ${push(float(max_price))}")

    location = getattr(parsed, "location", None)
    if location:
        clauses.append(f"town ILIKE ${push(f'%{_escape_like(location)}%')} ESCAPE '\\'")

    outcode = getattr(parsed, "outcode", None)
    if outcode:
        clauses.append(f"outcode ILIKE ${push(f'%{_escape_like(outcode)}%')} ESCAPE '\\'")

    if district:
        clauses.append(f"district ILIKE ${push(f'%{_escape_like(district)}%')} ESCAPE '\\'")

    property_types = getattr(parsed, "property_types", None) or []
    type_values = [
        t.value if hasattr(t, "value") else str(t) for t in property_types if t
    ]
    if type_values:
        clauses.append(f"property_type = ANY(${push(type_values)}::text[])")

    return (" AND ".join(clauses) if clauses else "TRUE"), params


async def execute_search_pg(
    pool: asyncpg.Pool,
    parsed: Any,
    message: str,
    embedding: list[float] | None,
    district: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[asyncpg.Record], int]:
    """Execute a hybrid (optional vector) search.

    Returns (rows for this page, total matching rows).
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))

    where_sql, filter_params = _build_where_clause(parsed, district)
    params: list[Any] = list(filter_params)

    # Hybrid ranking: vector similarity for meaning, ts_rank for the words the
    # user actually typed. The expression covers address, town and postcode so
    # "51 Cloverfields CW1 5AL" matches every token the user supplied.
    text_expression = (
        "to_tsvector('english', coalesce(address_line1, '') || ' ' || "
        "coalesce(town, '') || ' ' || coalesce(postcode, ''))"
    )
    rank_parts: list[str] = []

    if embedding:
        embedding_index = len(params) + 1
        params.append(_vector_literal(embedding))
        rank_parts.append(
            f"0.65 * (1 - coalesce(embedding <=> ${embedding_index}::vector, 1.0))"
        )

    query_text = (message or "").strip()
    if query_text:
        text_index = len(params) + 1
        params.append(query_text)
        # ts_rank for a three-term address match is ~0.27, an order of magnitude
        # below a cosine similarity. Scaling (and capping) makes the weights
        # mean what they say: a full text match scores 1.0.
        rank_parts.append(
            f"0.35 * least(4 * ts_rank({text_expression}, "
            f"plainto_tsquery('english', ${text_index})), 1.0)"
        )

    if rank_parts:
        order_by = "ORDER BY (" + " + ".join(rank_parts) + ") DESC, id ASC"
    else:
        order_by = "ORDER BY id"

    limit_index = len(params) + 1
    params.append(limit)
    offset_index = len(params) + 1
    params.append(offset)

    sql = (
        f"SELECT {SEARCH_COLUMNS} FROM properties WHERE {where_sql} "
        f"{order_by} LIMIT ${limit_index} OFFSET ${offset_index}"
    )
    count_sql = f"SELECT count(*) FROM properties WHERE {where_sql}"

    logger.debug("[Search] limit=%s offset=%s where=%s", limit, offset, where_sql)

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        total = await conn.fetchval(count_sql, *filter_params)

    logger.info(
        "[Search] %s rows (total=%s) for query=%r", len(rows), total, message[:50]
    )
    return rows, int(total or 0)


# ------------------------------------------------------------------ Counters
async def count_properties(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return int(await conn.fetchval("SELECT count(*) FROM properties") or 0)


async def count_sales(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return int(await conn.fetchval("SELECT count(*) FROM sales") or 0)


# ------------------------------------------------------------------ Fetch single property
async def fetch_property_by_id(pool: asyncpg.Pool, prop_id: int) -> asyncpg.Record | None:
    sql = (
        f"SELECT {SEARCH_COLUMNS} FROM properties WHERE id = $1"
    )
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, prop_id)


# ------------------------------------------------------------------ Pagination helpers
async def get_paginated_search(
    pool: asyncpg.Pool,
    parsed: Any,
    query: str,
    embedding: list[float] | None,
    district: str | None = None,
    limit: int = 20,
    page: int = 1,
) -> dict[str, Any]:
    """Execute search with 1-indexed pagination."""
    if page < 1:
        raise ValueError("Page must be at least 1")
    if limit < 1:
        raise ValueError("Limit must be at least 1")

    offset = (page - 1) * limit
    rows, total = await execute_search_pg(
        pool, parsed, query, embedding, district, limit=limit, offset=offset
    )

    return {
        "properties": [dict(row) for row in rows],
        "total_matches": total,
        "page": page,
        "per_page": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "has_next": offset + len(rows) < total,
        "has_prev": page > 1,
    }


# ------------------------------------------------------------------ Statistics
async def get_property_statistics(pool: asyncpg.Pool) -> dict[str, Any]:
    """Return a small set of database statistics for monitoring."""
    queries: list[tuple[str, str]] = [
        ("total_properties", "SELECT COUNT(*) FROM properties"),
        (
            "properties_with_embedding",
            "SELECT COUNT(*) FROM properties WHERE embedding IS NOT NULL",
        ),
        ("average_price", "SELECT AVG(price_paid)::NUMERIC(12,2) FROM properties"),
        (
            "median_price",
            "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_paid)::NUMERIC(12,2) "
            "FROM properties",
        ),
        (
            "most_common_type",
            "SELECT property_type FROM properties GROUP BY property_type "
            "ORDER BY COUNT(*) DESC LIMIT 1",
        ),
    ]

    stats: dict[str, Any] = {}
    async with pool.acquire() as conn:
        for name, sql in queries:
            stats[name] = await conn.fetchval(sql)
    return stats


# ------------------------------------------------------------------ Bulk operations
async def upsert_properties_batch(
    pool: asyncpg.Pool, properties: list[dict[str, Any]]
) -> dict[str, int]:
    """Upsert properties sequentially; failures are logged and skipped."""
    results: dict[str, int] = {}

    for prop in properties:
        try:
            row_id = await upsert_property(pool, prop)
            results[prop.get("address_line1", f"unknown-{row_id}")] = row_id
        except Exception as exc:  # noqa: BLE001 - batch should not abort
            logger.error("[BulkUpsert] Failed for %s: %s", prop.get("address_line1"), exc)

    return results


async def search_by_postcode(
    pool: asyncpg.Pool,
    postcode: str,
    limit: int = 50,
) -> tuple[list[asyncpg.Record], int]:
    """Return properties whose postcode matches the given prefix/area."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    sql = (
        f"SELECT {SEARCH_COLUMNS} FROM properties "
        "WHERE postcode ILIKE $1 ESCAPE '\\' "
        "ORDER BY price_paid ASC NULLS LAST LIMIT $2"
    )
    pattern = f"%{_escape_like(postcode)}%"

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, pattern, limit)
        total = await conn.fetchval(
            "SELECT count(*) FROM properties WHERE postcode ILIKE $1 ESCAPE '\\'",
            pattern,
        )
    return rows, int(total or 0)


# ------------------------------------------------------------------ Live listings
def _build_listing_where(parsed: Any, query_text: str) -> tuple[str, list[Any]]:
    """Filters for agent-uploaded listings (asking price, not sold price)."""
    clauses: list[str] = ["listing_status IN ('available', 'under_offer')"]
    params: list[Any] = []

    def push(value: Any) -> int:
        params.append(value)
        return len(params)

    if parsed.min_beds is not None:
        clauses.append(f"num_beds >= ${push(int(parsed.min_beds))}")
    if parsed.max_beds is not None:
        clauses.append(f"num_beds <= ${push(int(parsed.max_beds))}")
    if parsed.max_price is not None:
        clauses.append(f"asking_price <= ${push(float(parsed.max_price))}")
    if getattr(parsed, "min_price", None) is not None:
        clauses.append(f"asking_price >= ${push(float(parsed.min_price))}")

    if parsed.location:
        clauses.append(f"town ILIKE ${push(f'%{_escape_like(parsed.location)}%')} ESCAPE '\\'")
    if parsed.outcode:
        clauses.append(f"outcode ILIKE ${push(f'%{_escape_like(parsed.outcode)}%')} ESCAPE '\\'")
    if getattr(parsed, "district", None):
        clauses.append(
            f"district ILIKE ${push(f'%{_escape_like(parsed.district)}%')} ESCAPE '\\'"
        )

    types = [
        item.value if hasattr(item, "value") else str(item)
        for item in (parsed.property_types or [])
        if item
    ]
    if types:
        clauses.append(f"property_type = ANY(${push(types)}::text[])")

    has_structured = any(
        (
            parsed.min_beds is not None,
            parsed.max_beds is not None,
            parsed.max_price is not None,
            parsed.location,
            parsed.outcode,
            parsed.property_types,
        )
    )
    if query_text and not has_structured:
        index = push(f"%{_escape_like(query_text)}%")
        clauses.append(
            f"(address_line1 ILIKE ${index} ESCAPE '\\' "
            f"OR town ILIKE ${index} ESCAPE '\\' "
            f"OR description ILIKE ${index} ESCAPE '\\')"
        )

    return " AND ".join(clauses), params


async def search_live_listings(
    pool: asyncpg.Pool,
    parsed: Any,
    query_text: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[asyncpg.Record], int]:
    """Search agent-uploaded listings (live inventory)."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))

    where_sql, filter_params = _build_listing_where(parsed, query_text)
    params = list(filter_params)

    limit_index = len(params) + 1
    params.append(limit)
    offset_index = len(params) + 1
    params.append(offset)

    sql = (
        f"SELECT {LISTING_COLUMNS} FROM listings WHERE {where_sql} "
        "ORDER BY CASE listing_status WHEN 'available' THEN 0 ELSE 1 END, "
        f"listed_at DESC NULLS LAST, id DESC LIMIT ${limit_index} OFFSET ${offset_index}"
    )
    count_sql = f"SELECT count(*) FROM listings WHERE {where_sql}"

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        total = await conn.fetchval(count_sql, *filter_params)

    return rows, int(total or 0)


async def fetch_listing_by_id(pool: asyncpg.Pool, listing_id: int) -> asyncpg.Record | None:
    sql = f"SELECT {LISTING_COLUMNS} FROM listings WHERE id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, listing_id)


# ------------------------------------------------------------------ Listing photos
PHOTO_COLUMNS = "id, hash, path, thumb_path, width, height, bytes, position, is_cover"


def photo_record_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    photo_hash = row["hash"]
    return {
        "id": photo_hash[:16],
        "hash": photo_hash,
        "url": f"/media/{row['path']}",
        "thumb_url": f"/media/{row['thumb_path']}",
        "width": row["width"],
        "height": row["height"],
        "bytes": row["bytes"],
        "position": row["position"],
        "is_cover": row["is_cover"],
    }


async def fetch_listing_owner(pool: asyncpg.Pool, listing_id: int) -> str | None:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT agent_id FROM listings WHERE id = $1", listing_id)


async def list_agent_listings(
    pool: asyncpg.Pool,
    *,
    limit: int = 50,
    offset: int = 0,
    agent_id: str | None = None,
) -> tuple[list[asyncpg.Record], int]:
    """One page of agent listings for the management UI (newest first)."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    where_sql = "WHERE agent_id = $1" if agent_id else ""
    count_params: list[Any] = [agent_id] if agent_id else []

    params: list[Any] = list(count_params)
    limit_index = len(params) + 1
    params.append(limit)
    offset_index = len(params) + 1
    params.append(offset)

    sql = (
        f"SELECT {LISTING_COLUMNS} FROM listings {where_sql} "
        f"ORDER BY listed_at DESC NULLS LAST, id DESC "
        f"LIMIT ${limit_index} OFFSET ${offset_index}"
    )
    count_sql = f"SELECT count(*) FROM listings {where_sql}"

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        total = await conn.fetchval(count_sql, *count_params)

    return list(rows), int(total or 0)


async def list_listing_photos(pool: asyncpg.Pool, listing_id: int) -> list[dict[str, Any]]:
    sql = (
        f"SELECT {PHOTO_COLUMNS} FROM listing_photos "
        "WHERE listing_id = $1 ORDER BY position, id"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, listing_id)
    return [photo_record_to_dict(row) for row in rows]


async def list_photos_for_listings(
    pool: asyncpg.Pool, listing_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    if not listing_ids:
        return {}

    sql = (
        f"SELECT listing_id, {PHOTO_COLUMNS} FROM listing_photos "
        "WHERE listing_id = ANY($1::int[]) ORDER BY listing_id, position, id"
    )
    grouped: dict[int, list[dict[str, Any]]] = {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, listing_ids)

    for row in rows:
        grouped.setdefault(row["listing_id"], []).append(photo_record_to_dict(row))
    return grouped


async def insert_listing_photo(
    pool: asyncpg.Pool, listing_id: int, photo: dict[str, Any]
) -> None:
    sql = """
        INSERT INTO listing_photos
            (listing_id, hash, path, thumb_path, width, height, bytes, position, is_cover)
        VALUES (
            $1, $2, $3, $4, $5, $6, $7,
            COALESCE((SELECT max(position) + 1 FROM listing_photos WHERE listing_id = $1), 0),
            FALSE
        )
        ON CONFLICT (listing_id, hash) DO NOTHING
    """
    async with pool.acquire() as conn:
        await conn.execute(
            sql,
            listing_id,
            photo["hash"],
            photo["display_path"],
            photo["thumb_path"],
            photo["width"],
            photo["height"],
            photo["bytes"],
        )


async def delete_listing_photo(
    pool: asyncpg.Pool, listing_id: int, photo_id: str
) -> dict[str, Any] | None:
    sql = (
        "DELETE FROM listing_photos "
        "WHERE listing_id = $1 AND left(hash, 16) = $2 "
        "RETURNING path, thumb_path, is_cover"
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(sql, listing_id, photo_id)
            if row is None:
                return None

            remaining = await conn.fetchval(
                "SELECT count(*) FROM listing_photos WHERE listing_id = $1", listing_id
            )
            if remaining and row["is_cover"]:
                await conn.execute(
                    "UPDATE listing_photos SET is_cover = TRUE WHERE id = ("
                    "  SELECT id FROM listing_photos WHERE listing_id = $1 "
                    "  ORDER BY position, id LIMIT 1)",
                    listing_id,
                )

    return {
        "display_path": row["path"],
        "thumb_path": row["thumb_path"],
        "is_cover": row["is_cover"],
    }


async def set_cover_photo(
    pool: asyncpg.Pool, listing_id: int, photo_id: str
) -> bool:
    async with pool.acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval(
                "SELECT 1 FROM listing_photos "
                "WHERE listing_id = $1 AND left(hash, 16) = $2",
                listing_id,
                photo_id,
            )
            if not exists:
                return False

            await conn.execute(
                "UPDATE listing_photos SET is_cover = FALSE WHERE listing_id = $1",
                listing_id,
            )
            await conn.execute(
                "UPDATE listing_photos SET is_cover = TRUE "
                "WHERE listing_id = $1 AND left(hash, 16) = $2",
                listing_id,
                photo_id,
            )
    return True
