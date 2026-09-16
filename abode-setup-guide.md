
# Abode AI — Project Setup Guide

Monorepo: **ai-service** (Python/FastAPI :8001) · **api** (TypeScript/Fastify :3001) · **frontend** (Next.js 15 :3000) · **Postgres+pgvector** · **Redis**

---

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | ≥ 3.11 | `python --version` |
| Node.js | ≥ 20 (web-stream async iteration) | `node --version` |
| Docker Desktop | running (Postgres, Redis, testcontainers) | `docker ps` |
| VSCode extensions | Python, Pylance, ESLint, Docker | — |

---

## 2. Repository layout

```
abode/
├── docker-compose.yml
├── .env                                  # from .env.example
├── abode.code-workspace                  # multi-root (§11)
├── ai-service/
│   ├── requirements.txt  pytest.ini
│   ├── migrations/  001_initial.sql  002_auth.sql  003_sold_prices.sql  004_postcode_geo.sql
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py  schemas.py  gazetteer.py  parser.py  llm.py  cache.py
│   │   ├── router.py  search.py  db.py  repository.py  seed.py
│   │   ├── ingestion/   schemas formats blm mapping transform validate dedup pipeline persist sold_loader
│   │   ├── workers/     embed.py
│   │   ├── chat/        intents context cache service
│   │   ├── routers/     chat.py  poi.py
│   │   ├── poi/         geohash overpass scorer qa
│   │   ├── enrichment/  postcodes_io enrich review_report
│   │   ├── observability/ metrics tracing
│   │   └── security/    redact.py
│   └── tests/           (unit + integration, mirroring app/)
├── api/
│   ├── package.json  tsconfig.json  vitest.config.ts
│   ├── src/   config index app /services /plugins /routes /ws /observability
│   └── test/  (vitest suites)
└── frontend/
    ├── package.json  postcss.config.mjs  .env.local
    ├── app/   layout globals page search/page property/[id]/page
    ├── components/  SearchBox FilterChips ResultsList PropertyCard ChatPanel AskLocation
    └── lib/   api types
```

Every Python package dir needs an empty `__init__.py` (`app/`, `app/ingestion/`, `app/workers/`, `app/chat/`, `app/routers/`, `app/poi/`, `app/enrichment/`, `app/observability/`, `app/security/`).

---

## 3. Step 1 — Copy files from the conversation artifacts

Each artifact contained multiple files separated by `# ===== path =====` headers — split on those. Config blocks embedded as **comments** (`# {`, `// {`) need the comment prefix stripped.

| Artifact | Extract to |
|---|---|
| AI Service — Core Parser | `app/schemas.py`, `app/parser.py` ⚠️, `app/gazetteer.py` ⚠️ |
| AI Service — Router/LLM/Cache/Search/API | `app/llm.py`, `app/cache.py`, `app/router.py`, `app/search.py` ⚠️, `app/main.py`, `requirements.txt`, `pytest.ini` |
| AI Service — Tests | `tests/test_parser.py`, `test_router.py`, `test_search.py` |
| Ingestion — Formats/BLM/Mapping | `app/ingestion/{schemas,formats,blm,mapping}.py` |
| Ingestion — Transform/Validate/Dedup/Pipeline | `app/ingestion/{transform,validate,dedup,pipeline,persist}.py` ⚠️ |
| Ingestion — Tests | `tests/ingestion/test_ingestion.py` |
| Data Layer — Migrations & Docker | `migrations/001_initial.sql`, `docker-compose.yml`, `.env.example` |
| Data Layer — Repository/Worker/Persist/Seed | `app/db.py`, `app/repository.py`, `app/workers/embed.py`, `app/seed.py` |
| Data Layer — Integration Tests | `tests/integration/{conftest,helpers,test_upsert,test_embed_worker,test_search_db,test_persist}.py` |
| API Server — Fastify core | `api/package.json`, `tsconfig.json`, `vitest.config.ts`, `api/src/**` |
| API Server — Tests | `api/test/*.test.ts` |
| Frontend — Next.js | `frontend/**` |
| Chat — Core (Python) | `app/chat/*`, `app/routers/chat.py` |
| Chat — Tests | `tests/chat/*` |
| API — Chat Socket Bridge | `api/src/ws/*`, `api/test/{sse,chat-handler}.test.ts` |
| Frontend — ChatPanel | `frontend/components/ChatPanel.tsx` |
| POI — Core | `app/poi/*`, `app/routers/poi.py` |
| POI — Tests | `tests/poi/*` ⚠️ see §4 note |
| POI Wiring | `api/src/routes/ask.ts`, `api/test/ask.test.ts`, `frontend/components/AskLocation.tsx` |
| Hardening — Auth | `migrations/002_auth.sql`, `api/src/services/{passwords,user-store}.ts`, `api/src/routes/auth.ts` |
| Hardening — Auth Tests | `api/test/{auth-routes,passwords}.test.ts` |
| Hardening — Observability (TS) | `api/src/observability/*`, `api/src/config/validate.ts`, `api/test/metrics.test.ts` |
| Hardening — Observability (Py) | `app/observability/*`, `app/security/redact.py`, `tests/hardening/*` |
| Sold-Data Loader | `migrations/003_sold_prices.sql`, `app/ingestion/sold_loader.py` |
| Sold-Data Tests | `tests/ingestion/test_sold_loader.py`, `tests/integration/test_sold_loader.py` |
| Town Enrichment | `app/gazetteer.py` ✅ **final**, `migrations/004_postcode_geo.sql`, `app/enrichment/{postcodes_io,enrich}.py` |
| Enrichment Tests | `tests/enrichment/test_postcodes_io.py`, `tests/integration/test_enrichment.py` |
| Compound-Type Tests | `tests/parser/test_compound_types.py`, `tests/integration/test_compound_types.py` |
| Review Report | `app/enrichment/review_report.py` |

