"""FastAPI application entry point — lifespan, middleware, health.

Owns the database pool, embedder, search providers and chat service, and exposes
the HTTP surface consumed by the gateway (Node) or directly by the frontend.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import asyncpg
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from .cache import InMemorySemanticCache
from .chat.service import AnthropicChatLLM, ChatFallbackLLM, ChatService
from .llm import HashEmbedder, OllamaEmbedder, OpenAIEmbedder
from .media import ensure_media_root, is_safe_media_path
from .router import DeterministicSearchProvider, QueryRouter, build_providers, demo_data_enabled
from .schemas import ParsedQuery, ParseRequest, PropertyType

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_DB_POOL_MIN = int(os.getenv("AI_DB_POOL_MIN", "2"))
_DB_POOL_MAX = int(os.getenv("AI_DB_POOL_MAX", "10"))
_DB_TIMEOUT_SEC = int(os.getenv("AI_DB_TIMEOUT", "30"))

if _DB_POOL_MAX < _DB_POOL_MIN:
    logger.warning(
        "Invalid pool config (min=%s, max=%s); using min=2, max=10",
        _DB_POOL_MIN,
        _DB_POOL_MAX,
    )
    _DB_POOL_MIN, _DB_POOL_MAX = 2, 10


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def poi_answer_lookup(text: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Answer amenity questions from the property's coordinates and POI cache."""
    property_row = (context or {}).get("property") or {}
    latitude, longitude = property_row.get("latitude"), property_row.get("longitude")
    if latitude is None or longitude is None:
        return None

    from .poi.query import answer_poi_question
    from .routers.poi import get_poi_data

    pois = get_poi_data()
    if not pois:
        return None

    return answer_poi_question(pois, float(latitude), float(longitude), text)


