/**
 * Gateway route tests. The upstream AI service is stubbed via global fetch.
 */

import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildApp } from "../src/app";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("ask routes", () => {
  let app: FastifyInstance;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeAll(async () => {
    app = await buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires a q parameter", async () => {
    const response = await app.inject({ method: "GET", url: "/api/search" });
    expect(response.statusCode).toBe(400);
    expect(response.json().error).toBe("Invalid request");
  });

  it("coerces numeric filters and forwards them to the AI service", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ properties: [], total_matches: 0 }));

    const response = await app.inject({
      method: "GET",
      url: "/api/search?q=detached&min_beds=3&max_price=350000&property_type=detached",
    });

    expect(response.statusCode).toBe(200);
    const calledUrl = new URL(fetchMock.mock.calls[0][0] as string);
    expect(calledUrl.pathname).toBe("/search");
    expect(calledUrl.searchParams.get("query")).toBe("detached");
    expect(calledUrl.searchParams.get("min_beds")).toBe("3");
    expect(calledUrl.searchParams.get("max_price")).toBe("350000");
    expect(calledUrl.searchParams.get("property_types")).toBe("detached");
    expect(calledUrl.searchParams.get("limit")).toBe("50");
  });

  it("maps an upstream error to 502 without leaking detail", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "secret internal detail" }, 500));

    const response = await app.inject({ method: "GET", url: "/api/search?q=test" });

    expect(response.statusCode).toBe(502);
    expect(response.json().error).toMatch(/unavailable/i);
    expect(JSON.stringify(response.json())).not.toContain("secret internal detail");
  });

  it("returns 504 on upstream timeout", async () => {
    const timeout = new Error("timed out");
    timeout.name = "TimeoutError";
    fetchMock.mockRejectedValue(timeout);

    const response = await app.inject({ method: "GET", url: "/api/search?q=test" });

    expect(response.statusCode).toBe(504);
  });

  it("validates POI coordinates", async () => {
    const response = await app.inject({
      method: "POST",
      url: "/api/ask/poi",
      payload: { lat: 95, lon: 0 },
    });

    expect(response.statusCode).toBe(400);
  });

  it("forwards POI requests", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ nearby: [] }));

    const response = await app.inject({
      method: "POST",
      url: "/api/ask/poi",
      payload: { lat: 53.14, lon: -2.36, n: 3 },
    });

    expect(response.statusCode).toBe(200);
    const calledUrl = new URL(fetchMock.mock.calls[0][0] as string);
    expect(calledUrl.pathname).toBe("/poi/nearby");
    expect(calledUrl.searchParams.get("lat")).toBe("53.14");
    expect(calledUrl.searchParams.get("n")).toBe("3");
  });

  it("rejects a non-numeric property id", async () => {
    const response = await app.inject({ method: "GET", url: "/api/property/abc" });
    expect(response.statusCode).toBe(400);
  });

  it("maps an upstream 'not found' payload to 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "Property not found" }));

    const response = await app.inject({ method: "GET", url: "/api/property/42" });
    expect(response.statusCode).toBe(404);
  });

  it("forwards an area question for a property", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ answer: "The nearest supermarket is ALDI", results: [] }),
    );

    const response = await app.inject({
      method: "GET",
      url: "/api/property/1/nearby?q=nearest%20supermarket",
    });

    expect(response.statusCode).toBe(200);
    expect(response.json().answer).toContain("ALDI");
    const calledUrl = new URL(fetchMock.mock.calls[0][0] as string);
    expect(calledUrl.pathname).toBe("/property/1/nearby");
    expect(calledUrl.searchParams.get("q")).toBe("nearest supermarket");
  });

  it("requires an area question of at least two characters", async () => {
    const response = await app.inject({
      method: "GET",
      url: "/api/property/1/nearby?q=a",
    });
    expect(response.statusCode).toBe(400);
  });

  it("relays a non-amenity question as 422", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: "I can only answer questions about nearby amenities", examples: ["Nearest Tesco?"] },
        422,
      ),
    );

    const response = await app.inject({
      method: "GET",
      url: "/api/property/1/nearby?q=what%20is%20stamp%20duty",
    });

    expect(response.statusCode).toBe(422);
    expect(response.json().examples).toHaveLength(1);
  });

  it("relays a missing property as 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "Property not found" }, 404));

    const response = await app.inject({
      method: "GET",
      url: "/api/property/999/nearby?q=nearest%20park",
    });

    expect(response.statusCode).toBe(404);
  });

  it("rejects an empty chat payload", async () => {
    const response = await app.inject({
      method: "POST",
      url: "/api/chat",
      payload: { messages: [] },
    });
    expect(response.statusCode).toBe(400);
  });
});
