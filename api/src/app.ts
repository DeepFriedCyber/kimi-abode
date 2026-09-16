/**
 * Fastify application builder — assembles all plugins, routes, and hooks.
 */

import { FastifyInstance, FastifyPluginCallback } from "fastify";
import cors from "@fastify/cors";
import jwt from "@fastify/jwt";
import { config } from "./config";
import { authRoutes } from "./routes/auth";
import { askRoutes } from "./routes/ask";
import { PgUserStore, InMemoryUserStore } from "./services/user-store";


// ---- request counters (Prometheus-compatible) ------------------------------
const _requestCounts = new Map<string, number>();
const _incrementInterval = setInterval(() => {
  // Periodic GC: keep only recent counts for rendering
}, 60_000);

function incMetric(name: string): void {
  _requestCounts.set(name, (_requestCounts.get(name) ?? 0) + 1);
}


export async function buildApp(): Promise<FastifyInstance> {
  const Fastify = (await import("fastify")).default;
  const app = Fastify({
    logger: config.nodeEnv !== "test",
    trustProxy: true,
  });

  // ---- JWT secret validation (HS256 requires ≥32 chars / 256 bits) ----------
  const jwtSecret = process.env.JWT_SECRET;
  if (!jwtSecret || jwtSecret.length < 32) {
    throw new Error(
      "JWT_SECRET must be set and at least 32 characters long (recommended for HS256)",
    );
  }

  // ---- Plugins ---------------------------------------------------------------
  await app.register(cors, { origin: config.corsOrigin });
  await app.register(jwt, { secret: process.env.JWT_SECRET });

  // ---- Request metrics hook (Prometheus format) -----------------------------
  app.addHook("onResponse", async (request, reply) => {
    const key = `${request.method} ${request.url.split("?")[0]}`;
    incMetric(key);
  });

  app.get("/metrics", async (_req, reply) => {
    let body = "# HELP abode_http_requests_total Total HTTP requests\n";
    body += "# TYPE abode_http_requests_total counter\n";
    for (const [key, count] of _requestCounts) {
      body += `abode_http_requests_total{method="${key}"} ${count}\n`;
    }
    return reply.type("text/plain; version=0.0.4").send(body);
  });

  // ---- Auth routes (require DATABASE_URL) -----------------------------------
  if (config.databaseUrl) {
    await app.register(authRoutes, {
      store: new PgUserStore(config.databaseUrl),
      signAccess: (sub: string) => app.jwt.sign({ sub }, { expiresIn: "15m" }),
      verifyAccess: async (token: string): Promise<{ sub: string } | null> => {
        try {
          const decoded = await app.jwt.verify(token);
          return decoded as { sub: string };
        } catch {
          return null;
        }
      },
    }, { prefix: "/api" });
  } else {
    // Fallback to in-memory store for dev without DB
    await app.register(authRoutes, {
      store: new InMemoryUserStore(),
      signAccess: (sub: string) => app.jwt.sign({ sub }, { expiresIn: "15m" }),
      verifyAccess: async (token: string): Promise<{ sub: string } | null> => {
        try {
          const decoded = await app.jwt.verify(token);
          return decoded as { sub: string };
        } catch {
          return null;
        }
      },
    }, { prefix: "/api" });
  }

  // ---- POI / Ask routes ----------------------------------------------------
  await app.register(askRoutes, config.aiServiceUrl, { prefix: "/api" });

  return app;
}