def _secret(name: str) -> str:
    """Read a secret, ignoring obvious placeholders from example env files."""
    value = os.getenv(name, "").strip()
    if not value:
        return ""

    lowered = value.lower()
    if "xxxx" in lowered or lowered.startswith(("your", "sk-proj-xxx", "changeme")):
        logger.warning("[Config] %s looks like a placeholder — ignoring it", name)
        return ""

    return value


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise shared resources on startup and release them on shutdown."""
    from dotenv import load_dotenv

    load_dotenv()

    # --- embedder ----------------------------------------------------------
    embedder: HashEmbedder | OllamaEmbedder | OpenAIEmbedder | None = None

    if api_key := _secret("OPENAI_API_KEY"):
        try:
            embedder = OpenAIEmbedder(api_key)
            logger.info("[Lifespan] Using OpenAI embedder")
        except Exception as exc:  # noqa: BLE001
            logger.error("[Lifespan] OpenAI embedder init failed: %s", exc)
    elif os.getenv("OLLAMA_URL"):
        try:
            embedder = OllamaEmbedder(
                base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
                model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            )
            logger.info("[Lifespan] Using Ollama embedder")
        except Exception as exc:  # noqa: BLE001
            logger.error("[Lifespan] Ollama embedder init failed: %s", exc)

    if embedder is None:
        logger.info("[Lifespan] Using deterministic hash embedder (no semantic search)")
        embedder = HashEmbedder()

    app.state.embedder = embedder

    # --- database pool -----------------------------------------------------
    app.state.pool = None
    if database_url := os.getenv("DATABASE_URL"):
        if not database_url.startswith(("postgres://", "postgresql://")):
            logger.warning(
                "[Lifespan] DATABASE_URL is not a PostgreSQL URL (%s...); "
                "search will run without a database.",
                database_url[:20],
            )
        else:
            try:
                app.state.pool = await asyncpg.create_pool(
                    database_url,
                    min_size=_DB_POOL_MIN,
                    max_size=_DB_POOL_MAX,
                    timeout=_DB_TIMEOUT_SEC,
                )
                async with app.state.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                logger.info("[Lifespan] Database pool ready")
            except Exception as exc:  # noqa: BLE001
                logger.error("[Lifespan] Database pool failed: %s", exc)
                app.state.pool = None

    # --- search providers + cache -----------------------------------------
    app.state.providers = build_providers(pool=app.state.pool, embedder=embedder)
    app.state.router = QueryRouter(cache=InMemorySemanticCache(embedder))
    for provider in app.state.providers:
        app.state.router.add_provider(provider)
    logger.info("[Lifespan] %s providers registered", len(app.state.providers))

    # --- chat --------------------------------------------------------------
    if anthropic_key := _secret("ANTHROPIC_API_KEY"):
        chat_llm = AnthropicChatLLM(anthropic_key)
        logger.info("[Lifespan] Anthropic chat enabled")
    else:
        chat_llm = ChatFallbackLLM()
        logger.info("[Lifespan] Chat running in fallback mode")

    app.state.chat_service = ChatService(
        llm=chat_llm,
        cache=app.state.router.cache,
        poi_lookup=poi_answer_lookup,
    )

    # --- optional preloaded POI cache --------------------------------------
    cache_path = Path(
        os.getenv("POI_CACHE_PATH", str(Path(__file__).resolve().parent.parent / "data" / "poi_cache.json"))
    )
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            pois = payload.get("pois", []) if isinstance(payload, dict) else payload
            if pois:
                from .routers.poi import set_poi_data

                set_poi_data(pois)
                logger.info("[Lifespan] Loaded %s POIs from %s", len(pois), cache_path.name)
        except Exception as exc:  # noqa: BLE001 - cache is optional
            logger.warning("[Lifespan] Could not load POI cache: %s", exc)

    yield

    logger.info("[Lifespan] Shutting down")
    if app.state.pool:
        try:
            await app.state.pool.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("[Lifespan] Error closing pool: %s", exc)

    close = getattr(embedder, "aclose", None)
    if close is not None:
        try:
            await close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Lifespan] Error closing embedder: %s", exc)


app = FastAPI(
    title="Abode AI Service",
    description="UK property search, ingestion, chat and POI intelligence",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

_cors_origins = [
    origin.strip()
    for origin in os.getenv("AI_CORS_ORIGINS", "http://localhost:3001,http://localhost:3000").split(",")
    if origin.strip() and origin.strip() != "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "x-api-key", "x-request-id"],
)

# Listing photos are generated with content-hashed filenames, so they are
# immutable and safe to cache aggressively. Serving is done by a route (rather
# than StaticFiles) so the media root can be relocated in tests and the path
# allowlist is enforced.
ensure_media_root()


@app.get("/media/{path:path}")
async def media_file(path: str):
    from . import media as media_module

    if not is_safe_media_path(path):
        return JSONResponse(status_code=404, content={"error": "Not found"})

    root = media_module.MEDIA_ROOT.resolve()
    candidate = (media_module.MEDIA_ROOT / path).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return JSONResponse(status_code=404, content={"error": "Not found"})

    return FileResponse(
        candidate,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---- metrics ---------------------------------------------------------------
_request_count = 0


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Count requests. Single-process counter (use Prometheus for multi-worker)."""
    global _request_count
    response = await call_next(request)
    _request_count += 1

    if request.url.path.startswith("/media/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")

    return response


# ---- health ----------------------------------------------------------------
@app.get("/health")
async def health():
    """Liveness + database status."""
    pool = getattr(app.state, "pool", None)
    embedder = getattr(app.state, "embedder", None)

    db_ok = False
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            logger.error("[Health] DB check failed: %s", exc)

    return {
        "status": "ok",
        "db": db_ok,
        "mode": "read-write" if pool else "fallback",
        "embedder_type": type(embedder).__name__ if embedder else "none",
        "demo_data": demo_data_enabled(),
    }


@app.get("/")
async def root():
    return {"service": "abode-ai", "docs": "/docs", "health": "/health"}


# ---- parse -----------------------------------------------------------------
@app.post("/parse")
async def parse_endpoint(payload: ParseRequest):
    """Parse a natural-language query into structured filters."""
    from .parser import parse_query

    try:
        result = await parse_query(payload.query)
        return {**result.model_dump(mode="json"), "parsed_at": _utc_now()}
    except Exception as exc:  # noqa: BLE001 - degrade to deterministic parsing
        logger.error("[Parse] failed for %r: %s", payload.query, exc, exc_info=True)
        from .parser import _deterministic_parse

        fallback = _deterministic_parse(payload.query)
        return {
            **fallback.model_dump(mode="json"),
            "tier": "FORCED_DETERMINISTIC",
            "degraded": True,
            "parsed_at": _utc_now(),
        }


