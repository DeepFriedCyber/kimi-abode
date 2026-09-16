"""FastAPI application entry point — lifespan, middleware, health."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .cache import InMemorySemanticCache
from .chat.service import ChatService, AnthropicChatLLM, ChatFallbackLLM
from .llm import HashEmbedder, OpenAIEmbedder
from .router import QueryRouter


# ------------------------------------------------------------------ lifespan
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # --- embedder (semantic cache backend) ---------------------------------
    if key := os.getenv("OPENAI_API_KEY"):
        app.state.embedder = OpenAIEmbedder(key)
    else:
        app.state.embedder = HashEmbedder()

    # --- router with providers and semantic cache --------------------------
    base_router = QueryRouter(cache=InMemorySemanticCache(app.state.embedder))
    for provider in (app.state.providers if hasattr(app.state, "providers") else []):
        base_router.add_provider(provider)
    app.state.router = base_router

    # --- database pool ------------------------------------------------------
    app.state.pool = None
    if url := os.getenv("DATABASE_URL"):
        app.state.pool = await asyncpg.create_pool(url)

    # --- chat service -------------------------------------------------------
    chat_llm: AnthropicChatLLM | ChatFallbackLLM
    if os.getenv("ANTHROPIC_API_KEY"):
        chat_llm = AnthropicChatLLM(os.getenv("ANTHROPIC_API_KEY"))  # type: ignore[arg-type]
    else:
        chat_llm = ChatFallbackLLM()
    app.state.chat_service = ChatService(
        llm=chat_llm,
        cache=base_router.cache,
    )

    yield

    if app.state.pool:
        await app.state.pool.close()


# ------------------------------------------------------------------ app
app = FastAPI(
    title="Abode AI Service",
    description="UK property search, ingestion, chat & POI backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Build CORS allowed origins from env (comma-separated) or default to dev gateway URL
_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3001")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

if "*" in _cors_origins:
    # Wildcard + credentials is invalid per CORS spec — browsers reject it.
    # Fall back to the default gateway origin so the browser actually accepts the headers.
    _cors_origins = ["http://localhost:3001"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=None,  # use exact origins above instead
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---- shared metrics --------------------------------------------------------
_request_count: int = 0
_metric_lock: object  # placeholder — will be threading.Lock in prod


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Increment request counter on every response."""
    global _request_count
    response = await call_next(request)
    _request_count += 1
    return response


# ------------------------------------------------------------------ health
@app.get("/health")
async def health():
    """Health check — reports DB connectivity."""
    db_ok = False
    if app.state.pool:
        try:
            async with app.state.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            pass
    return {"status": "ok", "db": db_ok}


# ------------------------------------------------------------------ parse
@app.post("/parse")
async def parse_endpoint(body: dict):
    """Parse a natural-language query.

    Example POST body: {"query": "3 bed semi-detached in Sandbach under £250k"}
    """
    from .parser import parse_query
    from .schemas import ParseRequest

    req = ParseRequest(**body)
    result = await parse_query(req.query)
    return result.model_dump(mode="json")


# ------------------------------------------------------------------ search
@app.get("/search")
async def search_endpoint(
    query: str,
    min_beds: int | None = None,
    max_price: float | None = None,
    location: str | None = None,
    outcode: str | None = None,
    district: str | None = None,
    limit: int = 50,
):
    """Search properties using parsed filters + pgvector."""
    from .schemas import ParsedQuery

    parsed = ParsedQuery(
        raw=query,
        tier="",
        min_beds=min_beds,
        max_price=max_price,
        property_types=[],
        location=location or None,
        outcode=outcode or None,
        district=district or None,
        has_location=bool(location),
        has_price=bool(max_price),
    )

    if not app.state.pool:
        return {
            "properties": [],
            "tier_used": "deterministic",
            "total_matches": 0,
            "message": "No database connection configured",
        }

    emb = None
    if app.state.embedder:
        emb = await app.state.embedder.embed(query)

    from .repository import execute_search_pg
    rows, total = await execute_search_pg(app.state.pool, parsed, query, emb, district, limit)

    return {
        "properties": [dict(r) for r in rows],
        "tier_used": "deterministic",
        "total_matches": total,
        "message": f"Found {total} properties matching: {query}",
    }


# ------------------------------------------------------------------ metrics
@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus-compatible metrics render."""
    return PlainTextResponse(f"abode_http_requests_total {_request_count}\n")


# ------------------------------------------------------------------ mounts (routers)
from .routers import chat, poi  # noqa: E402

app.include_router(chat.router, prefix="/chat")
app.include_router(poi.router, prefix="/poi")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
