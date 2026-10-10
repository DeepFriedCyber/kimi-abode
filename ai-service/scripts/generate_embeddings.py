import asyncio
import os
import asyncpg
from app.llm import OllamaEmbedder
from app.workers.embed import run_embedding_worker

async def main():
    dsn = os.getenv("DATABASE_URL", "postgresql://abode:change_me@localhost:5432/abode")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=1, timeout=10)

    # Check current state
    async with pool.acquire() as conn:
        null_count = await conn.fetchval("SELECT COUNT(*) FROM properties WHERE embedding IS NULL")
        total = await conn.fetchval("SELECT COUNT(*) FROM properties")
        print(f"Total properties: {total}")
        print(f"Properties without embeddings: {null_count}")

    if null_count > 0:
        embedder = OllamaEmbedder()
        print(f"Generating embeddings for {null_count} properties using nomic-embed-text...")
        updated = await run_embedding_worker(pool, embedder, batch_size=50)
        print(f"Done! {updated} embeddings generated.")

        # Verify
        async with pool.acquire() as conn:
            null_after = await conn.fetchval("SELECT COUNT(*) FROM properties WHERE embedding IS NULL")
            sample = await conn.fetch("SELECT id, address_line1, town, postcode, (embedding IS NOT NULL) as has_emb FROM properties WHERE embedding IS NOT NULL LIMIT 3")
            print(f"Remaining without embeddings: {null_after}")
            for r in sample:
                print(f"  [{r['id']}] {r['address_line1']}, {r['town']} {r['postcode']} — embedded: {r['has_emb']}")

    await pool.close()

asyncio.run(main())
