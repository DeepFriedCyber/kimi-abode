"""Database helpers — pooling, migrations, upserts."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg


_MIGRATION_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    """Create a new asyncpg connection pool.

    Callers are responsible for closing the pool when done.
    For single-instance apps, consider managing the pool via FastAPI lifespan.
    """
    url = dsn or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:pass@host:5432/dbname"
        )
    return await asyncpg.create_pool(url)


async def close_pool(pool: asyncpg.Pool | None) -> None:
    """Close a specific pool instance."""
    if pool:
        await pool.close()


async def run_migrations(pool: asyncpg.Pool | None = None) -> None:
    """Execute all numbered SQL migrations in order."""
    owned_pool = False
    try:
        if pool is None:
            pool = await create_pool()
            owned_pool = True

        # Create extensions
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        files = sorted(_MIGRATION_DIR.glob("*.sql"))
        for f in files:
            print(f"  -> migrating {f.name}...")
            sql = f.read_text(encoding="utf-8")
            async with pool.acquire() as conn:
                await conn.execute(sql)
        print(f"  done -- {len(files)} migrations applied.")
    finally:
        if owned_pool and pool:
            await close_pool(pool)


def main():
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
