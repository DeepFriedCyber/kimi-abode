"""FastAPI application entry point — lifespan, middleware, health."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .cache import InMemorySemanticCache
from .chat.service import ChatService, AnthropicChatLLM, ChatFallbackLLM
from .llm import HashEmbedder, OllamaEmbedder, OpenAIEmbedder
from .router import QueryRouter


# ------------------------------------------------------------------ database pool configuration
# These settings prevent connection exhaustion and improve performance
_DB_POOL_MIN = int(os.getenv("AI_DB_POOL_MIN", "2"))  # Min connections
_DB_POOL_MAX = int(os.getenv("AI_DB_POOL_MAX", "10"))  # Max connections  
_DB_TIMEOUT_SEC = int(os.getenv("AI_DB_TIMEOUT", "30"))  # Idle timeout in seconds

# ------------------------------------------------------------------ lifespan
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Load .env (only when server starts, not on import during tests)
    from dotenv import load_dotenv
    load_dotenv()

    # --- embedder (semantic cache backend) ---------------------------------
    if key := os.getenv("OPENAI_API_KEY"):
        app.state.embedder = OpenAIEmbedder(key)
    elif os.getenv("OLLAMA_URL"):
        app.state.embedder = OllamaEmbedder(
            base_url=os.getenv("OLLAMA_URL"),
            model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        )
    else:
        app.state.embedder = HashEmbedder()

    # --- database pool ------------------------------------------------------
    app.state.pool = None
    if url := os.getenv("DATABASE_URL"):
        try:
            # Create pool with connection limits and proper configuration
            # Note: asyncpg uses different parameter names in connection string than psycopg2
            pool_config = {}
            app.state.pool = await asyncpg.create_pool(url)
        except Exception as e:
            print(f"[AI Service] Failed to create database pool: {e}")
            print("[AI Service] Continuing without database connection (read-only mode)")

    # --- router with providers and semantic cache --------------------------
    from .router import QueryRouter, build_providers

    app.state.providers = build_providers(pool=app.state.pool, embedder=app.state.embedder)
    base_router = QueryRouter(cache=InMemorySemanticCache(app.state.embedder))
    for provider in app.state.providers:
        base_router.add_provider(provider)
    app.state.router = base_router

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
_cors_origins_raw = os.getenv("AI_CORS_ORIGINS", "http://localhost:3001")
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
    allow_headers=["Content-Type", "Authorization", "x-api-key"],
)


# ---- shared metrics --------------------------------------------------------
_request_count: int = 0
_metric_lock: object | None = None


def _ensure_metrics_lock() -> object:
    """Ensure we have a lock for thread-safe metric updates."""
    global _metric_lock
    if _metric_lock is None:
        import threading
        _metric_lock = threading.Lock()
    return _metric_lock


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Increment request counter on every response (thread-safe)."""
    response = await call_next(request)
    
    # Thread-safe counter increment
    _ensure_metrics_lock().acquire()
    try:
        global _request_count
        _request_count += 1
    finally:
        _ensure_metrics_lock().release()
    
    return response


# ------------------------------------------------------------------ health
@app.get("/health")
async def health():
    """Health check — reports DB connectivity and service status."""
    db_ok = False
    
    if app.state.pool:
        try:
            async with app.state.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
    else:
        # No DB configured but service can still run in read-only mode
        db_ok = False
    
    return {
        "status": "ok", 
        "db": db_ok,
        "mode": "read-write" if app.state.pool else "read-only",
    }


# ------------------------------------------------------------------ parse
@app.post("/parse")
async def parse_endpoint(body: dict):
    """Parse a natural-language query.

    Example POST body: {"query": "3 bed semi-detached in Sandbach under £250k"}
    """
    from .parser import parse_query
    from .schemas import ParseRequest

    req = ParseRequest(**body)
    
    try:
        result = await parse_query(req.query)
        return result.model_dump(mode="json")
    except Exception as e:
        # Graceful degradation - continue with deterministic tier
        print(f"[Parse Service] Error parsing query: {e}")
        from .parser import parse_query_deterministic as fallback_parse
        try:
            result = await fallback_parse(req.query)
            return result.model_dump(mode="json")
        except Exception as e2:
            return {
                "error": str(e2),
                "message": "Failed to parse query - service degraded",
            }


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
            "message": "No database connection configured - using fallback search",
        }

    try:
        emb = None
        if app.state.embedder:
            emb = await app.state.embedder.embed(query)
    except Exception as e:
        print(f"[Search Service] Embedding failed, using deterministic tier: {e}")
        # Continue without embeddings (fallback to semantic cache only)

    try:
        rows, total = await execute_search_pg(app.state.pool, parsed, query, emb, district, limit)
        
        return {
            "properties": [dict(r) for r in rows],
            "tier_used": "deterministic" if not emb else "semantic",
            "total_matches": total,
            "message": f"Found {total} properties matching: {query}",
        }
    except Exception as e:
        print(f"[Search Service] Error during search: {e}")
        return {
            "properties": [],
            "tier_used": "deterministic",
            "total_matches": 0,
            "error": str(e),
            "message": f"Search failed: {e}",
        }


# ------------------------------------------------------------------ property
@app.get("/property")
async def property_endpoint(id: int):
    """Fetch a single property by ID."""
    from .repository import fetch_property_by_id

    if not app.state.pool:
        return {
            "id": id,
            "error": "No database connection configured",
        }

    try:
        row = await fetch_property_by_id(app.state.pool, id)
        if row is None:
            return {
                "id": id,
                "error": "Property not found",
            }
        return dict(row)
    except Exception as e:
        print(f"[Property Service] Error fetching property {id}: {e}")
        return {
            "id": id,
            "error": f"Failed to fetch property: {e}",
        }


# ------------------------------------------------------------------ metrics
@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus-compatible metrics render."""
    _ensure_metrics_lock().acquire()
    try:
        count = _request_count
    finally:
        _ensure_metrics_lock().release()
    
    return PlainTextResponse(f"abode_http_requests_total {count}\n")


# ------------------------------------------------------------------ mounts (routers)
from .routers import chat, poi  # noqa: E402

app.include_router(chat.router, prefix="/chat")
app.include_router(poi.router, prefix="/poi")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)