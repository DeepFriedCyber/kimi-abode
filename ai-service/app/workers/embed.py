"""Background embedding worker — generates property embeddings in bulk."""

from __future__ import annotations

import asyncio
from typing import Any, Optional


async def run_embedding_worker(
    pool,
    embedder,
    batch_size: int = 50,
) -> int:
    """Fetch properties without embeddings and generate them.

    Returns the number of properties updated.
    """
    if not pool or not embedder:
        return 0

    sql_fetch = "SELECT id, address_line1 FROM properties WHERE embedding IS NULL LIMIT %s"
    sql_update = "UPDATE properties SET embedding = $1 WHERE id = $2"

    count = 0
    while True:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql_fetch, batch_size)
        if not rows:
            break

        # Batch embed
        addresses = [r["address_line1"] for r in rows]
        embeddings = await _batch_embed(addresses, embedder)

        async with pool.acquire() as conn:
            for row, emb in zip(rows, embeddings):
                await conn.execute(sql_update, str(emb), row["id"])
                count += 1

    return count


async def _batch_embed(addresses: list[str], embedder) -> list[list[float]]:
    """Batch-embed a list of addresses."""
    tasks = [embedder.embed(addr) for addr in addresses]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    for r in results:
        if isinstance(r, Exception):
            valid_results.append([0.0] * 768)  # fallback zero vector
        else:
            valid_results.append(r)

    return valid_results


# Background task scheduler (simple interval-based — in prod use Celery/RQ)
_worker_task = None


async def start_embedding_worker(pool, embedder, interval_sec: int = 300):
    """Start the embedding worker as a background task."""
    global _worker_task

    async def _loop():
        while True:
            try:
                n = await run_embedding_worker(pool, embedder)
                if n > 0:
                    print(f"Embedding worker: {n} properties embedded")
            except Exception as e:
                print(f"Embedding worker error: {e}")
            await asyncio.sleep(interval_sec)

    _worker_task = asyncio.create_task(_loop())


def stop_embedding_worker():
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        _worker_task = None