# ---- search ----------------------------------------------------------------
def _coerce_property_types(values: list[str] | None) -> list[PropertyType]:
    types: list[PropertyType] = []
    for raw in values or []:
        try:
            types.append(PropertyType(raw.strip().lower()))
        except ValueError:
            logger.warning("[Search] ignoring unknown property type %r", raw)
    return types


@app.get("/search")
async def search_endpoint(
    query: str = Query(min_length=1, max_length=500),
    min_beds: int | None = Query(default=None, ge=0, le=20),
    max_beds: int | None = Query(default=None, ge=0, le=20),
    max_price: float | None = Query(default=None, ge=0, le=50_000_000),
    location: str | None = Query(default=None, max_length=120),
    outcode: str | None = Query(default=None, max_length=8),
    district: str | None = Query(default=None, max_length=120),
    property_types: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Search properties using parsed filters plus optional semantic ranking."""
    pool = getattr(app.state, "pool", None)

    if max_beds is not None and min_beds is not None and max_beds < min_beds:
        return JSONResponse(
            status_code=400,
            content={"error": "max_beds must be greater than or equal to min_beds"},
        )

    from .parser import parse_query

    # Parse the free-text query first, then let explicit parameters win.
    parsed = await parse_query(query)
    if min_beds is not None:
        parsed.min_beds = min_beds
    if max_beds is not None:
        parsed.max_beds = max_beds
    if max_price is not None:
        parsed.max_price = max_price
    if location:
        parsed.location = location
        parsed.has_location = True
    if outcode:
        parsed.outcode = outcode
        parsed.has_location = True
    if district:
        parsed.district = district
    if property_types:
        parsed.property_types = _coerce_property_types(property_types)

    if not pool:
        return await _demo_search(parsed, query, limit)

    embedding: list[float] | None = None
    embedder = getattr(app.state, "embedder", None)
    if embedder and not isinstance(embedder, HashEmbedder):
        try:
            embedding = await embedder.embed(query)
        except Exception as exc:  # noqa: BLE001 - fall back to keyword search
            logger.warning("[Search] embedding failed: %s", exc)

    from .repository import execute_search_pg, search_live_listings

    live_rows, live_total = [], 0
    try:
        live_rows, live_total = await search_live_listings(pool, parsed, query, limit)
    except Exception as exc:  # noqa: BLE001 - migration 006 may not be applied yet
        logger.warning("[Search] live listing search unavailable: %s", exc)

    try:
        sold_rows, sold_total = await execute_search_pg(
            pool, parsed, query, embedding, parsed.district, limit
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[Search] query failed: %s", exc, exc_info=True)
        if not live_rows:
            return JSONResponse(
                status_code=503,
                content={"error": "Search is temporarily unavailable", "properties": []},
            )
        sold_rows, sold_total = [], 0

    properties = _merge_results(live_rows, sold_rows, limit)

    if pool is not None and properties:
        live_ids = [item["id"] for item in properties if item.get("asking_price") is not None]
        if live_ids:
            try:
                from .repository import list_photos_for_listings

                photos_by_listing = await list_photos_for_listings(pool, live_ids)
                for item in properties:
                    if item.get("asking_price") is not None:
                        item["photos"] = photos_by_listing.get(item["id"], [])
            except Exception as exc:  # noqa: BLE001 - photos are optional
                logger.warning("[Search] could not attach photos: %s", exc)

    if live_rows and sold_rows:
        tier = "live+sold"
    elif live_rows:
        tier = "live"
    else:
        tier = "semantic" if embedding else "deterministic"

    return {
        "properties": properties,
        "tier_used": tier,
        "total_matches": live_total + sold_total,
        "message": (
            f"Found {live_total + sold_total} properties matching “{query[:50]}”"
            f" ({live_total} for sale, {sold_total} sold)"
        ),
        "limit": limit,
    }


def _merge_results(live_rows: Any, sold_rows: Any, limit: int) -> list[dict[str, Any]]:
    """Live listings first, then sold comparables; dedupe by address + postcode."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for row in list(live_rows) + list(sold_rows):
        data = dict(row)
        key = (
            (data.get("address_line1") or "").strip().lower(),
            (data.get("postcode") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(data)
        if len(merged) >= limit:
            break

    return merged


async def _demo_search(parsed: ParsedQuery, query: str, limit: int) -> dict[str, Any]:
    """Serve fixture data when no database is configured (development only)."""
    if not demo_data_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Search is not configured (DATABASE_URL missing)",
                "properties": [],
                "total_matches": 0,
            },
        )

    provider = DeterministicSearchProvider()
    result = await provider.execute(query, parsed=parsed) or {}
    properties = result.get("properties", [])[:limit]
    return {
        "properties": properties,
        "tier_used": "deterministic-demo",
        "total_matches": result.get("total_matches", len(properties)),
        "message": "Demo data (no database configured)",
        "limit": limit,
    }


# ---- property --------------------------------------------------------------
async def _resolve_property(pool, property_id: int) -> tuple[dict[str, Any] | None, bool]:
    """Return (record, is_live_listing) from the demo store or Postgres."""
    from .property_service import resolve_property

    return await resolve_property(pool, property_id)


@app.get("/property")
async def property_endpoint(id: int = Query(ge=1)):
    """Fetch a single property (live listing or sold record)."""
    pool = getattr(app.state, "pool", None)
    if pool is None and not demo_data_enabled():
        return JSONResponse(status_code=503, content={"error": "Database not configured"})

    try:
        record, is_listing = await _resolve_property(pool, id)
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"error": "Lookup failed"})

    if record is None:
        return JSONResponse(status_code=404, content={"error": "Property not found"})

    if is_listing and pool is not None:
        from .repository import list_listing_photos

        try:
            record["photos"] = await list_listing_photos(pool, id)
        except Exception as exc:  # noqa: BLE001 - photos are optional
            logger.warning("[Property] could not attach photos: %s", exc)

    return record


