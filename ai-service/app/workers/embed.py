"""Background embedding worker — generates property embeddings in bulk."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768


async def run_embedding_worker(
    pool,
    embedder,
    batch_size: int = 50,
    max_batches: int = 1_000,
) -> int:
    """Embed properties that have no embedding yet.

    Rows whose embedding call fails are skipped (not filled with zero vectors,
    which would poison vector search and mark the row as done).
    """
    if not pool or not embedder:
        return 0

    fetch_sql = (
        "SELECT id, address_line1, town, ward, postcode, property_type, num_beds, "
        "floor_area_sqm, tenure, source "
        "FROM properties WHERE embedding IS NULL ORDER BY id LIMIT $1"
    )
    update_sql = "UPDATE properties SET embedding = $1::vector WHERE id = $2"

    updated = 0

    for _ in range(max_batches):
        async with pool.acquire() as conn:
            rows = await conn.fetch(fetch_sql, batch_size)
        if not rows:
            break

        documents = [_embedding_document(row) for row in rows]
        embeddings = await _batch_embed(documents, embedder)

        pairs = [
            (_vector_literal(embedding), row["id"])
            for row, embedding in zip(rows, embeddings)
            if embedding is not None
        ]

        if not pairs:
            # Every row in this batch failed; stop rather than spin forever.
            logger.error("[EmbedWorker] batch failed entirely; stopping")
            break

        async with pool.acquire() as conn:
            await conn.executemany(update_sql, pairs)

        updated += len(pairs)

    return updated


def _embedding_document(row: Any) -> str:
    """Compose the text that gets embedded.

    Embedding an address alone carries no semantic signal. Composing the
    property's attributes makes vector search meaningful and gives the LLM
    something to explain.
    """
    parts = [
        f"{row.get('num_beds') or '?'} bed",
        row.get("property_type") or "",
        f"{row.get('floor_area_sqm'):.0f} sqm" if row.get("floor_area_sqm") else "",
        row.get("tenure") or "",
        row.get("address_line1") or "",
        row.get("town") or "",
        row.get("ward") or "",
        row.get("postcode") or "",
        row.get("source") or "",
    ]
    return ", ".join(part for part in parts if part).strip()


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.6f}" for value in embedding) + "]"


async def _batch_embed(documents: list[str], embedder) -> list[list[float] | None]:
    """Embed a batch, returning None for individual failures."""
    results = await asyncio.gather(
        *(embedder.embed(document) for document in documents),
        return_exceptions=True,
    )

    embeddings: list[list[float] | None] = []
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("[EmbedWorker] embedding failed: %s", result)
            embeddings.append(None)
            continue
        if len(result) != EMBEDDING_DIM:
            logger.warning(
                "[EmbedWorker] unexpected dimension %s (expected %s)",
                len(result),
                EMBEDDING_DIM,
            )
            embeddings.append(None)
            continue
        embeddings.append(result)
    return embeddings


_worker_task: asyncio.Task | None = None


async def start_embedding_worker(pool, embedder, interval_sec: int = 300) -> None:
    """Start the embedding worker as a background task."""
    global _worker_task

    async def loop() -> None:
        while True:
            try:
                count = await run_embedding_worker(pool, embedder)
                if count:
                    logger.info("[EmbedWorker] embedded %s properties", count)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("[EmbedWorker] error: %s", exc, exc_info=True)
            await asyncio.sleep(interval_sec)

    _worker_task = asyncio.create_task(loop())


def stop_embedding_worker() -> None:
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        _worker_task = None
