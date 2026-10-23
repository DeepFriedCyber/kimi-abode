/**
 * Agent listing upload routes — proxies to the AI service's /listings API.
 *
 * Multipart bodies are forwarded byte-for-byte; the AI service owns parsing,
 * validation and persistence. Agent credentials are forwarded, not inspected.
 */

import type { FastifyPluginAsync, FastifyRequest } from "fastify";
import { config } from "../config";
import { forwardBinary, forwardJson } from "../lib/upstream";

export interface ListingRoutesOptions {
  aiUrl: string;
}

const agentHeaders = (request: FastifyRequest): Record<string, string> => {
  const headers: Record<string, string> = {};
  const apiKey = request.headers["x-api-key"];
  const agentId = request.headers["x-agent-id"];
  if (typeof apiKey === "string") headers["x-api-key"] = apiKey;
  if (typeof agentId === "string") headers["x-agent-id"] = agentId;
  return headers;
};

const listQuerySchema = {
  querystring: {
    type: "object",
    additionalProperties: false,
    properties: {
      limit: { type: "integer", minimum: 1, maximum: 200, default: 50 },
      offset: { type: "integer", minimum: 0, default: 0 },
      agent_id: { type: "string", maxLength: 64 },
    },
  },
} as const;

export const listingRoutes: FastifyPluginAsync<ListingRoutesOptions> = async (app, opts) => {
  const aiUrl = opts.aiUrl.replace(/\/+$/, "");

  /** POST /api/listings/import — multipart upload (CSV/XLSX/JSON/XML/TXT). */
  app.post(
    "/listings/import",
    { bodyLimit: config.uploadLimitBytes },
    async (request, reply) => {
      const contentType = request.headers["content-type"] ?? "";
      if (!contentType.includes("multipart/form-data")) {
        return reply.code(415).send({ error: "multipart/form-data is required" });
      }

      return forwardJson(
        request,
        reply,
        `${aiUrl}/listings/import`,
        {
          method: "POST",
          headers: { "Content-Type": contentType, ...agentHeaders(request) },
          body: new Uint8Array(request.body as Buffer),
        },
        config.uploadTimeoutMs,
      );
    },
  );

  /** POST /api/listings — single canonical listing (CRM integrations). */
  const createListing = async (request: FastifyRequest, reply: any) => {
    return forwardJson(
      request,
      reply,
      `${aiUrl}/listings/`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", ...agentHeaders(request) },
        body: JSON.stringify(request.body ?? {}),
      },
      config.uploadTimeoutMs,
    );
  };
  app.post("/listings", {}, createListing);
  app.post("/listings/", {}, createListing);

  /** POST /api/listings/import/text — paste an email/description. */
  app.post("/listings/import/text", {}, async (request, reply) => {
    return forwardJson(
      request,
      reply,
      `${aiUrl}/listings/import/text`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", ...agentHeaders(request) },
        body: JSON.stringify(request.body ?? {}),
      },
      config.uploadTimeoutMs,
    );
  });

  /** GET /api/listings/import/columns — accepted columns and synonyms. */
  app.get("/listings/import/columns", {}, async (request, reply) => {
    return forwardJson(request, reply, `${aiUrl}/listings/import/columns`, {
      headers: agentHeaders(request),
    });
  });

  /** GET /api/listings/import/template?format=csv|xlsx */
  app.get(
    "/listings/import/template",
    {
      schema: {
        querystring: {
          type: "object",
          additionalProperties: false,
          properties: { format: { type: "string", enum: ["csv", "xlsx"], default: "csv" } },
        },
      },
    },
    async (request, reply) => {
      const { format } = request.query as { format: string };
      return forwardBinary(
        request,
        reply,
        `${aiUrl}/listings/import/template?format=${encodeURIComponent(format)}`,
        { headers: agentHeaders(request) },
      );
    },
  );

  /** GET /api/listings — uploaded listings (demo store). */  const listListings = async (request: FastifyRequest, reply: any) => {
    const query = request.query as {
      limit: number;
      offset: number;
      agent_id?: string;
    };
    const params = new URLSearchParams({
      limit: String(query.limit),
      offset: String(query.offset),
    });
    if (query.agent_id) params.set("agent_id", query.agent_id);

    return forwardJson(request, reply, `${aiUrl}/listings/?${params.toString()}`, {
      headers: agentHeaders(request),
    });
  };
  app.get("/listings", { schema: listQuerySchema }, listListings);
  app.get("/listings/", { schema: listQuerySchema }, listListings);

  // ---- photos -------------------------------------------------------------

  const listingParamsSchema = {
    params: {
      type: "object",
      required: ["id"],
      properties: { id: { type: "integer", minimum: 1 } },
    },
  } as const;

  const photoParamsSchema = {
    params: {
      type: "object",
      required: ["id", "photoId"],
      properties: {
        id: { type: "integer", minimum: 1 },
        photoId: { type: "string", pattern: "^[a-f0-9]{16}$" },
      },
    },
  } as const;

  /** POST /api/listings/:id/photos — multipart photo batch. */
  app.post(
    "/listings/:id/photos",
    { schema: listingParamsSchema, bodyLimit: config.photoLimitBytes },
    async (request, reply) => {
      const contentType = request.headers["content-type"] ?? "";
      if (!contentType.includes("multipart/form-data")) {
        return reply.code(415).send({ error: "multipart/form-data is required" });
      }

      const { id } = request.params as { id: number };
      return forwardJson(
        request,
        reply,
        `${aiUrl}/listings/${id}/photos`,
        {
          method: "POST",
          headers: { "Content-Type": contentType, ...agentHeaders(request) },
          body: new Uint8Array(request.body as Buffer),
        },
        config.uploadTimeoutMs,
      );
    },
  );

  /** DELETE /api/listings/:id/photos/:photoId */
  app.delete(
    "/listings/:id/photos/:photoId",
    { schema: photoParamsSchema },
    async (request, reply) => {
      const { id, photoId } = request.params as { id: number; photoId: string };
      return forwardJson(
        request,
        reply,
        `${aiUrl}/listings/${id}/photos/${photoId}`,
        { method: "DELETE", headers: agentHeaders(request) },
      );
    },
  );

  /** POST /api/listings/:id/photos/:photoId/cover */
  app.post(
    "/listings/:id/photos/:photoId/cover",
    { schema: photoParamsSchema },
    async (request, reply) => {
      const { id, photoId } = request.params as { id: number; photoId: string };
      return forwardJson(
        request,
        reply,
        `${aiUrl}/listings/${id}/photos/${photoId}/cover`,
        { method: "POST", headers: agentHeaders(request) },
      );
    },
  );

  /**
   * GET /api/media/* — images proxied from the AI service.
   *
   * Content-hashed filenames mean these are immutable; cache headers are
   * forwarded from upstream.
   */
  app.get("/media/*", async (request, reply) => {
    const relative = request.url.replace(/^\/api/, "");
    return forwardBinary(request, reply, `${aiUrl}${relative}`);
  });
};

export default listingRoutes;
