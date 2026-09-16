/**
 * Ask routes — POI queries, property location intelligence.
 */

import type { FastifyPluginCallback } from "fastify";


// ---- typed request bodies ---------------------------------------------------

interface SearchQuery {
  q?: string;
  min_beds?: string;
  max_price?: string;
  location?: string;
  outcode?: string;
  district?: string;
}

interface PoiBody {
  lat?: number;
  lon?: number;
  category?: string;
  radius?: number;
}

interface AskSearchBody {
  query?: string;
}


// ---- rate limiter (per-route) -----------------------------------------------

function createRouteLimiter(maxPerMinute: number): () => boolean {
  const entries: [number, number][] = []; // [timestamp, count]
  return function check(): boolean {
    const now = Date.now();
    // Remove expired entries
    while (entries.length > 0 && now - entries[0][0] > 60_000) {
      entries.shift();
    }
    if (entries.length === 0) {
      entries.push([now, 1]);
      return true;
    }
    const latest = entries[entries.length - 1];
    if (now - latest[0] > 60_000) {
      entries.push([now, 1]);
      return true;
    }
    if (latest[1] >= maxPerMinute) return false;
    latest[1]++;
    return true;
  };
}

const searchLimiter = createRouteLimiter(30);
const askSearchLimiter = createRouteLimiter(20);


// ---- routes -----------------------------------------------------------------

export const askRoutes: FastifyPluginCallback<string> = async (app, aiUrl) => {
  // Health check — no rate limit needed
  app.get("/ask/health", async () => ({ status: "ok" }));

  // GET /api/search — frontend search endpoint (proxy to AI service)
  app.get<{ Querystring: SearchQuery }>("/search", async (req, reply) => {
    const query = req.query as SearchQuery;

    if (!query.q || query.q.trim().length < 2) {
      return reply.code(400).send({ error: "q parameter must be at least 2 characters" });
    }

    // Rate limit to prevent API abuse
    if (!searchLimiter()) {
      return reply.code(429).send({ error: "too many search requests; try again later" });
    }

    const params = new URLSearchParams();
    params.set("query", query.q.trim());
    if (query.min_beds) params.set("min_beds", query.min_beds);
    if (query.max_price) params.set("max_price", query.max_price);
    if (query.location) params.set("location", query.location);
    if (query.outcode) params.set("outcode", query.outcode);
    if (query.district) params.set("district", query.district);

    try {
      const res = await fetch(`${aiUrl}/search?${params.toString()}`, { signal: AbortSignal.timeout(10_000) });
      if (!res.ok) return reply.code(502).send({ error: "AI service returned an error" });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });

  // POI query
  app.post<{ Body: PoiBody }>("/ask/poi", async (req, reply) => {
    const { lat, lon, category, radius }: PoiBody = req.body;

    if (lat == null || lon == null) {
      return reply.code(400).send({ error: "lat and lon are required" });
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      return reply.code(400).send({ error: "lat/lon out of valid range" });
    }

    const queryStr = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    if (category) queryStr.set("category", category);
    if (radius && radius > 0) queryStr.set("radius", String(radius));

    try {
      const res = await fetch(`${aiUrl}/poi/nearby?${queryStr}`, { signal: AbortSignal.timeout(5_000) });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });

  // Property search via AI service — uses parsed fields + DB filter
  app.post<{ Body: AskSearchBody }>("/ask/search", async (req, reply) => {
    const { query }: AskSearchBody = req.body;

    if (!query || query.trim().length < 2) {
      return reply.code(400).send({ error: "query must be at least 2 characters" });
    }

    // Rate limit to prevent abuse (this is a double-hop request, costs more)
    if (!askSearchLimiter()) {
      return reply.code(429).send({ error: "too many ask/search requests; try again later" });
    }

    try {
      // Parse first to get structured fields (tier, beds, price, location)
      const parseRes = await fetch(`${aiUrl}/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
        signal: AbortSignal.timeout(5_000),
      });

      if (!parseRes.ok) {
        return reply.code(502).send({ error: "AI parse service failed" });
      }

      const parsed = (await parseRes.json()) as Record<string, unknown>;

      // Now do the actual search with those fields
      const params = new URLSearchParams();
      params.set("query", query);
      if (parsed.min_beds) params.set("min_beds", String(parsed.min_beds));
      if (parsed.max_price) params.set("max_price", String(parsed.max_price));
      if (parsed.location) params.set("location", parsed.location);
      if (parsed.outcode) params.set("outcode", parsed.outcode);
      if (parsed.district) params.set("district", parsed.district);

      const types = parsed.property_types;
      if (Array.isArray(types)) {
        for (const t of types) {
          params.append("types", String(t));
        }
      }

      const res = await fetch(`${aiUrl}/search?${params.toString()}`, { signal: AbortSignal.timeout(10_000) });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });
};
