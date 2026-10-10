import fastify from "fastify";
import { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";

// ---- routes -----------------------------------------------------------------

export const askRoutes = async (app: FastifyInstance, opts: any) => {
  const aiUrl = opts.aiUrl;

  // Proxy to AI service parse endpoint (for frontend /api/parse)
  app.post("/parse", async function (req, reply) {
    try {
      const res = await fetch(`${aiUrl}/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req.body),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) return reply.code(502).send({ error: "AI parse service failed" });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });

  // Proxy to AI service chat endpoint (for frontend /api/chat)
  app.post("/chat", async function (req, reply) {
    try {
      const res = await fetch(`${aiUrl}/chat/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req.body),
        signal: AbortSignal.timeout(10000),
      });
      if (!res.ok) return reply.code(502).send({ error: "AI chat service failed" });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });

  // GET /api/search — frontend search endpoint (proxy to AI service)
  app.get("/search", async function (req, reply) {
    const query = req.query as Record<string, unknown>;

    if (!query.q || typeof query.q !== "string" || query.q.trim().length < 2) {
      return reply.code(400).send({ error: "q parameter must be at least 2 characters" });
    }

    const params = new URLSearchParams();
    params.set("query", String(query.q).trim());
    if (typeof query.min_beds === "number") params.set("min_beds", String(query.min_beds));
    if (typeof query.max_price === "number") params.set("max_price", String(query.max_price));
    if (typeof query.location === "string") params.set("location", query.location);
    if (typeof query.outcode === "string") params.set("outcode", query.outcode);
    if (typeof query.district === "string") params.set("district", query.district);

    try {
      const res = await fetch(`${aiUrl}/search?${params.toString()}`, { signal: AbortSignal.timeout(10_000) });
      if (!res.ok) return reply.code(502).send({ error: "AI service returned an error" });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });

  // POI query
  app.post("/ask/poi", async function (req, reply) {
    const body = req.body as Record<string, unknown>;

    const lat = Number(body.lat);
    const lon = Number(body.lon);

    if (Number.isNaN(lat) || Number.isNaN(lon)) {
      return reply.code(400).send({ error: "lat and lon are required" });
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
        return reply.code(400).send({ error: "lat/lon out of valid range" });
    }

    const queryStr = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    if (typeof body.category === "string") queryStr.set("category", String(body.category));
    if (typeof body.radius === "number" && body.radius > 0) queryStr.set("radius", String(body.radius));
    if (typeof body.n === "number" && body.n > 0) queryStr.set("n", String(body.n));

    try {
      const res = await fetch(`${aiUrl}/poi/nearby?${queryStr}`, { signal: AbortSignal.timeout(5_000) });
      if (!res.ok) return reply.code(502).send({ error: "AI service returned an error" });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });

  // Property search via AI service — uses parsed fields + DB filter
  app.post("/ask/search", async function (req, reply) {
    const body = req.body as Record<string, unknown>;
    const query = typeof body.query === "string" ? body.query : String(body.query);

    if (!query || query.trim().length < 2) {
      return reply.code(400).send({ error: "query must be at least 2 characters" });
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
      if (typeof parsed.min_beds === "number") params.set("min_beds", String(parsed.min_beds));
      if (typeof parsed.max_price === "number") params.set("max_price", String(parsed.max_price));
      if (typeof parsed.location === "string") params.set("location", parsed.location);
      if (typeof parsed.outcode === "string") params.set("outcode", parsed.outcode);
      if (typeof parsed.district === "string") params.set("district", parsed.district);

      const types = parsed.property_types;
      if (Array.isArray(types)) {
        for (const t of types) {
          if (typeof t === "string") params.append("types", t);
        }
      }

      const res = await fetch(`${aiUrl}/search?${params.toString()}`, { signal: AbortSignal.timeout(10_000) });
      if (!res.ok) return reply.code(502).send({ error: "AI service returned an error" });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });

  // GET /api/property/:id — fetch a single property by ID
  app.get("/property/:id", async function (req: any, reply) {
    const id = parseInt((req as any).params?.id || "0", 10);
    if (isNaN(id) || id < 0) {
      return reply.code(400).send({ error: "Invalid property id" });
    }

    try {
      const params = new URLSearchParams({ id: String(id) });
      const res = await fetch(`${aiUrl}/property?${params.toString()}`, { signal: AbortSignal.timeout(5_000) });
      if (!res.ok) return reply.code(502).send({ error: "AI service returned an error" });
      return res.json();
    } catch {
      return reply.code(502).send({ error: "AI service unavailable" });
    }
  });
};