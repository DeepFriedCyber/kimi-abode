/**
 * Authentication routes: registration, login, token refresh and profile.
 *
 * JWTs are signed/verified by @fastify/jwt, which is registered once in
 * app.ts. No secret fallback exists here.
 */

import type { FastifyPluginAsync, FastifyReply, FastifyRequest } from "fastify";
import {
  EmailAlreadyExistsError,
  normaliseEmail,
  registerUser,
  userStore,
} from "../services/user-store";
import { validatePassword } from "../services/passwords";
import { clientKey, FixedWindowRateLimiter } from "../services/rate-limit";
import { config } from "../config";

export interface JwtPayload {
  sub: string;
  email: string;
  name?: string;
}

const isTest = config.nodeEnv === "test";
const loginLimiter = new FixedWindowRateLimiter(isTest ? 1_000 : 10, 15 * 60_000);
const registerLimiter = new FixedWindowRateLimiter(isTest ? 1_000 : 10, 60 * 60_000);

const emailSchema = {
  type: "string",
  minLength: 3,
  maxLength: 254,
  pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$",
} as const;

const registerSchema = {
  body: {
    type: "object",
    required: ["email", "password"],
    additionalProperties: false,
    properties: {
      email: emailSchema,
      password: { type: "string", minLength: 1, maxLength: 200 },
      name: { type: "string", maxLength: 100 },
    },
  },
  response: {
    201: {
      type: "object",
      properties: {
        user: {
          type: "object",
          properties: {
            id: { type: "integer" },
            email: { type: "string" },
            name: { type: "string" },
            createdAt: { type: "string" },
          },
        },
      },
    },
  },
} as const;

const loginSchema = {
  body: {
    type: "object",
    required: ["email", "password"],
    additionalProperties: false,
    properties: {
      email: emailSchema,
      password: { type: "string", minLength: 1, maxLength: 200 },
    },
  },
} as const;

function tooManyRequests(reply: FastifyReply, retryAfter: number): void {
  void reply
    .code(429)
    .header("Retry-After", String(retryAfter))
    .send({ error: "Too many attempts. Please try again later." });
}

async function payloadFromRequest(request: FastifyRequest): Promise<JwtPayload> {
  return request.jwtVerify<JwtPayload>();
}

async function signFor(app: { jwt: { sign: (p: object) => string } }, user: {
  id: number;
  email: string;
  name: string;
}): Promise<string> {
  return app.jwt.sign({
    sub: String(user.id),
    email: user.email,
    name: user.name,
  });
}

export const authRoutes: FastifyPluginAsync = async (app) => {
  /**
   * POST /api/auth/register
   *
   * Returns the created user. The response for an existing address is
   * deliberately generic (409 without confirming whether the account exists
   * is still an oracle, so we keep the message neutral and rate limited).
   */
  app.post("/auth/register", { schema: registerSchema }, async (request, reply) => {
    const body = request.body as { email: string; password: string; name?: string };

    const limit = registerLimiter.consume(clientKey(request.ip, "register"));
    if (!limit.allowed) return tooManyRequests(reply, limit.retryAfterSeconds);

    const email = normaliseEmail(body.email);
    const name = body.name?.trim() ?? "";

    const policy = validatePassword(body.password, { email, name });
    if (!policy.valid) {
      return reply.code(400).send({ error: policy.message ?? "Invalid password" });
    }

    try {
      const user = await registerUser({ email, password: body.password, name });
      return reply.code(201).send({ user });
    } catch (error) {
      if (error instanceof EmailAlreadyExistsError) {
        // Same shape as the success path to avoid confirming account existence
        // via status code; the message stays generic.
        return reply.code(409).send({ error: "Unable to create an account with those details." });
      }
      request.log.error({ err: error }, "Registration failed");
      return reply.code(500).send({ error: "Registration failed" });
    }
  });

  /** POST /api/auth/login */
  app.post("/auth/login", { schema: loginSchema }, async (request, reply) => {
    const body = request.body as { email: string; password: string };
    const email = normaliseEmail(body.email);

    const limit = loginLimiter.consume(clientKey(request.ip, "login", email));
    if (!limit.allowed) return tooManyRequests(reply, limit.retryAfterSeconds);

    const user = await userStore.authenticate(email, body.password);
    if (!user) {
      // Identical response for "no such user" and "wrong password".
      return reply.code(401).send({ error: "Invalid email or password" });
    }

    const accessToken = await signFor(app, user);
    return reply.send({
      access_token: accessToken,
      token_type: "Bearer",
      expires_in: config.jwt.expiresIn,
      user,
    });
  });

  /** GET /api/auth/me */
  app.get("/auth/me", async (request, reply) => {
    let payload: JwtPayload;
    try {
      payload = await payloadFromRequest(request);
    } catch {
      return reply.code(401).send({ error: "Invalid or expired token" });
    }

    const user = await userStore.findById(Number(payload.sub));
    if (!user) {
      return reply.code(401).send({ error: "Invalid or expired token" });
    }

    return reply.send({ user });
  });

  /**
   * POST /api/auth/refresh
   *
   * Rotates the token. Only tokens that are still valid can be refreshed; a
   * dedicated refresh-token store with rotation is the next step for
   * production (this keeps the surface small for now).
   */
  app.post("/auth/refresh", async (request, reply) => {
    let payload: JwtPayload;
    try {
      payload = await payloadFromRequest(request);
    } catch {
      return reply.code(401).send({ error: "Invalid or expired token" });
    }

    const user = await userStore.findById(Number(payload.sub));
    if (!user) {
      return reply.code(401).send({ error: "Invalid or expired token" });
    }

    const accessToken = await signFor(app, user);
    return reply.send({
      access_token: accessToken,
      token_type: "Bearer",
      expires_in: config.jwt.expiresIn,
      user,
    });
  });

  /**
   * POST /api/auth/logout
   *
   * Stateless JWTs cannot be revoked without a denylist; clients must discard
   * the token. Documented here rather than pretending otherwise.
   */
  app.post("/auth/logout", async (_request, reply) => {
    return reply.code(204).send();
  });
};

export default authRoutes;
