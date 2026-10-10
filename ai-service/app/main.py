"""FastAPI application entry point — lifespan, middleware, health.

This module initializes the Abode AI Service with proper connection pooling,
CORS configuration, and graceful fallback modes for development/testing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .cache import InMemorySemanticCache
from .chat.service import ChatService, AnthropicChatLLM, ChatFallbackLLM
from .llm import HashEmbedder, OllamaEmbedder, OpenAIEmbedder
from .router import QueryRouter


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ database pool configuration
# These settings prevent connection exhaustion and improve performance
_DB_POOL_MIN = int(os.getenv("AI_DB_POOL_MIN", "2"))  # Min connections
_DB_POOL_MAX = int(os.getenv("AI_DB_POOL_MAX", "10"))  # Max connections  
_DB_TIMEOUT_SEC = int(os.getenv("AI_DB_TIMEOUT", "30"))  # Idle timeout in seconds

# Validate pool configuration
if _DB_POOL_MAX < _DB_POOL_MIN:
    logger.warning(
        f"Pool configuration invalid (max={_DB_POOL_MAX}, min={_DB_POOL_MIN}). "
        f"Using defaults: min=2, max=10"
    )
    _DB_POOL_MIN = 2
    _DB_POOL_MAX = 10


# ------------------------------------------------------------------ lifespan
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle management.
    
    Handles embedder initialization and database pool creation on startup,
    proper cleanup on shutdown.
    """
    # Load .env (only when server starts, not on import during tests)
    from dotenv import load_dotenv
    load_dotenv()

    # --- embedder (semantic cache backend) ---------------------------------
    embedder: HashEmbedder | OllamaEmbedder | OpenAIEmbedder | None = None
    
    if key := os.getenv("OPENAI_API_KEY"):
        logger.info("[Lifespan] Initializing OpenAI embedder")
        try:
            embedder = OpenAIEmbedder(key)
        except Exception as e:
            logger.error(f"[Lifespan] Failed to init OpenAI embedder: {e}")

    elif os.getenv("OLLAMA_URL"):
        logger.info("[Lifespan] Initializing Ollama embedder")
        try:
            model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
            embedder = OllamaEmbedder(
                base_url=os.getenv("OLLAMA_URL"),
                model=model,
            )
        except Exception as e:
            logger.error(f"[Lifespan] Failed to init Ollama embedder: {e}")

    else:
        # Fallback to hash-based embedding (deterministic but no vector search)
        logger.info("[Lifespan] Using deterministic hash embedder (no vector DB)")
        embedder = HashEmbedder()

    app.state.embedder = embedder

    # --- database pool ------------------------------------------------------
    pool_config: dict[str, Any] = {
        "min_size": _DB_POOL_MIN,
        "max_size": _DB_POOL_MAX,
        "timeout": _DB_TIMEOUT_SEC,
    }
    
    app.state.pool = None
    
    if url := os.getenv("DATABASE_URL"):
        logger.info(f"[Lifespan] Creating database pool with URL: {url[:30]}...")
        try:
            app.state.pool = await asyncpg.create_pool(url, **pool_config)
            # Verify connection by executing a simple query
            async with app.state.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("[Lifespan] Database pool created successfully")
        except Exception as e:
            logger.error(f"[Lifespan] Failed to create database pool: {e}")
            logger.warning("[Lifespan] Continuing without database connection (read-only mode)")

    # --- router with providers and semantic cache --------------------------
    from .router import QueryRouter, build_providers

    app.state.providers = build_providers(pool=app.state.pool, embedder=embedder)
    base_router = QueryRouter(cache=InMemorySemanticCache(app.state.embedder))
    for provider in app.state.providers:
        base_router.add_provider(provider)
    
    logger.info(f"[Lifespan] Router initialized with {len(app.state.providers)} providers")

    # --- chat service -------------------------------------------------------
    chat_llm: AnthropicChatLLM | ChatFallbackLLM
    if os.getenv("ANTHROPIC_API_KEY"):
        logger.info("[Lifespan] Initializing Anthropic chat LLM")
        chat_llm = AnthropicChatLLM(os.getenv("ANTHROPIC_API_KEY"))  # type: ignore[arg-type]
    else:
        logger.info("[Lifespan] Using ChatFallbackLLM (deterministic responses)")
        chat_llm = ChatFallbackLLM()
        
    app.state.chat_service = ChatService(
        llm=chat_llm,
        cache=base_router.cache,
    )

    yield
    
    # Cleanup on shutdown
    logger.info("[Lifespan] Shutting down application")
    
    if app.state.pool:
        try:
            await app.state.pool.close()
            logger.info("[Lifespan] Database pool closed")
        except Exception as e:
            logger.error(f"[Lifespan] Error closing database pool: {e}")


