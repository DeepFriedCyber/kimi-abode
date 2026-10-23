/**
 * Application smoke tests: boot, liveness, 404 shape, metrics.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildApp } from "../src/app";

describe("app", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = await buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it("boots and reports liveness without touching dependencies", async () => {
    const response = await app.inject({ method: "GET", url: "/health" });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ status: "ok" });
  });

  it("returns a JSON 404 for unknown routes", async () => {
    const response = await app.inject({ method: "GET", url: "/nope" });

    expect(response.statusCode).toBe(404);
    expect(response.json().error).toBe("Not found");
    expect(response.json().correlation_id).toBeTruthy();
  });

  it("exposes metrics as text", async () => {
    await app.inject({ method: "GET", url: "/health" });
    const response = await app.inject({ method: "GET", url: "/api/metrics" });

    expect(response.statusCode).toBe(200);
    expect(response.headers["content-type"]).toContain("text/plain");
    expect(response.body).toContain("abode_http_");
  });

  it("reports aggregate health for the frontend", async () => {
    const response = await app.inject({ method: "GET", url: "/api/health" });

    expect(response.statusCode).toBe(200);
    expect(response.json().services).toHaveProperty("database");
    expect(response.json().services).toHaveProperty("ai_service");
  });
});