---

## 4. Step 2 — ⚠️ Use the LATEST version of these 5 files

| File | Final version | If you use the stale one… |
|---|---|---|
| `app/gazetteer.py` | **Complete replacement** in *Town Enrichment* artifact | "Sandbach"/"Crewe" won't parse as locations |
| `app/parser.py` | Original + **compound-type `TYPE_PATTERNS`** (update block) | "semi-detached" also returns detached houses |
| `app/search.py` | Original + **town/district clause** (update block) | location search returns zero results |
| `app/ingestion/dedup.py` | Original + **number-conflict guard** (update block) | 23/25 Station Road-style false merges |
| `app/ingestion/transform.py` | Original + **housemetric transforms** (update block) | sold_loader crashes on missing transforms |

Also: in `tests/poi/test_scorer.py`, replace the broken import line with:
```python
from app.poi.scorer import (PoiPoint, decay_score, haversine_m, nearest,
                            score_property)
```

---

## 5. Step 3 — Apply the 5 wiring patches

### Patch A — `app/main.py`

Add at module level (after `app = FastAPI(...)`):

```python
from fastapi.responses import PlainTextResponse
from app.observability.metrics import Metrics, MetricsMiddleware, InstrumentedRouter
from app.routers.chat import router as chat_router
from app.routers.poi import router as poi_router
from app.chat.service import ChatService, AnthropicChatLLM
from app.chat.cache import PostgresChatCache, InMemoryChatCache

metrics = Metrics()
app.add_middleware(MetricsMiddleware, metrics=metrics)
app.include_router(chat_router)
app.include_router(poi_router)

class _NoLLM:
    async def stream(self, messages):
        yield ("Chat needs ANTHROPIC_API_KEY — but I can still compute "
               "stamp duty, mortgages, and search homes.")

@app.get("/metrics")
async def metrics_endpoint():
    return PlainTextResponse(metrics.render())
```

Replace the lifespan body with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if key := os.getenv("OPENAI_API_KEY"):
        app.state.embedder = OpenAIEmbedder(key)
    else:
        app.state.embedder = HashEmbedder()

    base_router = QueryRouter(providers=build_providers(),
                              cache=InMemorySemanticCache(app.state.embedder))
    app.state.router = InstrumentedRouter(base_router, metrics)

    app.state.pool = None
    if url := os.getenv("DATABASE_URL"):
        import asyncpg
        app.state.pool = await asyncpg.create_pool(url)

    async def search_fn(parsed, message):
        if not app.state.pool:
            return []
        from app.repository import execute_search_pg
        emb = await app.state.embedder.embed(parsed.semantic_remainder or message)
        rows, _ = await execute_search_pg(app.state.pool, parsed, message, emb, None, 6)
        return [dict(r) for r in rows]

    llm = AnthropicChatLLM(os.environ["ANTHROPIC_API_KEY"]) if os.getenv("ANTHROPIC_API_KEY") else _NoLLM()
    cache = PostgresChatCache(app.state.pool, app.state.embedder) if app.state.pool else InMemoryChatCache(app.state.embedder)
    app.state.chat_service = ChatService(llm, cache, parse_fn=app.state.router.parse, search_fn=search_fn)
    yield
    if app.state.pool:
        await app.state.pool.close()
```

In `search()`: import and call `execute_search_pg` (from `app.repository`) instead of `execute_search` — **required**, asyncpg has no pgvector codec.

### Patch B — `api/src/app.ts` (inside `buildApp`, before `return app`)

```typescript
import { authRoutes } from "./routes/auth";
import { askRoutes } from "./routes/ask";
import { PgUserStore } from "./services/user-store";
import { Metrics, metricsHook } from "./observability/metrics";

const metrics = new Metrics();
app.addHook("onResponse", metricsHook(metrics));
app.get("/metrics", async (_req, reply) =>
  reply.type("text/plain; version=0.0.4").send(metrics.render()));

