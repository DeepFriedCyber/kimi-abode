/**
 * Tests for metrics / observability.
 */

import { describe, it, expect } from "vitest";
import { Metrics, metricsHook } from "../src/observability/metrics";

describe("Metrics", () => {
  const metrics = new Metrics();

  it("increments request count", () => {
    metrics.inc("test");
    expect(metrics["requestCount"].get("test")).toBe(1);
  });

  it("renders Prometheus-compatible output", () => {
    metrics.inc("requests", 5);
    const rendered = metrics.render();
    expect(rendered).toContain("abode_http_requests_total 5");
  });

  it("records latency observations", () => {
    metrics.observe("search_ms", 100);
    metrics.observe("search_ms", 200);
    const avg = (metrics["latencySum"].get("search_ms") || 0) / (metrics["latencyCount"].get("search_ms") || 1);
    expect(avg).toBe(150);
  });

  it("returns empty string when no metrics", () => {
    const m = new Metrics();
    expect(m.render()).toBe("");
  });
});

describe("metricsHook", () => {
  it("calls inc with the correct path", async () => {
    const metrics = new Metrics();
    const hook = metricsHook(metrics);

    const mockReq = { route: null, url: "/test" }; // route is null in our test
    const mockReply = { statusCode: 200 };

    await hook(mockReq, mockReply);
    // Route path "/test" → key "test_responses"
    expect(metrics["requestCount"].get("test_responses")).toBe(1);
  });
});