# ------------------------------------------------------------------ app
app = FastAPI(
    title="Abode AI Service",
    description="UK property search, ingestion, chat & POI backend",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc documentation
    openapi_url="/openapi.json",
)


# Build CORS allowed origins from env (comma-separated) or default to dev gateway URL
_cors_origins_raw = os.getenv("AI_CORS_ORIGINS", "http://localhost:3001")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

if "*" in _cors_origins:
    # Wildcard + credentials is invalid per CORS spec — browsers reject it.
    # Fall back to the default gateway origin so the browser actually accepts the headers.
    logger.warning("[CORS] '*' found in origins - using specific gateway URL instead")
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
        
        # Log high-traffic endpoints for monitoring
        if request.url.path in ["/api/parse", "/api/search"]:
            logger.info(f"[Metrics] Request #{_request_count}: {request.method} {request.url.path}")
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
        except Exception as e:
            logger.error(f"[Health] DB check failed: {e}")
            db_ok = False
    else:
        # No DB configured but service can still run in read-only mode
        db_ok = False
    
    return {
        "status": "ok", 
        "db": db_ok,
        "mode": "read-write" if app.state.pool else "read-only",
        "embedder_type": type(app.state.embedder).__name__ if app.state.embedder else "none",
    }


# ------------------------------------------------------------------ parse
@app.post("/parse")
async def parse_endpoint(body: dict):
    """Parse a natural-language query.

    Converts user's search query into structured filters (min_beds, max_price, location, etc.).
    
    Example POST body: {"query": "3 bed semi-detached in Sandbach under £250k"}
    
    Returns:
        {
            "intent": string,
            "entities": [...],
            "original_query": string,
            "parsed_at": ISO 8601 timestamp,
        }
    """
    from .parser import parse_query
    from .schemas import ParseRequest

    req = ParseRequest(**body)
    
    try:
        result = await parse_query(req.query)
        return {
            **result.model_dump(mode="json"),
            "parsed_at": asyncio.get_event_loop().time(),  # For monitoring
        }
    except Exception as e:
        # Graceful degradation - continue with deterministic tier
        logger.error(f"[Parse] Error parsing query '{req.query}': {e}", exc_info=True)
        
        # Return deterministic fallback response
        from .parser import parse_query_deterministic as fallback_parse
        
        try:
            result = await fallback_parse(req.query)
            return {
                **result.model_dump(mode="json"),
                "tier": "deterministic",
                "parsed_at": asyncio.get_event_loop().time(),
            }
        except Exception as e2:
            logger.error(f"[Parse] Fallback parsing also failed: {e2}", exc_info=True)
            return {
                "error": str(e2),
                "message": "Failed to parse query - service degraded",
                "parsed_at": asyncio.get_event_loop().time(),
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
    """Search properties using parsed filters + pgvector.

    Accepts query parameters:
    - query: The search string (e.g., "detached house in Sandbach")
    - min_beds: Minimum number of bedrooms (optional)
    - max_price: Maximum price in pounds (optional)
    - location: Town or area to filter by (optional)
    - outcode: Postcode area to filter by (optional)
    - district: District name for additional filtering (optional)
    - limit: Maximum results (default: 50, max: 100)

    Returns:
        {
            "properties": [...],
            "tier_used": string (semantic|deterministic),
            "total_matches": int,
            "message": string,
            "limit": int,
        }
    """
    # Validate parameters
    try:
        if min_beds is not None and min_beds < 0:
            raise ValueError("min_beds cannot be negative")
        if max_price is not None and max_price < 0:
            raise ValueError("max_price cannot be negative")
        if limit > 100:
            raise ValueError("limit cannot exceed 100")
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e), "message": "Invalid parameter"}
        )

    from .repository import execute_search_pg
    from .schemas import ParsedQuery

    parsed = ParsedQuery(
        raw=query,
        tier="",  # Will be set by parser
        min_beds=min_beds,
        max_price=max_price,
        property_types=[],  # Set by parser
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
            "limit": limit,
        }

    try:
        emb = None
        if app.state.embedder and hasattr(app.state.embedder, 'embed'):
            # Only generate embeddings for non-hash embedders
            from llm import HashEmbedder
            if not isinstance(app.state.embedder, HashEmbedder):
                emb = await app.state.embedder.embed(query)
                logger.info(f"[Search] Generated embedding for query: {query[:30]}...")
    except Exception as e:
        logger.error(f"[Search] Embedding failed, using deterministic tier: {e}")
        
    try:
        rows, total = await execute_search_pg(app.state.pool, parsed, query, emb, district, limit)
        
        # Determine search tier used
        semantic_tier = "semantic" if emb and len(emb) > 0 else "deterministic"
        
        return {
            "properties": [dict(r) for r in rows],
            "tier_used": semantic_tier,
            "total_matches": total,
            "message": f"Found {total} properties matching: {query[:50]}...",
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"[Search] Error during search for '{query}': {e}", exc_info=True)
        
        # Graceful degradation to deterministic results
        return {
            "properties": [],
            "tier_used": "deterministic",
            "total_matches": 0,
            "error": str(e),
            "message": f"Search failed with error: {e}. Using fallback mode.",
            "limit": limit,
        }


