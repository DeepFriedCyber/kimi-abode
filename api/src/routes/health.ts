/**
 * Health check routes — Service monitoring and status aggregation.
 */

import type { FastifyPluginCallback } from "fastify";
import { PropertyRepository } from "../db/property-repository";

interface HealthRoutesOptions {
  aiServiceUrl: string;
}

// ---- Types -------------------------------------------------------------------

interface ServiceHealth {
  name: string;
  status: "healthy" | "unhealthy" | "degraded";
  details?: Record<string, unknown>;
}

interface HealthResponse {
  timestamp: number;
  version: string;
  services: {
    database: ServiceHealth;
    ai_service: ServiceHealth;
  };
  status: "healthy" | "unhealthy";
}

// ---- Helper functions --------------------------------------------------------

/** Check AI service health by HTTP request */
async function checkAiServiceHealth(aiServiceUrl: string): Promise<ServiceHealth> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2000);
  try {
    const response = await fetch(`${aiServiceUrl}/health`, { signal: controller.signal });
    
    if (response.ok) {
      clearTimeout(timeoutId);
      return { name: "ai_service", status: "healthy" };
    } else {
      clearTimeout(timeoutId);
      console.warn("[HealthCheck] AI service returned non-OK status:", response.status);
      return { name: "ai_service", status: "degraded" };
    }
  } catch (err) {
    clearTimeout(timeoutId);
    const errorMsg = err instanceof Error ? err.message : "Unknown error";
    console.warn(`[HealthCheck] Cannot reach AI service at ${aiServiceUrl}: ${errorMsg}`);
    return { name: "ai_service", status: "degraded" };
  }
}

/** Check PostgreSQL or SQLite connectivity. */
async function checkDatabaseHealth(): Promise<ServiceHealth> {
  const repo = new PropertyRepository();
  
  // Try to get property count (non-invasive health check)
  try {
    const count = await repo.count();
    
    if (count > 0) {
      return {
        name: "database",
        status: "healthy",
        details: {
          property_count: count,
        },
      };
    } else {
      console.warn("[HealthCheck] Database connected but no properties found");
      return {
        name: "database",
        status: "degraded",
        details: {
          property_count: 0,
        },
      };
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : "Unknown error";
    console.warn(`[HealthCheck] Database health check failed: ${errorMsg}`);
    
    // Check if it's a connection error vs other error
    if (errorMsg.includes("ECONNREFUSED") || errorMsg.includes("connection")) {
      return { name: "database", status: "unhealthy" };
    }
    
    // Note: If connection attempt fails, we return unhealthy below
    return { name: "database", status: "unhealthy" };
  }
}

// ---- routes ------------------------------------------------------------------

export const healthRoutes: FastifyPluginCallback<HealthRoutesOptions> = async (app, opts) => {
  const aiServiceUrl = opts.aiServiceUrl;

  // ---- Aggregate health check endpoint ----------------------------------------

  /**
   * GET /health — Returns overall service status.
   * 
   * Response includes:
   * - timestamp: Unix timestamp in ms
   * - version: API server version
   * - services: Health status of each backend service
   * - status: "healthy" if all services pass, "unhealthy" otherwise
   */
  app.get<{ Querystring?: {} }>("/health", async () => {
    const timestamp = Date.now();
    
    // Check database connectivity
    const dbHealth = await checkDatabaseHealth();
    
    // Check AI service health
    const aiHealth = await checkAiServiceHealth(aiServiceUrl);
    
    const overallStatus = dbHealth.status === "healthy" && aiHealth.status === "healthy" 
      ? "healthy" 
      : "unhealthy";

    return {
      timestamp,
      version: "0.1.0",
      services: {
        database: dbHealth,
        ai_service: aiHealth,
      },
      status: overallStatus,
    } as HealthResponse;
  });

  /** Check only AI service health (for external monitoring). */
  app.get<{ Querystring?: {} }>("/health/ai", async () => {
    return {
      timestamp: Date.now(),
      version: "0.1.0",
      name: "ai_service",
      status: await new Promise<ServiceHealth>((resolve) => {
        const aiHealth = checkAiServiceHealth(aiServiceUrl);
        resolve(aiHealth);
      }),
    };
  });

  /** Check only database health (for external monitoring). */
  app.get<{ Querystring?: {} }>("/health/database", async () => {
    return {
      timestamp: Date.now(),
      version: "0.1.0",
      name: "database",
      status: await new Promise<ServiceHealth>((resolve) => {
        const dbHealth = checkDatabaseHealth();
        resolve(dbHealth);
      }),
      details: (await new Promise<ServiceHealth>(async (resolve) => {
        const dbHealth = await checkDatabaseHealth();
        resolve(dbHealth);
      })).details,
    };
  });
};