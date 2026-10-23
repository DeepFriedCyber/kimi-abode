# Abode AI — UK property intelligence

Natural-language property search for the UK market: deterministic query parsing,
optional vector search, area/POI intelligence, and a streaming chat assistant.

```
Next.js (frontend)  ──HTTP──▶  Fastify gateway (/api)  ──HTTP/SSE──▶  FastAPI AI service
                                                                      ├── Postgres + pgvector
                                                                      └── fixture data (dev)
```

The gateway is deliberately thin: validation, CORS, auth, rate limiting, timeouts
and SSE passthrough. All property logic lives in the Python service.

## Quick start (development)

Requirements: Node 20+, Python 3.11+.

```bash
# 1. AI service (port 8001) — runs without a database using fixture data
cd ai-service
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# 2. API gateway (port 3001)
cd api
npm install
npm run dev

# 3. Frontend (port 3000)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

Environment files:

| File | Purpose |
|---|---|
| `api/.env` | gateway: `AI_SERVICE_URL`, `CORS_ORIGIN`, `JWT_SECRET` (≥32 chars) |
| `ai-service/.env` or root `.env` | `DATABASE_URL` (Postgres), `OPENAI_API_KEY` **or** `OLLAMA_URL`, `ANTHROPIC_API_KEY`, `DEMO_DATA`, `POI_INGEST_API_KEY` |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` |

Notes:

- Without `DATABASE_URL` the AI service serves the Sandbach fixture
  (`ai-service/data/sandbach_properties.json`) and reports `tier_used: deterministic-demo`.
  Set `DEMO_DATA=false` to disable fixtures.
- Without `ANTHROPIC_API_KEY` chat returns a deterministic fallback message.
- Without `OPENAI_API_KEY`/`OLLAMA_URL` embeddings use a non-semantic hash embedder.
- `POI_INGEST_API_KEY` protects `POST /poi/ingest`; production refuses to start
  ingest without it.

## Tests and checks

```bash
cd api        && npm run check          # tsc --noEmit + vitest
cd ai-service && python -m pytest       # unit + API smoke tests
cd frontend   && npm run check          # tsc --noEmit + next build
```

End-to-end smoke (starts both services, exercises the gateway):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/e2e-smoke.ps1
```

## Running on PostgreSQL

Without Docker (a local PostgreSQL 17/18 install is fine — pgvector must be
available to that installation):

```powershell
powershell -File scripts/dev-postgres.ps1 init      # cluster in .pgdata, port 5544
powershell -File scripts/dev-postgres.ps1 start
powershell -File scripts/dev-postgres.ps1 migrate   # 001..007, extension check
$env:DATABASE_URL = "postgresql://abode:<POSTGRES_PASSWORD from .env>@127.0.0.1:5544/abode"
python scripts/load_demo_to_postgres.py             # 500 rows, idempotent
python scripts/pg_smoke.py                          # 21 checks through the API
```

`dev-postgres.ps1` uses the password in `.env` so the connection string matches
deployment config; `reset` drops the cluster. With Docker, `docker compose up -d`
does the same job on port 5432, and the migrations mount as initdb scripts.

`pg_smoke.py` covers what the unit tests only assert against fakes: SQL search
with filters, the live/sold union, property detail, the photo joins and the POI
endpoint. Run it after any repository change.

## Demo dataset (500 historical sales)

`search_results(4).csv` is imported into `ai-service/data/demo_listings.json`
using the same pipeline the production feed uses:

```bash
cd ai-service
python -m scripts.import_listings --input "../search_results(4).csv"
```

The importer:

- splits the postcode out of the address and canonicalises it (`CW11 1JD`);
- maps `Type` onto the search taxonomy (bungalow variants collapse to `bungalow`);
- converts `Mar 2025` to `2025-03-01` and records `sold_precision: month`;
- derives `price_per_sqm` from price and floor area;
- geo-enriches every postcode via postcodes.io (ward, district, lat/lon), falling
  back to an outcode centroid when a postcode is unknown;
- validates and de-duplicates (house number **and** postcode must agree).

Use `--no-enrich` to skip network access, or `--limit N` for a quick run.
Inspect the result with `python ../scripts/fixture_report.py data/demo_listings.json`.

### Amenity data — offline OSM extract (recommended)

Overpass *is* OpenStreetMap's query API, but public instances are unreliable for
bulk and demo use. For a fixed area, download a regional extract once and filter
it locally:

```bash
cd ai-service
python -m scripts.preload_pois --download   # 221 MB North West England extract
```

That streams `data/cache/north_west.osm.pbf` with pyosmium, keeps amenities
(restaurants/cafés, pubs, schools, supermarkets, hospitals, stations) inside the
dataset's bounding box, and writes `data/poi_cache.json`, which the service loads
at startup. `*.osm.pbf` and `data/cache/` are git-ignored; the resulting cache is
small (~336 POIs for the demo area) and safe to commit.

Alternative: query Overpass directly with `--source overpass`; endpoints are
configurable via `OVERPASS_URL` or `OVERPASS_ENDPOINTS` (comma separated). If no
source is reachable, the property page shows "No amenity data available" instead
of failing.

## Agent listing uploads

Agents upload whatever their CRM exports; the importer detects the format and
columns, normalises the values, and previews before writing anything.

| Format | Notes |
|---|---|
| CSV / TSV | delimiter and encoding auto-detected (`utf-8`, `cp1252`), quoted commas |
| XLSX | first sheet, first row = headers (max 8 MB) |
| JSON / JSONL | a list of objects, or `{"listings": [...]}` |
| XML | BLM/RESO-style repeated elements; XXE blocked via `defusedxml` |
| TXT | pasted email/description → one draft listing |

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/listings/import` | multipart: `file`, `dry_run`, `mapping` (JSON), `source` |
| `POST` | `/api/listings/import/text` | `{ "text": "...", "dry_run": true }` |
| `POST` | `/api/listings` | single canonical listing (CRM integration) |
| `GET` | `/api/listings` | paginated (`limit`, `offset`, `agent_id`) |
| `GET` | `/api/listings/import/columns` | canonical fields + synonyms |
| `GET` | `/api/listings/import/template?format=csv\|xlsx` | template download |
| `POST` | `/api/listings/:id/photos` | multipart photo batch (`files`) |
| `DELETE` | `/api/listings/:id/photos/:photoId` | remove a photo |
| `POST` | `/api/listings/:id/photos/:photoId/cover` | set the cover image |
| `GET` | `/api/media/*` | photo delivery (immutable, cached) |

