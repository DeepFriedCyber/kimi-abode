"""Repository layer — SQL operations for properties, sales and search."""

from __future__ import annotations

from typing import Any

import asyncpg


# ------------------------------------------------------------------ Upsert property
async def upsert_property(pool: asyncpg.Pool, prop: dict[str, Any]) -> int:
    """Upsert a property record. Returns the row id."""
    sql = """
        INSERT INTO properties (address_line1, address_line2, town, postcode,
                                outcode, property_type, num_beds, price_paid,
                                date_sold, latitude, longitude, embedding, source)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (address_line1, postcode)
        DO UPDATE SET price_paid = EXCLUDED.price_paid,
                      date_sold = EXCLUDED.date_sold,
                      embedding = EXCLUDED.embedding
        RETURNING id
    """
    async with pool.acquire() as conn:
        return await conn.fetchval(
            sql,
            prop["address_line1"], prop.get("address_line2"),
            prop.get("town"), prop.get("postcode"),
            prop.get("outcode"), prop.get("property_type"),
            prop.get("num_beds"), prop.get("price_paid"),
            prop.get("date_sold"), prop.get("latitude"),
            prop.get("longitude"),
            str(prop["embedding"]) if prop.get("embedding") else None,
            prop.get("source", "land-registry"),
        )


async def upsert_sale(pool: asyncpg.Pool, sale: dict[str, Any]) -> int:
    """Upsert a sold-price record. Returns the row id (0 if not inserted)."""
    sql = """
        INSERT INTO sales (property_address, property_town, postcode,
                           price_paid, date_sold, property_type)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT DO NOTHING
    """
    async with pool.acquire() as conn:
        result = await conn.execute(sql,
            sale["property_address"], sale.get("property_town"),
            sale.get("postcode"), sale["price_paid"],
            sale.get("date_sold"), sale.get("property_type"))
        # parse the command tag (e.g. "INSERT 0" means no row inserted)
        return int(result.split()[-1]) if result.split()[-1] != "0" else 0


# ------------------------------------------------------------------ Search

def _build_where_clause(parsed: Any, district: str | None) -> tuple[str, list[Any]]:
    """Build WHERE clause and params from a ParsedQuery + optional district.

    Returns (where_sql, param_list). Parameters are $1-based in param_list.
    """
    clauses = []
    params: list[Any] = []
    idx = 0

    def push(val: Any) -> int:
        nonlocal idx
        idx += 1
        params.append(val)
        return idx

    if parsed.min_beds is not None:
        clauses.append(f"num_beds >= ${push(parsed.min_beds)}")

    if parsed.max_price is not None:
        clauses.append(f"price_paid <= ${push(parsed.max_price)}")

    if parsed.location or parsed.outcode:
        loc = parsed.location or ""
        oc = parsed.outcode or ""
        clauses.append(
            f"(town ILIKE ${push(f'%{loc}%')} OR outcode ILIKE ${push(f'%{oc}%')})"
        )

    if district:
        clauses.append(f"district ILIKE ${push(f'%{district}%')}")

    return " AND ".join(clauses) if clauses else "TRUE", params


async def execute_search_pg(
    pool: asyncpg.Pool,
    parsed: Any,
    message: str,
    embedding: list[float] | None,
    district: str | None = None,
    limit: int = 50,
) -> tuple[list[asyncpg.Record], int]:
    """Execute hybrid search using pgvector cosine similarity.

    Parameters are safely positional ($1, $2, ...) computed before SQL construction.
    """
    where_sql, params = _build_where_clause(parsed, district)

    # Reserve parameter index: LIMIT gets the next numbered placeholder
    limit_param_idx = len(params) + 1
    params.append(limit)

    base_sql = (
        f"SELECT *, (embedding IS NOT NULL)::int as has_embedding "
        f"FROM properties WHERE {where_sql} LIMIT ${limit_param_idx}"
    )

    if embedding:
        vec_str = f"[{','.join(f'{v:.6f}' for v in embedding)}]"
        # The LIMIT param index won't change since we already fixed it above
        sql = (
            f"SELECT *, (embedding IS NOT NULL)::int as has_embedding "
            f"FROM properties WHERE {where_sql} "
            f"ORDER BY embedding <=> '{vec_str}'::vector "
            f"LIMIT ${limit_param_idx}"
        )
    else:
        sql = base_sql

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        total = len(rows)
    return rows, total


# ------------------------------------------------------------------ Counters
async def count_properties(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM properties")


async def count_sales(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM sales")
