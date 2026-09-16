"""Observability/metrics for AI service (Python)."""

from __future__ import annotations

import time
from collections import defaultdict


class Metrics:
    """Simple in-memory metrics collector."""

    def __init__(self):
        self._requests: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, amount: int = 1):
        self._requests[name] += amount

    def observe(self, name: str, value: float):
        self._latencies[name].append(value)

    def render(self) -> str:
        lines = ["# Abode AI Metrics\n"]
        for name, count in sorted(self._requests.items()):
            avg = sum(self._latencies.get(name, [0])) / max(len(self._latencies.get(name, [1])), 1)
            lines.append(f"abode_{name}_total {{count={count}, avg_latency_ms={avg:.1f}}}\n")
        return "\n".join(lines)


class MetricsMiddleware:
    """FastAPI middleware for request metrics."""

    def __init__(self, app, *, metrics: Metrics):
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        except Exception:
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.metrics.inc("requests")
            self.metrics.observe("latency_ms", elapsed_ms)


class InstrumentedRouter:
    """Router wrapper that tracks provider health and latency."""

    def __init__(self, router, metrics):
        self.router = router
        self.metrics = metrics
        self._provider_counts: dict[str, int] = defaultdict(int)

    async def route(self, query):
        start = time.perf_counter()
        result = await self.router.route(query)
        elapsed_ms = (time.perf_counter() - start) * 1000
        tier = result.get("tier", "unknown")
        self._provider_counts[tier] += 1
        self.metrics.observe(f"router_{tier}_ms", elapsed_ms)
        return result
