"""Semantic cache — similarity-thresholded caching for search & chat."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CacheEntry:
    query: str
    result: dict[str, Any]
    embedding: list[float] = field(default_factory=list)
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _hash_bucket(text: str, bucket_count: int = 256) -> int:
    """Hash text into one of several buckets for fast pre-filtering."""
    h = hashlib.md5(text.lower().encode()).hexdigest()
    return int(h[:4], 16) % bucket_count


class InMemorySemanticCache:
    """Simple in-memory cache with cosine-similarity lookups.

    Uses hash-based bucket pre-filtering to avoid full-store scans at scale.
    Evicts entries that exceed max_size or are older than ttl_seconds (LRU).
    """

    def __init__(
        self,
        embedder=None,
        threshold: float = 0.85,
        ttl_seconds: int = 3600,
        max_size: int = 10_000,
    ):
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self.threshold = threshold
        self._embedder = embedder
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._bucket_count = 256

    def _evict_expired(self) -> None:
        """Remove entries past their TTL."""
        now = time.time()
        expired_keys = [
            k for k, e in self._store.items()
            if now - e.created_at > self.ttl_seconds
        ]
        for k in expired_keys:
            del self._store[k]

    def _evict_if_needed(self) -> None:
        """Evict oldest entries when the store has exceeded max_size."""
        while len(self._store) >= self.max_size:
            # OrderedDict.popitem(last=False) removes the oldest entry (FIFO/LRU)
            self._store.popitem(last=False)

    def _find_exact_match(self, query_lower: str) -> str | None:
        """Find exact case-insensitive match among surviving entries."""
        for key in self._store:
            if key.lower() == query_lower:
                entry = self._store[key]
                if time.time() - entry.created_at <= self.ttl_seconds:
                    return key
                del self._store[key]
        return None

    async def get(self, query: str) -> dict | None:
        """Look up a cached result by semantic similarity."""
        query_lower = query.lower()
        self._evict_expired()

        # Enforce max_size on every lookup so the cache never overflows when
        # callers bypass put() (e.g. direct InMemorySemanticCache usage).
        while len(self._store) >= self.max_size:
            self._store.popitem(last=False)  # remove LRU (oldest)

        # Fast path: exact match (also handles TTL)
        key = self._find_exact_match(query_lower)
        if key:
            entry = self._store[key]
            entry.hit_count += 1
            self._store.move_to_end(key)
            return entry.result

        # Slow path: semantic match — use hash bucket to narrow candidates
        if not self._embedder:
            return None

        q_emb = await self._embedder.embed(query)
        bucket = _hash_bucket(query, self._bucket_count)

        best_sim = 0.0
        best_key = None
        for key, entry in self._store.items():
            if time.time() - entry.created_at > self.ttl_seconds:
                continue
            if not entry.embedding:
                continue
            # Additional bucket check — only compare entries from same hash bucket
            if _hash_bucket(entry.query, self._bucket_count) != bucket:
                continue
            sim = _cosine_sim(q_emb, entry.embedding)
            if sim > best_sim:
                best_sim = sim
                best_key = key

        if best_key and best_sim >= self.threshold:
            entry = self._store.pop(best_key)  # move to end
            entry.hit_count += 1
            self._store[best_key] = entry
            return entry.result
        return None

    async def put(self, query: str, result: dict):
        """Cache a search result with its embedding."""
        emb = []
        if self._embedder:
            emb = await self._embedder.embed(query)
        entry = CacheEntry(query=query, result=result, embedding=emb)

        # Remove existing entry for same query (case-insensitive)
        query_lower = query.lower()
        existing_key = next(
            (k for k in self._store if k.lower() == query_lower), None
        )
        if existing_key:
            del self._store[existing_key]

        # Evict oldest entries if at capacity
        while len(self._store) >= self.max_size:
            self._store.popitem(last=False)  # remove LRU (oldest)

        self._store[query] = entry

    def clear(self):
        self._store.clear()


class PostgresChatCache:
    """pgvector-backed chat cache using the embeddings table."""

    def __init__(self, pool, embedder=None):
        self.pool = pool
        self.embedder = embedder

    async def get(self, query: str) -> dict | None:
        if not self.pool:
            return None
        emb = await self.embedder.embed(query) if self.embedder else [0.0] * 768
        sql = """
            SELECT result FROM chat_cache
            ORDER BY embedding <=> $1
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, str(emb))
        if row:
            return row["result"]
        return None

    async def put(self, query: str, result: dict):
        if not self.pool or not self.embedder:
            return
        emb = await self.embedder.embed(query)
        sql = """
            INSERT INTO chat_cache (query, embedding, result)
            VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
        """
        async with self.pool.acquire() as conn:
            vec_str = f"[{','.join(f'{v:.6f}' for v in emb)}]"
            await conn.execute(sql, query, vec_str, json.dumps(result))
