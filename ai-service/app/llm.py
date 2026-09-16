"""Embedding providers — OpenAI and hash-based fallback."""

from __future__ import annotations

import hashlib
import struct
from typing import Optional


class Embedder:
    """Base embedding interface."""

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class OpenAIEmbedder(Embedder):
    """Use OpenAI text-embedding models for semantic vectors."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model = model
        self._client = None  # lazy import

    async def embed(self, text: str) -> list[float]:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)

        response = await self._client.embeddings.create(
            input=text, model=self.model, dimensions=768
        )
        vec = response.data[0].embedding
        return [float(v) for v in vec]


class HashEmbedder(Embedder):
    """Deterministic hash-based embedding as a dev/test fallback.

    Maps text to a fixed-dimensional vector via MurmurHash-like features.
    NOT semantically meaningful — used only when no API key is available.
    """

    def __init__(self, dim: int = 768):
        self.dim = dim

    async def embed(self, text: str) -> list[float]:
        # Hash-based vector using a single robust hash pass
        digest = hashlib.sha256(text.encode()).digest()
        result = []
        for i in range(self.dim):
            # Use chunks of the digest to derive values
            chunk = digest[i % len(digest) : (i % len(digest)) + 4]
            if not chunk: # Fallback for small digests
                chunk = digest[:4]
            h = int.from_bytes(chunk, "big")
            result.append((h % 10000 - 5000) / 5000.0)
        return result
