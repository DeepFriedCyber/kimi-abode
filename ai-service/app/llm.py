"""Embedding providers — OpenAI, Ollama (local), and hash-based fallback."""

from __future__ import annotations

import hashlib
from typing import Optional

EMBEDDING_DIM = 768


class Embedder:
    """Base embedding interface."""

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release any underlying HTTP client."""
        return None


class OpenAIEmbedder(Embedder):
    """Use OpenAI text-embedding models for semantic vectors."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model = model
        self._client = None

    async def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def embed(self, text: str) -> list[float]:
        client = await self._get_client()
        kwargs = {"input": text, "model": self.model}
        # Only the v3 models accept a custom dimension; passing it to others 400s.
        if self.model.startswith("text-embedding-3"):
            kwargs["dimensions"] = EMBEDDING_DIM

        response = await client.embeddings.create(**kwargs)
        return [float(value) for value in response.data[0].embedding]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


class OllamaEmbedder(Embedder):
    """Use a local Ollama server for embeddings (no API costs)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client: Optional["httpx.AsyncClient"] = None  # type: ignore[name-defined]

    async def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30)
        return self._client

    async def embed(self, text: str) -> list[float]:
        client = await self._get_client()
        response = await client.post(
            "/api/embed",
            json={"model": self.model, "input": text, "truncate": True},
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings") or []
        if not embeddings:
            raise ValueError("Ollama returned no embeddings")
        return [float(value) for value in embeddings[0]]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class HashEmbedder(Embedder):
    """Deterministic hash-based embedding for development and tests.

    This is NOT semantic: different sentences produce near-orthogonal vectors.
    It exists so the service runs without an API key, and it means the semantic
    cache behaves like an exact-match cache.
    """

    def __init__(self, dim: int = EMBEDDING_DIM):
        if dim < 1:
            raise ValueError("dim must be positive")
        self.dim = dim

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand the digest deterministically to `dim` values in [-1, 1].
        values: list[float] = []
        for index in range(self.dim):
            window = (digest * ((index // len(digest)) + 1))[index : index + 4]
            chunk = int.from_bytes(window, "big")
            values.append((chunk % 10_000 - 5_000) / 5_000.0)
        return values