# ------------------------------------------------------------------ property
@app.get("/property")
async def property_endpoint(id: int):
    """Fetch a single property by ID.

    Args:
        id: Primary key of the property to fetch
        
    Returns:
        Property record or error if not found/database unavailable
    """
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
        # Convert asyncpg.Record to dict for JSON serialization
        return dict(row)
    except Exception as e:
        logger.error(f"[Property] Error fetching property {id}: {e}", exc_info=True)
        return {
            "id": id,
            "error": f"Failed to fetch property",
        }


# ------------------------------------------------------------------ metrics
@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus-compatible metrics render.

    Returns text/plain format suitable for Prometheus scraping.
    """
    _ensure_metrics_lock().acquire()
    try:
        count = _request_count
    finally:
        _ensure_metrics_lock().release()
    
    return PlainTextResponse(f"abode_http_requests_total {count}\n")


# ------------------------------------------------------------------ database info
@app.get("/db/info")
async def db_info():
    """Database connection information and statistics.

    Returns database pool configuration and health status.
    """
    if not app.state.pool:
        return {
            "connected": False,
            "pool_config": None,
            "message": "No database configured",
        }
    
    try:
        async with app.state.pool.acquire() as conn:
            # Get PostgreSQL version and database name
            async with conn.transaction():
                version = await conn.fetchval("SELECT version()")
                dbname = await conn.fetchval("SELECT current_database()")
                
                return {
                    "connected": True,
                    "version": str(version),
                    "database": dbname,
                    "pool_size": app.state.pool.min_size,
                    "pool_max": app.state.pool.max_size,
                }
    except Exception as e:
        logger.error(f"[DB Info] Failed to get DB info: {e}", exc_info=True)
        return {
            "connected": False,
            "error": str(e),
        }


# ------------------------------------------------------------------ mounts (routers)
from .routers import chat, poi  # noqa: E402

app.include_router(chat.router, prefix="/chat")
app.include_router(poi.router, prefix="/poi")


@app.get("/docs/{doc}")
async def docs_redirect(doc: str):
    """Redirect to /docs for Swagger UI."""
    return RedirectResponse(url="/docs", status_code=307)
