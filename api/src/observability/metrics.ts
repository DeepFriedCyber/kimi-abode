/**
 * Observability / metrics for the API server.
 */

import type { FastifyInstance } from "fastify";


export class Metrics {
  private requestCount = new Map<string, number>();
  private latencySum = new Map<string, number>();
  private latencyCount = new Map<string, number>();

  inc(name: string, amount: number = 1): void {
    this.requestCount.set(name, (this.requestCount.get(name) || 0) + amount);
  }

  observe(name: string, ms: number): void {
    const sum = this.latencySum.get(name) || 0;
    const count = this.latencyCount.get(name) || 0;
    this.latencySum.set(name, sum + ms);
    this.latencyCount.set(name, count + 1);
  }

  render(): string {
    const lines: string[] = [];
    for (const [name, count] of this.requestCount.entries()) {
      const avg = count > 0 ? (this.latencySum.get(name) || 0) / count : 0;
      lines.push(`abode_http_${name}_total ${count}`);
      lines.push(`abode_http_${name}_avg_latency_ms ${avg.toFixed(2)}`);
    }
    return lines.join("\n");
  }
}

/** Hook for recording response metrics. */
export function metricsHook(metrics: Metrics) {
  return async (request: any, reply: any) => {
    const path = request.route?.url || request.url;
    const safePath = path || "/unknown";
    // Normalize route path for metrics key
    const key = safePath.startsWith("/")
      ? `${safePath.slice(1).replace(/\//g, "_")}_responses`
      : `${safePath.replace(/\//g, "_")}_responses`;
    metrics.inc(key, reply.statusCode < 400 ? 1 : 0);
  };
}

/** Prometheus-compatible metrics endpoint plugin. */
export function registerMetricsPlugin(app: FastifyInstance, metrics: Metrics) {
  app.get("/api/metrics", async () => ({ metrics: metrics.render() }));
}
