"""Repository layer — SQL operations for properties, sales and search.

This module provides type-safe database operations using asyncpg with PostgreSQL.
All queries use parameterized statements to prevent SQL injection.
"""

from __future__ import annotations

import logging
from typing import Any, List, Tuple

import asyncpg

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ Upsert property
async def upsert_property(pool: asyncpg.Pool, prop: dict[str, Any]) -> int:
    """Upsert a property record. Returns the row id.
    
    Uses INSERT ... ON CONFLICT for upsert pattern with unique constraint on (address_line1, postcode).
    
    Args:
        pool: Database connection pool
        prop: Property data dictionary
        
    Returns:
        The primary key of the inserted/updated property
    """
    sql = """
        INSERT INTO properties (address_line1, address_line2, town, postcode,
                                outcode, property_type, num_beds, price_paid,
                                date_sold, latitude, longitude, embedding, source)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (address_line1, postcode)
        DO UPDATE SET price_paid = EXCLUDED.price_paid,
                      date_sold = EXCLUDED.date_sold,
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
            prop.get("date_sold"), prop.get("latitude"),
            prop.get("longitude"),
            str(prop["embedding"]) if prop.get("embedding") else None,
            prop.get("source", "land-registry"),
        )


async def upsert_sale(pool: asyncpg.Pool, sale: dict[str, Any]) -> int:
    """Upsert a sold-price record. Returns the row id (0 if not inserted).
    
    Uses INSERT ... ON CONFLICT DO NOTHING to avoid duplicate entries.
    
    Args:
        pool: Database connection pool
        sale: Sale data dictionary
        
    Returns:
        Row ID if inserted, 0 otherwise
    """
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
        # Parse command tag (e.g. "INSERT 0 1" means 1 row affected)
        parts = result.split()
        return int(parts[-1]) if parts[-1] != "0" else 0


# ------------------------------------------------------------------ Search

def _build_where_clause(parsed: Any, district: str | None) -> tuple[str, list[Any]]:
    """Build WHERE clause and params from a ParsedQuery + optional district.
    
    This function constructs SQL filter conditions using parameterized queries
    to prevent SQL injection. Location/outcode filters use wildcard matching
    with explicit null checks.
    
    Args:
        parsed: Parsed query object with filter values
        district: Optional district name for additional filtering
        
    Returns:
        Tuple of (where_sql, param_list). Parameters are $1-based in param_list.
    """
    clauses = []
    params: list[Any] = []
    idx = 0

    def push(val: Any) -> int:
        """Add parameter to list and return its index."""
        nonlocal idx
        idx += 1
        params.append(val)
        return idx

    # Beds filter
    if parsed.min_beds is not None:
        clauses.append(f"num_beds >= ${push(parsed.min_beds)}")

    # Price filter
    if parsed.max_price is not None:
        clauses.append(f"price_paid <= ${push(parsed.max_price)}")

    # Location/outcode filter (combined) - with explicit null check
    if parsed.location or parsed.outcode:
        loc = parsed.location or ""
        oc = parsed.outcode or ""
        # Use LIKE patterns but ensure wildcards are added to non-empty strings
        town_pattern = f"%{loc}%" if loc else ""
        outcode_pattern = f"%{oc}%" if oc else ""
        clauses.append(
            f"(town ILIKE ${push(town_pattern)} OR outcode ILIKE ${push(outcode_pattern)})"
        )

    # District filter (if provided) - with null check
    if district:
        clauses.append(f"district ILIKE ${push(f'%{district}%')}")

    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    return where_sql, params


async def execute_search_pg(
    pool: asyncpg.Pool,
    parsed: Any,
    message: str,
    embedding: list[float] | None,
    district: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[asyncpg.Record], int]:
    """Execute hybrid search using pgvector cosine similarity.
    
    Parameters are safely positional ($1, $2, ...) computed before SQL construction
    to prevent SQL injection and ensure type safety.
    
    Args:
        pool: Database connection pool
        parsed: Parsed query with filters (min_beds, max_price, location, etc.)
        message: Search query string (for logging)
        embedding: Vector embedding for semantic search (optional)
        district: District name filter (optional)
        limit: Maximum number of results (default: 50)
        offset: Pagination offset for cursor-based pagination
        
    Returns:
        Tuple of (properties list, total matching records)
        
    Raises:
        Exception: If database connection fails or query errors
    """
    # Build WHERE clause with safe parameterized queries
    where_sql, params = _build_where_clause(parsed, district)

    # Build ORDER BY clause based on embedding availability
    order_by = ""
    
    if embedding and len(embedding) > 0:
        emb_str = f"[{','.join(f'{v:.6f}' for v in embedding)}]"
        params.append(emb_str)
        emb_idx = len(params)
        
        # Use L2 distance for vector search (pgvector native support)
        embed_limit = limit + 10  # Fetch more than requested for better ranking
        embed_offset = offset
        
        sql = (
            f"SELECT *, (embedding IS NOT NULL)::int as has_embedding "
            f"FROM properties WHERE {where_sql} "
            f"ORDER BY embedding <=> ${emb_idx}::vector "
            f"LIMIT ${embed_limit} OFFSET ${embed_offset}"
        )
    else:
        # No embedding - use simple ORDER BY id for deterministic results
        params.append(limit)
        params.append(offset)
        
        base_sql = (
            f"SELECT *, (embedding IS NOT NULL)::int as has_embedding "
            f"FROM properties WHERE {where_sql} "
            f"ORDER BY id OFFSET $2 LIMIT $1"
        )
        sql = base_sql
    
    logger.debug(f"[Search] Executing query: limit={limit}, offset={offset}, where={where_sql}")
    
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql, *params)
            total = len(rows)
            logger.info(f"[Search] Found {total} properties for query: {message[:50]}...")
        except Exception as e:
            logger.error(f"[Search] Query execution failed: {e}", exc_info=True)
            raise
    
    return rows, total


# ------------------------------------------------------------------ Counters

async def count_properties(pool: asyncpg.Pool) -> int:
    """Count total properties in database.
    
    Args:
        pool: Database connection pool
        
    Returns:
        Total count of property records
    """
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM properties")


async def count_sales(pool: asyncpg.Pool) -> int:
    """Count total sales records.
    
    Args:
        pool: Database connection pool
        
    Returns:
        Total count of sales records
    """
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM sales")


# ------------------------------------------------------------------ Fetch single property

async def fetch_property_by_id(pool: asyncpg.Pool, prop_id: int) -> asyncpg.Record | None:
    """Fetch a single property by ID.
    
    Args:
        pool: Database connection pool
        prop_id: Primary key of property to fetch
        
    Returns:
        Property record if found, None otherwise
    """
    sql = (
        "SELECT id, address_line1, address_line2, town, postcode, outcode, "
        "property_type, num_beds, price_paid, date_sold, latitude, longitude "
        "FROM properties WHERE id = $1"
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
    """Execute search with pagination support.
    
    Converts 1-indexed pagination to offset-based queries for database compatibility.
    Uses cursor-like behavior through offset/limit pattern.
    
    Args:
        pool: Database connection pool
        parsed: Parsed query with filters
        query: Original search query string
        embedding: Vector embedding for semantic search (optional)
        district: District name filter (optional)
        limit: Results per page (default: 20)
        page: Page number (1-indexed, default: 1)
        
    Returns:
        Dict with properties, pagination info, and metadata
        
    Raises:
        ValueError: If page or limit parameters are invalid
    """
    # Validate parameters
    if page < 1:
        raise ValueError("Page must be at least 1")
    if limit < 1:
        raise ValueError("Limit must be at least 1")
    
    # Convert to offset-based pagination
    offset = (page - 1) * limit
    
    rows, total = await execute_search_pg(pool, parsed, query, embedding, district, limit=limit, offset=offset)
    
    return {
        "properties": [dict(r) for r in rows],
        "total_matches": total,
        "page": page,
        "per_page": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
        "has_next": offset + len(rows) < total,
        "has_prev": page > 1,
    }


# ------------------------------------------------------------------ Statistics

async def get_property_statistics(pool: asyncpg.Pool) -> dict[str, Any]:
    """Get database statistics for monitoring.
    
    Args:
        pool: Database connection pool
        
    Returns:
        Dictionary with various database metrics
    """
    queries = [
        ("Total properties", "SELECT COUNT(*) FROM properties"),
        ("Properties with embedding", "SELECT COUNT(*) FROM properties WHERE embedding IS NOT NULL"),
        ("Properties without embedding", "SELECT COUNT(*) FROM properties WHERE embedding IS NULL"),
        ("Average property price", "SELECT AVG(price_paid)::NUMERIC(10,2) FROM properties"),
        ("Median property price (approx)", """
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_paid)::NUMERIC(10,2) 
            FROM properties
        """),
        ("Most common property type", """
            SELECT property_type, COUNT(*) as count 
            FROM properties 
            GROUP BY property_type 
            ORDER BY count DESC 
            LIMIT 1
        """),
    ]
    
    stats: dict[str, Any] = {}
    async with pool.acquire() as conn:
        for name, sql in queries:
            value = await conn.fetchval(sql)
            stats[name] = value
    
    return stats


# ------------------------------------------------------------------ Bulk operations

async upsert_properties_batch(pool: asyncpg.Pool, properties: list[dict[str, Any]]) -> dict[str, int]:
    """Batch upsert multiple properties.
    
    Args:
        pool: Database connection pool
        properties: List of property dictionaries
        
    Returns:
        Dictionary mapping original addresses to their row IDs
    """
    results: dict[str, int] = {}
    
    for prop in properties:
        try:
            row_id = await upsert_property(pool, prop)
            address = prop.get("address_line1", f"Unknown-{row_id}")
            results[address] = row_id
        except Exception as e:
            logger.error(f"[BulkUpsert] Failed to insert {prop}: {e}", exc_info=True)
    
    return results


async def search_by_postcode(
    pool: asyncpg.Pool,
    postcode: str,
    limit: int = 50,
) -> tuple[list[asyncpg.Record], int]:
    """Search properties within a specific postcode area.
    
    Args:
        pool: Database connection pool
        postcode: Postcode to search (e.g., "CW10")
        limit: Maximum results (default: 50)
        
    Returns:
        Tuple of (properties list, total count)
    """
    sql = """
        SELECT id, address_line1, address_line2, town, postcode, outcode,
               property_type, num_beds, price_paid, date_sold, latitude, longitude,
               embedding IS NOT NULL as has_embedding
        FROM properties
        WHERE postcode ILIKE $1
        ORDER BY price_paid ASC
        LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, f"%{postcode}%", limit)
        return rows, len(rows)