if (cfg.databaseUrl) {
  await app.register(authRoutes({
    store: new PgUserStore(cfg.databaseUrl),
    signAccess: (sub) => app.jwt.sign({ sub }, { expiresIn: "15m" }),
  }), { prefix: "/api" });
}
await app.register(askRoutes(cfg.aiServiceUrl), { prefix: "/api" });
```

### Patch C — `api/src/index.ts` (after `buildApp`, before `listen`)

```typescript
import { attachChatSocket } from "./ws/chat.socket";
attachChatSocket(app, { aiUrl: config.aiServiceUrl, corsOrigin: config.corsOrigin });
```

### Patch D — `frontend/app/layout.tsx`

```tsx
import { ChatPanel } from "../components/ChatPanel";
// ...add <ChatPanel /> immediately before </body>
```

### Patch E — `frontend/app/property/[id]/page.tsx`

```tsx
import { AskLocation } from "../../../components/AskLocation";
// ...add <AskLocation propertyId={p.id} /> inside the <aside>, after the POI card
```

### Dependency additions

- `api/package.json`: add `"socket.io": "^4"` (deps), `"socket.io-client": "^4"` (devDeps), `"engines": {"node": ">=20"}`
- `frontend/package.json`: add `"socket.io-client": "^4"` (deps)

---

## 6. Step 4 — Install & configure

```bash
# Python
cd ai-service
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Node services
cd ../api && npm install
cd ../frontend && npm install

# Infra + env
cd .. && docker compose up -d postgres redis
cp .env.example .env
# .env: DATABASE_URL=postgresql://abode:dev@localhost:5432/abode
#       (+ OPENAI_API_KEY / ANTHROPIC_API_KEY when ready — optional for dev)
cp frontend/.env.local.example frontend/.env.local 2>/dev/null || \
  echo "NEXT_PUBLIC_API_URL=http://localhost:3001" > frontend/.env.local
```

---

## 7. Step 5 — Database & data

```bash
cd ai-service && source .venv/bin/activate
export DATABASE_URL=postgresql://abode:dev@localhost:5432/abode

python -m app.db                        # migrations 001–004
# load your real file + enrich (towns + coordinates):
python - <<'EOF'
import asyncio
from app.db import create_pool
from app.ingestion.sold_loader import load_sold_csv
from app.enrichment.enrich import enrich_properties
from app.enrichment.postcodes_io import PostcodesIO

async def main():
    pool = await create_pool()
    print(await load_sold_csv(pool, open("housemetric.csv").read()))
    while (n := await enrich_properties(pool, PostcodesIO(), batch=300)):
        print("enriched", n)
    await pool.close()
asyncio.run(main())
EOF

python -m app.enrichment.review_report  # verify against expectations
# optional: POIs for the region + scores
curl -X POST localhost:8001/poi/ingest -H 'Content-Type: application/json' \
  -d '{"bbox":"53.03,-2.60,53.28,-2.20"}'   # needs uvicorn running first
```

---

## 8. Step 6 — Run the services (3 terminals)

```bash
# T1 — AI service
cd ai-service && source .venv/bin/activate && uvicorn app.main:app --port 8001
# T2 — API server
cd api && npm run dev
# T3 — frontend
cd frontend && npm run dev
```

---

## 9. Step 7 — Run the tests

```bash
cd ai-service && source .venv/bin/activate
pytest -v                       # unit suites (~140 tests, offline)
pytest tests/integration -v     # needs Docker running (testcontainers)

cd ../api && npm test           # ~25 vitest suites, no ports/DB
```

---

## 10. Verification checklist

| Check | Expected |
|---|---|
| `curl localhost:8001/health` | `{"status":"ok","db":true}` |
| `curl -X POST localhost:8001/parse -d '{"query":"3 bed semi-detached in Sandbach under £250k"}' -H 'Content-Type: application/json'` | `tier: "deterministic"`, `location: "sandbach"` |
| `curl localhost:3001/health` | `{"status":"ok","ai":true}` |
| http://localhost:3000 → search "detached bungalow in ST7" | bungalows only, no detached houses |
| Chat widget → "stamp duty on £300k?" | streams "£5,000", tier: deterministic |
| Detail page → AskLocation → "nearest Tesco superstore?" | computed miles + walk time |
| `python -m app.enrichment.review_report` | 500 properties / 500 sales / 3 trap pairs kept separate |

---

## 11. VSCode multi-root workspace (`abode.code-workspace`)

```json
{
  "folders": [
    { "path": "ai-service" },
    { "path": "api" },
    { "path": "frontend" }
  ],
  "settings": {
    "python.defaultInterpreterPath": "${workspaceFolder:ai-service}/.venv/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false
  }
}
```

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `location search returns 0 rows` | stale `search.py` — apply town/district version (§4) |
| "semi-detached" returns detached houses | stale `parser.py` — apply compound version (§4) |
| `KeyError: 'Address'` on CSV load | BOM — loader strips it; check you're using `sold_loader.load_sold_csv` |
| asyncpg `invalid input for query argument $1` (vector) | Patch A step: must call `execute_search_pg`, not `execute_search` |
| Integration tests all SKIP | Docker not running (testcontainers needs it) |
| `pytest: module 'app' not found` | run pytest from `ai-service/` (pytest.ini sets `pythonpath = .`) |
| Chat socket auth fails | dev-token disabled when `NODE_ENV=production` — expected; use real auth |
| CORS errors in browser | set `CORS_ORIGIN=http://localhost:3000` in api env |
| `ReadableStream is not async iterable` | Node < 20 — upgrade |
