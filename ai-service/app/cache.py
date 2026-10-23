"""Semantic cache — similarity-thresholded caching for search & chat.

Entries are keyed by (context, query). `context` exists so a chat answer cached
for one property is never served for another, and so search results with
different filters do not collide.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheEntry:
    query: str
    result: dict[str, Any]
    embedding: list[float] = field(default_factory=list)
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def cache_key(context: str, query: str) -> str:
    """Stable key for a (context, query) pair."""
    return f"{context.strip().lower()}\x1f{query.strip().lower()}"


class InMemorySemanticCache:
    """LRU + TTL cache with optional cosine-similarity lookup.

    Lookup is O(n) over live entries. That is acceptable for the default
    `max_size` (1 000) and a single process; move to pgvector/Redis before
    raising it. The previous docstring claimed hash-bucketed pre-filtering that
    was never implemented.
    """

    def __init__(
        self,
        embedder=None,
        threshold: float = 0.9,
        ttl_seconds: int = 3_600,
        max_size: int = 1_000,
    ):
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        if max_size < 1:
            raise ValueError("max_size must be >= 1")

        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._embedder = embedder
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size

    # -- internals ---------------------------------------------------------
    def _is_live(self, entry: CacheEntry, now: float) -> bool:
        return (now - entry.created_at) < self.ttl_seconds

    def _evict(self, now: float) -> None:
        for key in [k for k, e in self._store.items() if not self._is_live(e, now)]:
            del self._store[key]

    def _enforce_capacity(self) -> None:
        while len(self._store) >= self.max_size:
            self._store.popitem(last=False)  # oldest / least recently used

    # -- public API --------------------------------------------------------
    async def get(self, query: str, *, context: str = "") -> dict | None:
        """Return a cached result, exact match first then semantic match."""
        now = time.time()
        self._evict(now)

        key = cache_key(context, query)
        entry = self._store.get(key)
        if entry and self._is_live(entry, now):
            entry.hit_count += 1
            self._store.move_to_end(key)
            return json.loads(json.dumps(entry.result))  # defensive copy

        if not self._embedder:
            return None

        query_embedding = await self._embedder.embed(query)
        best_key: str | None = None
        best_similarity = 0.0

        for candidate_key, candidate in self._store.items():
            if not self._is_live(candidate, now) or not candidate.embedding:
                continue
            similarity = _cosine_sim(query_embedding, candidate.embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_key = candidate_key

        if best_key is None or best_similarity < self.threshold:
            return None

        hit = self._store.pop(best_key)
        hit.hit_count += 1
        self._store[best_key] = hit
        return json.loads(json.dumps(hit.result))

    async def put(self, query: str, result: dict, *, context: str = "") -> None:
        """Store a result, embedding the query when an embedder is configured."""
        embedding: list[float] = []
        if self._embedder:
            try:
                embedding = await self._embedder.embed(query)
            except Exception:  # noqa: BLE001 - caching must never break a request
                embedding = []

        key = cache_key(context, query)
        self._store.pop(key, None)
        self._enforce_capacity()
        self._store[key] = CacheEntry(query=query, result=result, embedding=embedding)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


class PostgresChatCache:
    """pgvector-backed chat cache.

    Uses cosine distance with a maximum-distance guard so an unrelated question
    cannot be served from cache.
    """

    def __init__(self, pool, embedder=None, max_distance: float = 0.15):
        self.pool = pool
        self.embedder = embedder
        self.max_distance = max_distance

    def _cache_text(self, query: str, context: str) -> str:
        return f"[{context.strip().lower()}] {query.strip()}" if context else query.strip()

    async def get(self, query: str, *, context: str = "") -> dict | None:
        if not self.pool or not self.embedder:
            return None

        embedding = await self.embedder.embed(self._cache_text(query, context))
        sql = """
            SELECT result, embedding <=> $1::vector AS distance
            FROM chat_cache
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT 1
        """
        vector = "[" + ",".join(f"{value:.6f}" for value in embedding) + "]"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, vector)

        if row and float(row["distance"]) <= self.max_distance:
            result = row["result"]
            return json.loads(result) if isinstance(result, str) else dict(result)
        return None

    async def put(self, query: str, result: dict, *, context: str = "") -> None:
        if not self.pool or not self.embedder:
            return

        text = self._cache_text(query, context)
        embedding = await self.embedder.embed(text)
        vector = "[" + ",".join(f"{value:.6f}" for value in embedding) + "]"

        sql = """
            INSERT INTO chat_cache (query, embedding, result)
            VALUES ($1, $2::vector, $3::jsonb)
            ON CONFLICT DO NOTHING
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, text, vector, json.dumps(result))


def hash_text(text: str) -> str:
    """Small helper for callers that need a deterministic key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
