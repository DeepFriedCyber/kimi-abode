/**
 * Health endpoints.
 *
 * - GET /health            liveness only (no downstream calls)
 * - GET /health/ready      readiness (database + AI service)
 * - GET /api/health        aggregate status for the frontend
 * - GET /health/ai         AI service only
 * - GET /health/database   property store only
 */

import type { FastifyPluginAsync } from "fastify";
import { propertyRepository } from "../db/property-repository";
import { config } from "../config";

export interface HealthRoutesOptions {
  aiServiceUrl: string;
}

type Status = "healthy" | "degraded" | "unhealthy";

interface ServiceHealth {
  name: string;
  status: Status;
  details?: Record<string, unknown>;
}

const startedAt = Date.now();

async function checkDatabase(): Promise<ServiceHealth> {
  try {
    const count = await propertyRepository.count();
    return {
      name: "database",
      status: "healthy",
      details: { property_count: count, driver: propertyRepository.driver },
    };
  } catch (error) {
    return {
      name: "database",
      status: "unhealthy",
      details: { error: error instanceof Error ? error.message : "unknown" },
    };
  }
}

async function checkAiService(aiServiceUrl: string): Promise<ServiceHealth> {
  try {
    const response = await fetch(`${aiServiceUrl}/health`, {
      signal: AbortSignal.timeout(2_000),
    });
    return {
      name: "ai_service",
      status: response.ok ? "healthy" : "degraded",
      details: { http_status: response.status },
    };
  } catch {
    return { name: "ai_service", status: "degraded" };
  }
}

function aggregate(db: ServiceHealth, ai: ServiceHealth): { status: Status; services: Record<string, ServiceHealth> } {
  const status: Status =
    db.status === "healthy" && ai.status === "healthy"
      ? "healthy"
      : db.status === "unhealthy"
        ? "unhealthy"
        : "degraded";

  return {
    status,
    services: { database: db, ai_service: ai },
  };
}

export const healthRoutes: FastifyPluginAsync<HealthRoutesOptions> = async (app, opts) => {
  const aiServiceUrl = opts.aiServiceUrl;

  app.get("/health", async () => ({
    status: "ok",
    version: config.version,
    uptime_seconds: Math.round((Date.now() - startedAt) / 1000),
    timestamp: new Date().toISOString(),
  }));

  const aggregateHandler = async () => {
    const [db, ai] = await Promise.all([checkDatabase(), checkAiService(aiServiceUrl)]);
    return {
      ...aggregate(db, ai),
      version: config.version,
      timestamp: new Date().toISOString(),
    };
  };

  // Readiness probe: 503 when a dependency is unhealthy.
  app.get("/health/ready", async (_request, reply) => {
    const [db, ai] = await Promise.all([checkDatabase(), checkAiService(aiServiceUrl)]);
    const result = aggregate(db, ai);
    return reply.code(result.status === "unhealthy" ? 503 : 200).send(result);
  });

  // Frontend-facing aggregate (always 200 so the UI can show a partial state).
  app.get("/api/health", aggregateHandler);
  app.get("/health/status", aggregateHandler);

  app.get("/health/ai", async () => checkAiService(aiServiceUrl));

  app.get("/health/database", async () => checkDatabase());
};

export default healthRoutes;
