/**
 * Fastify application builder.
 *
 * This module is intentionally small: plugins, cross-cutting hooks, error
 * handling and route registration. Route behaviour lives in ./routes.
 */

import Fastify, { type FastifyInstance } from "fastify";
import cors from "@fastify/cors";
import jwt from "@fastify/jwt";
import fastifySwagger from "@fastify/swagger";
import fastifySwaggerUi from "@fastify/swagger-ui";
import { config } from "./config";
import { authRoutes } from "./routes/auth";
import { askRoutes } from "./routes/ask";
import { healthRoutes } from "./routes/health";
import { listingRoutes } from "./routes/listings";
import { Metrics, metricsHook, registerMetricsPlugin } from "./observability/metrics";

export async function buildApp(): Promise<FastifyInstance> {
  const app = Fastify({
    logger:
      config.nodeEnv === "test"
        ? false
        : {
            level: process.env.LOG_LEVEL ?? "info",
            redact: {
              paths: [
                "req.headers.authorization",
                "req.headers.cookie",
                "req.headers['x-api-key']",
              ],
              censor: "[REDACTED]",
            },
          },
    trustProxy: config.trustProxy,
    bodyLimit: config.bodyLimit,
    requestIdHeader: "x-request-id",
  });

  // ---- plugins ------------------------------------------------------------
  await app.register(cors, {
    origin: config.corsOrigins,
    credentials: true,
    methods: ["GET", "POST", "OPTIONS"],
    allowedHeaders: [
      "Content-Type",
      "Authorization",
      "x-api-key",
      "x-agent-id",
      "x-request-id",
    ],
    maxAge: 86_400,
  });

  // Multipart bodies are forwarded to the AI service untouched. Registering a
  // buffer parser here avoids buffering/rebuilding the form in the gateway.
  app.addContentTypeParser(
    "multipart/form-data",
    { parseAs: "buffer", bodyLimit: config.photoLimitBytes },
    (_request, body, done) => done(null, body),
  );

  await app.register(jwt, {
    secret: config.jwt.secret,
    sign: {
      expiresIn: config.jwt.expiresIn,
      iss: config.jwt.issuer,
      aud: config.jwt.audience,
    },
    verify: {
      allowedIss: config.jwt.issuer,
      allowedAud: config.jwt.audience,
    },
  });

  // ---- API documentation --------------------------------------------------
  await app.register(fastifySwagger, {
    openapi: {
      openapi: "3.0.3",
      info: {
        title: "Abode API",
        description:
          "Gateway for property search, query parsing, POI intelligence and chat.",
        version: config.version,
      },
      servers: [{ url: process.env.API_URL ?? `http://localhost:${config.port}` }],
      components: {
        securitySchemes: {
          BearerAuth: { type: "http", scheme: "bearer", bearerFormat: "JWT" },
        },
      },
    },
  });

  if (!config.isProduction) {
    await app.register(fastifySwaggerUi, {
      routePrefix: "/docs",
      uiConfig: { docExpansion: "list", deepLinking: true },
    });
  }

  // ---- observability ------------------------------------------------------
  const metrics = new Metrics();
  app.addHook("onResponse", metricsHook(metrics));
  registerMetricsPlugin(app, metrics);

  // ---- error handling -----------------------------------------------------
  // Must be registered BEFORE route plugins: Fastify snapshots the current
  // error/not-found handlers into each encapsulated plugin context.
  app.setNotFoundHandler((request, reply) => {
    return reply.code(404).send({
      error: "Not found",
      correlation_id: request.id,
    });
  });

  app.setErrorHandler((error, request, reply) => {
    // Fastify/AJV validation errors are safe to surface (they describe the
    // request, not the system).
    if (error.validation) {
      return reply.code(error.statusCode ?? 400).send({
        error: "Invalid request",
        details: error.validation.map((issue) => ({
          path: issue.instancePath || issue.params?.missingProperty || issue.schemaPath,
          message: issue.message,
        })),
        correlation_id: request.id,
      });
    }

    const statusCode = error.statusCode && error.statusCode >= 400 ? error.statusCode : 500;

    if (statusCode >= 500) {
      request.log.error({ err: error }, "Unhandled request error");
      return reply.code(500).send({
        error: "Internal server error",
        correlation_id: request.id,
      });
    }

    return reply.code(statusCode).send({ error: error.message, correlation_id: request.id });
  });

  // ---- routes -------------------------------------------------------------
  await app.register(healthRoutes, { aiServiceUrl: config.aiServiceUrl });
  await app.register(authRoutes, { prefix: "/api" });
  await app.register(askRoutes, { prefix: "/api", aiUrl: config.aiServiceUrl });
  await app.register(listingRoutes, { prefix: "/api", aiUrl: config.aiServiceUrl });

  return app;
}

export default buildApp;
