"""Backfill property embeddings.

    python scripts/embed_properties.py                      # uses .env + DATABASE_URL
    python scripts/embed_properties.py --dsn postgresql://...
    python scripts/embed_properties.py --limit 100 --batch 25
    python scripts/embed_properties.py --force              # re-embed everything

Resumable: only rows with a NULL embedding are processed unless --force.
Rows that fail are left NULL (never zero-filled, which would poison search).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ai-service"))

import asyncpg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app.llm import HashEmbedder, OllamaEmbedder, OpenAIEmbedder, is_placeholder_secret  # noqa: E402
from app.workers.embed import run_embedding_worker  # noqa: E402

load_dotenv(ROOT / ".env")


def build_embedder(force_hash: bool = False):
    """Mirror the service's provider selection (OpenAI > Ollama > hash)."""
    if not force_hash:
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not is_placeholder_secret(key):
            try:
                return OpenAIEmbedder(api_key=key), "openai"
            except Exception:  # noqa: BLE001
                pass
        if os.getenv("OLLAMA_URL"):
            embedder = OllamaEmbedder(
                base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
                model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            )
            return embedder, "ollama"
    return HashEmbedder(), "hash"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=None, help="max rows this run")
    parser.add_argument("--batch", type=int, default=25)
    parser.add_argument("--force", action="store_true", help="re-embed existing rows")
    parser.add_argument("--hash", action="store_true", help="force the hash embedder")
    args = parser.parse_args()

    if not args.dsn or not args.dsn.startswith("postgres"):
        print("DATABASE_URL must be a postgres:// or postgresql:// URL")
        return 2

    embedder, provider = build_embedder(args.hash)
    print(f"embedder: {provider} ({type(embedder).__name__})")

    pool = await asyncpg.create_pool(args.dsn, min_size=1, max_size=4)
    try:
        if args.force:
            async with pool.acquire() as conn:
                await conn.execute("UPDATE properties SET embedding = NULL")
            print("cleared existing embeddings")

        pending = await pool.fetchval(
            "SELECT count(*) FROM properties WHERE embedding IS NULL"
        )
        print(f"rows pending: {pending}")
        if not pending:
            print("nothing to do")
            return 0

        started = time.perf_counter()
        remaining = args.limit
        total = 0
        while True:
            batch_size = args.batch if remaining is None else min(args.batch, remaining)
            if batch_size <= 0:
                break
            done = await run_embedding_worker(
                pool, embedder, batch_size=batch_size, max_batches=1
            )
            if done == 0:
                break
            total += done
            remaining = None if remaining is None else remaining - done
            elapsed = time.perf_counter() - started
            print(f"  embedded {total} ({total / elapsed:,.1f}/s)", flush=True)

        elapsed = time.perf_counter() - started
        stored = await pool.fetchval(
            "SELECT count(*) FROM properties WHERE embedding IS NOT NULL"
        )
        failed = await pool.fetchval(
            "SELECT count(*) FROM properties WHERE embedding IS NULL"
        )
        print(
            f"done: {total} embedded in {elapsed:.1f}s, "
            f"{stored} stored, {failed} still null"
        )
        return 0 if failed == 0 else 1
    finally:
        await pool.close()
        close = getattr(embedder, "aclose", None)
        if close is not None:
            await close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
