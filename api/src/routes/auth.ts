/**
 * Authentication routes — register, login, token validation.
 * Includes per-IP rate limiting to prevent brute-force attacks.
 */

import type { FastifyPluginCallback } from "fastify";


// ---- typed interfaces -------------------------------------------------------

interface AuthOpts {
  store: PgStore;
  signAccess: (sub: string) => string;
  verifyAccess: (token: string) => Promise<{ sub: string } | null>;
}

interface PgStore {
  createUser(opts: { email: string; passwordHash: string }): Promise<{ id: number }>;
  getUser(email: string): Promise<{ passwordHash: string; salt: string } | null> | null;
}


// ---- typed request bodies ---------------------------------------------------

interface RegisterBody {
  email?: string;
  password?: string;
}

interface LoginBody {
  email?: string;
  password?: string;
}


// ---- rate limiter (with cleanup) -------------------------------------------

const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute
const RATE_LIMIT_MAX = 5;            // max requests per window

interface RateEntry {
  count: number;
  resetAt: number;
}

// Map stores buckets keyed by IP; cleanupInterval removes stale entries
const ipAttempts = new Map<string, RateEntry>();
let _cleanupTimer: ReturnType<typeof setInterval> | null = null;

function startRateLimiterCleanup(): void {
  if (_cleanupTimer) return;
  _cleanupTimer = setInterval(() => {
    const now = Date.now();
    for (const [ip, entry] of ipAttempts.entries()) {
      if (now > entry.resetAt) ipAttempts.delete(ip);
    }
  }, RATE_LIMIT_WINDOW_MS);
  // Auto-cleanup on exit
  _cleanupTimer.unref?.();
}
startRateLimiterCleanup();

function checkRateLimit(ip: string): boolean {
  const now = Date.now();
  const entry = ipAttempts.get(ip);

  if (!entry || now > entry.resetAt) {
    ipAttempts.set(ip, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return true;
  }

  if (entry.count >= RATE_LIMIT_MAX) {
    return false;
  }

  entry.count++;
  return true;
}


function getIP(req: any): string {
  const forwarded = req.headers?.["x-forwarded-for"] as string | undefined;
  if (forwarded) {
    const first = forwarded.split(",")[0].trim();
    if (first) return first.replace("::ffff:", "");
  }
  return (req.ip ?? req.raw?.socket?.remoteAddress ?? "unknown").replace("::ffff:", "");
}


// ---- routes -----------------------------------------------------------------

export const authRoutes: FastifyPluginCallback<AuthOpts> = async (app, opts) => {
  // Register
  app.post<{ Body: RegisterBody }>("/auth/register", async (req, reply) => {
    const ip = getIP(req);
    if (!checkRateLimit(ip)) {
      return reply.code(429).send({ error: "too many registration attempts; try again later" });
    }

    const { email, password }: RegisterBody = req.body;
    if (!email || !password) {
      return reply.code(400).send({ error: "email and password are required" });
    }

    // Validate email format
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return reply.code(400).send({ error: "invalid email format" });
    }

    const { hash } = await import("./../services/passwords").then(m => m.hashPassword(password));
    await opts.store.createUser({ email, passwordHash: hash });

    const token = opts.signAccess(email);
    return { token };
  });

  // Login
  app.post<{ Body: LoginBody }>("/auth/login", async (req, reply) => {
    const ip = getIP(req);
    if (!checkRateLimit(ip)) {
      return reply.code(429).send({ error: "too many login attempts; try again later" });
    }

    const { email, password }: LoginBody = req.body;
    if (!email || !password) {
      return reply.code(400).send({ error: "email and password are required" });
    }

    // Use constant-time comparison to prevent timing attacks
    const user = await opts.store.getUser(email);
    if (!user) {
      // Still hash to avoid timing the lookup
      await import("./../services/passwords").then(m => m.hashPassword(password));
      return reply.code(401).send({ error: "invalid credentials" });
    }

    const verified = await import("./../services/passwords").then(m => m.verifyPassword(password, user.passwordHash, user.salt));
    if (!verified) {
      return reply.code(401).send({ error: "invalid credentials" });
    }

    const token = opts.signAccess(email);
    return { token };
  });

  // Get current user (requires valid JWT)
  app.get<{ Headers: { authorization?: string } }>("/auth/me", async (req, reply) => {
    const authHeader = req.headers.authorization ?? "";
    const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : authHeader;

    if (!token) {
      return reply.code(401).send({ error: "authentication required" });
    }

    // Verify with Fastify's jwt plugin (real cryptographic verification)
    try {
      const decoded = await app.jwt.verify(token);
      return { user: decoded };
    } catch {
      return reply.code(401).send({ error: "invalid or expired token" });
    }
  });
};
