/**
 * Metrics unit tests.
 */

import { describe, expect, it } from "vitest";
import { Metrics, metricKey, metricsHook } from "../src/observability/metrics";

describe("Metrics", () => {
  it("increments request count", () => {
    const metrics = new Metrics();
    metrics.inc("test");
    expect(metrics.render()).toContain("abode_http_test_total 1");
  });

  it("renders Prometheus-compatible output", () => {
    const metrics = new Metrics();
    metrics.inc("requests", 5);
    expect(metrics.render()).toContain("abode_http_requests_total 5");
  });

  it("averages latency observations", () => {
    const metrics = new Metrics();
    metrics.observe("search_ms", 100);
    metrics.observe("search_ms", 200);
    expect(metrics.render()).toContain("abode_http_search_ms_avg_latency_ms 150.00");
  });

  it("returns empty string when no metrics", () => {
    expect(new Metrics().render()).toBe("");
  });
});

describe("metricsHook", () => {
  it("counts every response and normalises the path", async () => {
    const metrics = new Metrics();
    const hook = metricsHook(metrics);

    const request = { url: "/test", routeOptions: undefined } as never;
    await hook(request, { statusCode: 500 } as never);

    expect(metrics.render()).toContain("abode_http_test_responses_total 1");
  });

  it("uses the route template so ids do not explode cardinality", () => {
    const key = metricKey({ url: "/api/property/123", routeOptions: { url: "/api/property/:id" } } as never);
    expect(key).toBe("api_property_id_responses");
  });
});
