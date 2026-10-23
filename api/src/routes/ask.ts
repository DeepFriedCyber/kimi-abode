/**
 * API gateway routes — a thin, typed proxy in front of the Python AI service.
 *
 * Responsibilities: validate/coerce input, enforce timeouts and body limits,
 * normalise errors, and never leak upstream detail to clients.
 */

import type { FastifyPluginAsync, FastifyReply, FastifyRequest } from "fastify";
import { callUpstream, fail, forwardJson, readJson } from "../lib/upstream";

export interface AskRoutesOptions {
  aiUrl: string;
}

const idParamsSchema = {
  params: {
    type: "object",
    required: ["id"],
    properties: { id: { type: "integer", minimum: 1 } },
  },
} as const;

const searchQuerySchema = {
  querystring: {
    type: "object",
    required: ["q"],
    additionalProperties: false,
    properties: {
      q: { type: "string", minLength: 1, maxLength: 500 },
      min_beds: { type: "integer", minimum: 0, maximum: 20 },
      max_price: { type: "number", minimum: 0 },
      property_type: { type: "string", maxLength: 40 },
      location: { type: "string", maxLength: 120 },
      outcode: { type: "string", maxLength: 8 },
      district: { type: "string", maxLength: 120 },
      limit: { type: "integer", minimum: 1, maximum: 100, default: 50 },
    },
  },
} as const;

const parseBodySchema = {
  body: {
    type: "object",
    required: ["query"],
    additionalProperties: false,
    properties: { query: { type: "string", minLength: 1, maxLength: 500 } },
  },
} as const;

const poiBodySchema = {
  body: {
    type: "object",
    required: ["lat", "lon"],
    additionalProperties: false,
    properties: {
      lat: { type: "number", minimum: -90, maximum: 90 },
      lon: { type: "number", minimum: -180, maximum: 180 },
      category: { type: "string", maxLength: 40 },
      radius: { type: "number", exclusiveMinimum: 0, maximum: 50_000 },
      n: { type: "integer", minimum: 1, maximum: 50, default: 5 },
    },
  },
} as const;

const chatMessageSchema = {
  type: "object",
  required: ["role", "content"],
  additionalProperties: false,
  properties: {
    role: { type: "string", enum: ["user", "assistant"] },
    content: { type: "string", minLength: 1, maxLength: 4_000 },
  },
} as const;

const chatBodySchema = {
  body: {
    type: "object",
    required: ["messages"],
    additionalProperties: false,
    properties: {
      messages: { type: "array", minItems: 1, maxItems: 50, items: chatMessageSchema },
      property_id: { type: "integer", minimum: 1 },
    },
  },
} as const;

