/**
 * Minimal in-process fixed-window rate limiter.
 *
 * Suitable for a single instance / local development. For multi-instance
 * deployments swap the bucket map for Redis (@fastify/rate-limit).
 */

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  retryAfterSeconds: number;
}

interface Bucket {
  count: number;
  resetAt: number;
}

export class FixedWindowRateLimiter {
  private readonly buckets = new Map<string, Bucket>();
  private lastSweep = Date.now();

  constructor(
    private readonly limit: number,
    private readonly windowMs: number,
    private readonly maxKeys = 10_000,
  ) {
    if (limit < 1 || windowMs < 1) {
      throw new Error("Rate limiter requires a positive limit and window");
    }
  }

  consume(key: string): RateLimitResult {
    const now = Date.now();
    this.sweep(now);

    const bucket = this.buckets.get(key);
    if (!bucket || bucket.resetAt <= now) {
      this.evictIfFull();
      this.buckets.set(key, { count: 1, resetAt: now + this.windowMs });
      return {
        allowed: true,
        remaining: this.limit - 1,
        retryAfterSeconds: 0,
      };
    }

    if (bucket.count >= this.limit) {
      return {
        allowed: false,
        remaining: 0,
        retryAfterSeconds: Math.max(1, Math.ceil((bucket.resetAt - now) / 1000)),
      };
    }

    bucket.count += 1;
    return {
      allowed: true,
      remaining: this.limit - bucket.count,
      retryAfterSeconds: 0,
    };
  }

  reset(): void {
    this.buckets.clear();
  }

  private sweep(now: number): void {
    if (now - this.lastSweep < this.windowMs) return;
    this.lastSweep = now;
    for (const [key, bucket] of this.buckets) {
      if (bucket.resetAt <= now) this.buckets.delete(key);
    }
  }

  private evictIfFull(): void {
    if (this.buckets.size < this.maxKeys) return;
    // Map iteration is insertion-ordered: drop the oldest keys first.
    const toDrop = this.buckets.size - this.maxKeys + 1;
    let dropped = 0;
    for (const key of this.buckets.keys()) {
      this.buckets.delete(key);
      if (++dropped >= toDrop) break;
    }
  }
}

/** Client key for rate limiting: prefer the socket address. */
export function clientKey(ip: string | undefined, scope: string, subject = ""): string {
  return `${scope}:${ip ?? "unknown"}:${subject.toLowerCase()}`;
}