@app.get("/property/{property_id}/nearby")
async def property_nearby(
    property_id: int,
    q: str = Query(min_length=2, max_length=200),
):
    """Answer "how far is the nearest Tesco?" for a property.

    Deterministic: parsed intent + POI data + haversine. The LLM never guesses
    distances or brands.
    """
    from .poi.query import answer_poi_question
    from .routers.poi import get_poi_data

    pool = getattr(app.state, "pool", None)
    if pool is None and not demo_data_enabled():
        return JSONResponse(status_code=503, content={"error": "Database not configured"})

    try:
        record, _ = await _resolve_property(pool, property_id)
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"error": "Lookup failed"})

    if record is None:
        return JSONResponse(status_code=404, content={"error": "Property not found"})

    latitude, longitude = record.get("latitude"), record.get("longitude")
    if latitude is None or longitude is None:
        return JSONResponse(
            status_code=422,
            content={"error": "This property has no coordinates, so amenities cannot be measured"},
        )

    pois = get_poi_data()
    if not pois:
        return JSONResponse(
            status_code=503,
            content={"error": "Amenity data is not loaded (run scripts/preload_pois)"},
        )

    result = answer_poi_question(pois, float(latitude), float(longitude), q)
    if result is None:
        return JSONResponse(
            status_code=422,
            content={
                "error": "I can only answer questions about nearby amenities",
                "examples": [
                    "How far is the nearest Tesco?",
                    "What gyms are nearby?",
                    "Nearest train station",
                    "Primary schools within 2 miles",
                ],
            },
        )

    result["property_id"] = property_id
    return result


# ---- metrics ---------------------------------------------------------------
@app.get("/metrics")
async def metrics_endpoint():
    return PlainTextResponse(
        "# HELP abode_http_requests_total Total HTTP requests handled\n"
        "# TYPE abode_http_requests_total counter\n"
        f"abode_http_requests_total {_request_count}\n"
    )


# ---- database info ---------------------------------------------------------
@app.get("/db/info")
async def db_info():
    pool = getattr(app.state, "pool", None)
    if not pool:
        return {"connected": False, "pool_config": None, "message": "No database configured"}

    try:
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            database = await conn.fetchval("SELECT current_database()")
    except Exception as exc:  # noqa: BLE001
        logger.error("[DBInfo] failed: %s", exc)
        return {"connected": False, "error": "Database query failed"}

    return {
        "connected": True,
        "version": version,
        "database": database,
        "pool_min": pool.get_min_size(),
        "pool_max": pool.get_max_size(),
    }


# ---- routers ---------------------------------------------------------------
from .routers import chat, poi, listings, photos  # noqa: E402

app.include_router(chat.router, prefix="/chat")
app.include_router(poi.router, prefix="/poi")
app.include_router(listings.router, prefix="/listings")
app.include_router(photos.router, prefix="/listings")
