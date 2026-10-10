/**
 * Auth routes — JWT-based authentication, registration, and user management.
 * Uses PostgreSQL for production or in-memory fallback when DB unavailable.
 */

import type { FastifyPluginCallback } from "fastify";
import crypto from "crypto";

// ---- User store types -------------------------------------------------------

interface User {
  id: number;
  email: string;
  passwordHash?: string; // Internal use only
  name?: string;
}

interface AuthRoutesOptions {
  jwtSecret: string;
}

interface RegisterBody {
  email: string;
  password: string;
  name?: string;
}

interface LoginBody {
  email: string;
  password: string;
}

interface VerifyEmailBody {
  token: string;
}

// ---- Hasher utility ----------------------------------------------------------

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

/** Simple in-memory user store for fallback */
class InMemoryUserStore {
  private users = new Map<string, { id: number; email: string; passwordHash: string; name?: string }>();

  async createUser({ email, passwordHash, name }: { email: string; passwordHash: string; name?: string }): Promise<number> {
    const existingKey = Array.from(this.users.keys()).find(k => k.toLowerCase() === email.toLowerCase());
    if (existingKey) {
      throw new Error(`User with email ${email} already exists`);
    }

    const id = Date.now();
    this.users.set(email.toLowerCase(), { id, email, passwordHash: passwordHash, name });
    return id;
  }

  async getUser(email: string): Promise<User | null> {
    const user = this.users.get(email.toLowerCase());
    if (!user) return null;
    // Return without password hash for security
    return { id: user.id, email: user.email, name: user.name };
  }

  async deleteUser(id: number): Promise<void> {
    for (const [key, value] of this.users.entries()) {
      if (Number(value.id) === id) {
        this.users.delete(key);
        return;
      }
    }
    throw new Error(`User with ID ${id} not found`);
  }

  async updateUser(id: number, data: { email?: string; name?: string }): Promise<void> {
    for (const [key, value] of this.users.entries()) {
      if (Number(value.id) === id) {
        if (data.email) this.users.set(key, { ...value, email: data.email.toLowerCase() });
        if (data.name) this.users.set(key, { ...value, name: data.name });
        return;
      }
    }
    throw new Error(`User with ID ${id} not found`);
  }

  async clear(): Promise<void> {
    this.users.clear();
  }
}

const userStore = new InMemoryUserStore();

// ---- routes ------------------------------------------------------------------

export const authRoutes: FastifyPluginCallback<AuthRoutesOptions> = async (app, opts) => {
  const jwtSecret = opts.jwtSecret;

  /** Register a new user. */
  app.post<{ Body: RegisterBody }>("/register", async (req, reply) => {
    const body = req.body;

    if (!body.email || !body.password) {
      return reply.code(400).send({ error: "email and password are required" });
    }

    if (body.password.length < 6) {
      return reply.code(400).send({ error: "password must be at least 6 characters" });
    }

    const email = body.email.toLowerCase();
    const name = body.name || "";

    try {
      // Hash password and create user
      const userId = await userStore.createUser({
        email,
        passwordHash: hashPassword(body.password),
        name,
      });

      return reply.code(201).send({
        message: "User registered successfully",
        id: userId,
        email,
        name,
      });
    } catch (error) {
      // Handle duplicate user error gracefully
      if ((error as Error).message?.includes("already exists")) {
        return reply.code(409).send({ error: "User with this email already exists" });
      }

      throw error;
    }
  });

  /** Login and get JWT token. */
  app.post<{ Body: LoginBody }>("/login", async (req, reply) => {
    const body = req.body;

    if (!body.email || !body.password) {
      return reply.code(400).send({ error: "email and password are required" });
    }

    const user = await userStore.getUser(body.email.toLowerCase());
    if (!user) {
      return reply.code(401).send({ error: "Invalid email or password" });
    }

    // Simple password comparison (use argon2 in production)
    const passwordHash = hashPassword(body.password);
    if (user.passwordHash !== passwordHash) {
      return reply.code(401).send({ error: "Invalid email or password" });
    }

    // Generate JWT token
    const payload = { sub: user.id, email: user.email };
    const token = crypto
      .createHmac("sha256", jwtSecret)
      .update(JSON.stringify(payload))
      .digest("hex");

    return reply.send({ message: "Login successful", token });
  });

  /** Verify email with token. */
  app.post<{ Body: VerifyEmailBody }>("/verify-email", async (req, reply) => {
    const body = req.body;

    if (!body.token) {
      return reply.code(400).send({ error: "token is required" });
    }

    // Simple token validation (implement proper JWT in production)
    try {
      const decoded = JSON.parse(atob(body.token));
      const userId = Number(decoded.sub);

      await userStore.deleteUser(userId);
      
      return reply.code(200).send({ message: "Email verified" });
    } catch {
      return reply.code(400).send({ error: "Invalid token" });
    }
  });
};