export const askRoutes: FastifyPluginAsync<AskRoutesOptions> = async (app, opts) => {
  const aiUrl = opts.aiUrl.replace(/\/+$/, "");

  /** GET /api/search — natural-language property search. */
  app.get("/search", { schema: searchQuerySchema }, async (request, reply) => {
    const query = request.query as {
      q: string;
      min_beds?: number;
      max_price?: number;
      property_type?: string;
      location?: string;
      outcode?: string;
      district?: string;
      limit: number;
    };

    const params = new URLSearchParams({
      query: query.q.trim(),
      limit: String(query.limit),
    });
    if (query.min_beds !== undefined) params.set("min_beds", String(query.min_beds));
    if (query.max_price !== undefined) params.set("max_price", String(query.max_price));
    if (query.location) params.set("location", query.location.trim());
    if (query.outcode) params.set("outcode", query.outcode.trim());
    if (query.district) params.set("district", query.district.trim());
    if (query.property_type) params.append("property_types", query.property_type.trim());

    return forwardJson(request, reply, `${aiUrl}/search?${params.toString()}`);
  });

  /** POST /api/parse — structured query parsing. */
  app.post("/parse", { schema: parseBodySchema }, async (request, reply) => {
    const body = request.body as { query: string };
    return forwardJson(request, reply, `${aiUrl}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: body.query }),
    });
  });

  /** GET /api/property/:id */
  app.get("/property/:id", { schema: idParamsSchema }, async (request, reply) => {
    const { id } = request.params as { id: number };

    const result = await callUpstream(request, `${aiUrl}/property?id=${id}`);
    if (!result.ok) return fail(reply, request, result.failure);

    const { response } = result;
    const data = await readJson(response);

    if (response.status === 404) {
      return reply.code(404).send({ error: "Property not found" });
    }
    if (response.status === 503) {
      return fail(reply, request, { reason: "not_ready" });
    }
    if (!response.ok || data === null || typeof data !== "object" || data === null) {
      return fail(reply, request, {
        reason: response.ok ? "bad_response" : "unavailable",
      });
    }
    // The AI service signals "not found" with a 200 + {error} payload.
    if ("error" in data) {
      return reply.code(404).send({ error: "Property not found" });
    }

    return reply.send(data);
  });

  /** POST /api/ask/poi — amenities near a coordinate. */
  /** GET /api/property/:id/nearby — "how far is the nearest Tesco?" */
  app.get(
    "/property/:id/nearby",
    {
      schema: {
        params: {
          type: "object",
          required: ["id"],
          properties: { id: { type: "integer", minimum: 1 } },
        },
        querystring: {
          type: "object",
          required: ["q"],
          additionalProperties: false,
          properties: { q: { type: "string", minLength: 2, maxLength: 200 } },
        },
      },
    },
    async (request, reply) => {
      const { id } = request.params as { id: number };
      const { q } = request.query as { q: string };

      const result = await callUpstream(
        request,
        `${aiUrl}/property/${id}/nearby?q=${encodeURIComponent(q)}`,
      );
      if (!result.ok) return fail(reply, request, result.failure);

      const { response } = result;
      const data = await readJson(response);

      // These are deliberately user-facing (404 / "only amenity questions").
      if ((response.status === 404 || response.status === 422) && data !== null) {
        return reply.code(response.status).send(data);
      }
      if (!response.ok || data === null) {
        return fail(reply, request, {
          reason: response.status === 503 ? "not_ready" : "unavailable",
        });
      }

      return reply.send(data);
    },
  );

  app.post("/ask/poi", { schema: poiBodySchema }, async (request, reply) => {
    const body = request.body as {
      lat: number;
      lon: number;
      category?: string;
      radius?: number;
      n: number;
    };

    const params = new URLSearchParams({
      lat: String(body.lat),
      lon: String(body.lon),
      n: String(body.n),
    });
    if (body.category) params.set("category", body.category);
    if (body.radius !== undefined) params.set("radius", String(body.radius));

    return forwardJson(request, reply, `${aiUrl}/poi/nearby?${params.toString()}`);
  });

  /** POST /api/chat — blocking chat completion. */
  app.post("/chat", { schema: chatBodySchema }, async (request, reply) => {
    return forwardJson(request, reply, `${aiUrl}/chat/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request.body),
    });
  });

  /**
   * POST /api/chat/stream — Server-Sent Events passthrough.
   *
   * The upstream contract is `data: {"chunk": "..."}\n\n` terminated by
   * `data: [DONE]\n\n`; bytes are forwarded unchanged so the client sees
   * tokens as the model produces them.
   */
  app.post("/chat/stream", { schema: chatBodySchema }, async (request, reply) => {
    const result = await callUpstream(request, `${aiUrl}/chat/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(request.body),
    });
    if (!result.ok) return fail(reply, request, result.failure);
    if (!result.response.ok || !result.response.body) {
      return fail(reply, request, { reason: "unavailable" });
    }

    reply.hijack();
    reply.raw.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });

    const reader = result.response.body.getReader();
    let closed = false;
    reply.raw.on("close", () => {
      closed = true;
      void reader.cancel().catch(() => undefined);
    });

    try {
      while (!closed) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) reply.raw.write(Buffer.from(value));
      }
    } catch (error) {
      request.log.warn({ err: error }, "Chat stream interrupted");
    } finally {
      if (!closed) reply.raw.end();
    }
  });
};

export default askRoutes;
