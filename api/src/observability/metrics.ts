/**
 * Observability: in-process counters and latency summaries.
 *
 * Keys are derived from the *route template* (e.g. /api/property/:id) rather
 * than the concrete URL to keep cardinality bounded.
 */

import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";

export class Metrics {
  private readonly requestCount = new Map<string, number>();
  private readonly latencySum = new Map<string, number>();
  private readonly latencyCount = new Map<string, number>();

  inc(name: string, amount = 1): void {
    this.requestCount.set(name, (this.requestCount.get(name) ?? 0) + amount);
  }

  observe(name: string, ms: number): void {
    this.latencySum.set(name, (this.latencySum.get(name) ?? 0) + ms);
    this.latencyCount.set(name, (this.latencyCount.get(name) ?? 0) + 1);
  }

  render(): string {
    const names = new Set([...this.requestCount.keys(), ...this.latencySum.keys()]);
    const lines: string[] = [];

    for (const name of [...names].sort()) {
      const count = this.requestCount.get(name);
      if (count !== undefined) {
        lines.push(`abode_http_${name}_total ${count}`);
      }
      const observations = this.latencyCount.get(name);
      const sum = this.latencySum.get(name);
      if (observations && sum !== undefined) {
        lines.push(
          `abode_http_${name}_avg_latency_ms ${(sum / observations).toFixed(2)}`,
        );
      }
    }

    return lines.join("\n");
  }
}

/** Normalise a route/URL into a bounded metric name. */
export function metricKey(request: FastifyRequest): string {
  const path = request.routeOptions?.url ?? request.url.split("?")[0] ?? "/unknown";
  return `${path.replace(/^\//, "").replace(/[/:]+/g, "_") || "root"}_responses`;
}

/**
 * onResponse hook: counts every response (including errors) and records
 * latency when Fastify exposes it.
 */
export function metricsHook(metrics: Metrics) {
  return async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const key = metricKey(request);
    metrics.inc(key, 1);

    const elapsed = reply.elapsedTime;
    if (typeof elapsed === "number" && Number.isFinite(elapsed)) {
      metrics.observe(key, elapsed);
    }
  };
}

/** Exposes Prometheus-style text at GET /api/metrics. */
export function registerMetricsPlugin(app: FastifyInstance, metrics: Metrics): void {
  app.get("/api/metrics", async (_request, reply) => {
    return reply
      .header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
      .send(metrics.render());
  });
}