Behaviour:

- `dry_run=true` returns counts, detected column mapping, per-row errors with
  spreadsheet row numbers, warnings and a five-row preview — **and writes
  nothing**.
- Partial imports: valid rows are stored, invalid rows are reported.
- Idempotent: re-uploading updates by address + postcode (per agent), so a
  corrected file does not create duplicates.
- Postcodes are geocoded via postcodes.io on commit (ward, district, lat/lon).
- Live listings carry `asking_price` / `listing_status`; sold imports carry
  `price_paid` / `date_sold` — the UI labels them "Asking" or "Sold".
- Storage: the Postgres `listings` table (migration 006) when `DATABASE_URL` is
  set, otherwise `data/agent_listings.json` for the demo. Uploaded listings are
  searchable immediately (address, town and description).

Auth: `X-API-Key: $AGENT_API_KEY` (required in production) plus `X-Agent-Id`
for attribution and per-agent scoping. Uploads are rate limited per agent.

UI: [`/agent/import`](http://localhost:3000/agent/import) — drag-and-drop or
paste, preview, then import.

## Listing photos

Agents upload photos per listing; the server validates, re-encodes and serves
derivatives.

- **Formats:** JPEG, PNG, WebP and HEIC/HEIF (iPhone photos). The declared
  content type and filename are ignored — the image is decoded and its real
  format checked.
- **Processing:** EXIF orientation is applied, then the image is re-encoded to
  WebP at two sizes (display ≤ 1600 px, thumb ≤ 480 px). Re-encoding **strips
  EXIF, including GPS coordinates**.
- **Limits:** 12 MB per photo, 10 files per request, 20 photos per listing,
  40 MB per request at the gateway. Images below 200×200 and above 30 MP are
  rejected; animated GIF/SVG are rejected.
- **Dedupe:** identical bytes are stored once per listing; re-uploading returns
  `added: 0`.
- **Cover photo:** the first photo becomes the cover; agents can change it.
  Deleting the cover promotes the next photo.
- **Storage:** `data/media/listings/<id>/<hash>-{display,thumb}.webp` in
  development (`MEDIA_ROOT` overrides). Filenames are content-hashed, so the
  media route serves them `immutable`.
- **Ownership:** uploads/deletes require the same agent as the listing; reads
  are public (marketing images).

The property page shows a gallery with thumbnails, cards use the cover
thumbnail, and `/agent/listings` manages photos (upload, set cover, remove).

> Note: deletion removes the file immediately, but any CDN/edge cache may keep
> a previously fetched copy until it expires. Treat photo takedown as eventual.

## Ask about this area (amenity Q&A)

On a property page, buyers can ask plain-English questions and get a
deterministic answer from OpenStreetMap data:

| Question | Answer (real demo data) |
|---|---|
| How far is the nearest Tesco superstore? | Tesco Extra, 1.3 miles (~27 min walk) |
| Nearest Tesco (any format) | Tesco Express, 1.2 miles |
| Nearest supermarket | ALDI, 0.4 miles (~8 min walk) |
| What gyms are nearby? | Bannatyne Health Club 0.6 miles, PureGym 1.2 miles, Crewe Lifestyle Centre 1.4 miles |
| Primary schools within 2 miles | Haslington Primary Academy 0.4 miles, … |
| Nearest train station | Crewe, 1.3 miles |

Distances are shown in UK imperial — yards under a tenth of a mile, then miles
to one decimal place, and whole miles without a decimal — while the JSON keeps
`distance_m` in metres for maps and routing. Walk times assume 3 mph.

How it works:

- `GET /api/property/:id/nearby?q=...` → `app/poi/query.py`.
- Intent parsing maps **brands** (`Tesco`, `Sainsbury's`, `M&S`, `PureGym`,
  `Boots`, `Costa`, …) and **categories** (`gym`, `pharmacy`, `primary school`,
  `park`, `station`, …) onto the OSM taxonomy.
- Candidates are filtered by radius (default 5 km, widened once to 15 km — shown
  to users as 3.1 miles or 9.3 miles), sorted by haversine distance, and rendered
  with a walk-time estimate.
- If a brand is absent, the answer falls back honestly: *“There is no Waitrose
  within 3.1 miles. The nearest supermarket is ALDI…”*.
- Gym questions prefer real `fitness_centre`s over cricket/football clubs;
  primary/secondary intent filters schools where the phase is known (ISCED).
- The **same lookup runs before the LLM in chat**, so “how far is the nearest
  Tesco?” works without an API key and can never hallucinate a distance.

Amenity coverage: supermarkets, convenience stores, gyms/leisure centres,
schools, nurseries, pharmacies, GP surgeries, dentists, hospitals, parks,
playgrounds, stations, cafés, restaurants, pubs and bars.

Caveats: distances are straight-line and walking time assumes 80 m/min; OSM
records locations, not quality (Ofsted grades are a separate source); opening
hours and store presence change. Data © OpenStreetMap contributors (ODbL) —
attributed in the API response and in the UI.

Refresh after changing the taxonomy: `python -m scripts.preload_pois`.

## API surface (gateway)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | liveness (no downstream calls) |
| `GET` | `/health/ready` | readiness (503 when a dependency is down) |
| `GET` | `/api/health` | aggregate status for the UI |
| `GET` | `/api/search?q=` | natural-language search (`min_beds`, `max_beds`, `max_price`, `property_type`, `location`, `outcode`, `limit`) |
| `POST` | `/api/parse` | `{ query }` → structured filters |
| `GET` | `/api/property/:id` | property detail |
| `POST` | `/api/ask/poi` | `{ lat, lon, category?, n? }` |
| `GET` | `/api/property/:id/nearby?q=` | amenity Q&A (“nearest Tesco?”) |
| `POST` | `/api/chat` | `{ messages, property_id? }` |
| `POST` | `/api/chat/stream` | SSE: `data: {"chunk": "…"}` … `data: [DONE]` |
| `POST` | `/api/auth/register` \| `/login` \| `/refresh` \| `/logout` | JWT (Bearer) |
| `GET` | `/api/auth/me` | requires Bearer token |
| `GET` | `/api/metrics` | Prometheus-style counters |
| `GET` | `/docs` | OpenAPI UI (non-production only) |

## Production checklist

- Rotate any credential that has ever been committed; see `docs/SECURITY-NOTICE.md`.
- Set `JWT_SECRET` (≥32 chars) and `CORS_ORIGIN` (explicit https origins).
- Set `AI_SERVICE_URL`, `DATABASE_URL` (Postgres + pgvector), and run
  `ai-service/migrations/*.sql`.
- Set `POI_INGEST_API_KEY`; leave `TRUST_PROXY=0` unless behind a trusted proxy.
- `DEMO_DATA` is ignored when `NODE_ENV=production`.
