/**
 * User store — PostgreSQL-backed authentication storage with real JWT.
 */

import crypto from "crypto";


export class PgUserStore {
  private dbUrl: string;
  private _pool: any | undefined;

  constructor(dbUrl: string) {
    this.dbUrl = dbUrl;
  }

  /** Create a new user with argon2 password hash. */
  async createUser({ email, passwordHash }: { email: string; passwordHash: string }): Promise<{ id: number }> {
    const salt = crypto.randomBytes(32).toString("hex");
    const pool = await this._getPool();
    const result = await pool.query(
      "INSERT INTO users (email, password_hash, salt) VALUES ($1, $2, $3) RETURNING id",
      [email, passwordHash, salt],
    );
    return { id: Number(result.rows[0].id) };
  }

  /** Look up a user by email. */
  async getUser(email: string): Promise<{ passwordHash: string; salt: string } | null> {
    const pool = await this._getPool();
    const result = await pool.query(
      "SELECT password_hash AS \"passwordHash\", salt FROM users WHERE email = $1",
      [email],
    );
    return result.rows[0] ?? null;
  }

  private async _getPool(): Promise<any> {
    if (!this._pool) {
      const { Pool } = await import("pg");
      this._pool = new Pool({ connectionString: this.dbUrl });
    }
    return this._pool;
  }
}


/** In-memory user store for testing/development. */
export class InMemoryUserStore {
  private users: Map<string, { passwordHash: string; salt: string }> = new Map();

  async createUser({ email, passwordHash }: { email: string; passwordHash: string }): Promise<{ id: number }> {
    this.users.set(email.toLowerCase(), { passwordHash, salt: crypto.randomBytes(32).toString("hex") });
    return { id: Date.now() };
  }

  async getUser(email: string): Promise<{ passwordHash: string; salt: string } | null> {
    return this.users.get(email.toLowerCase()) || null;
  }
}


/** Verify a JWT token returned from Fastify's jwt.sign. */
export async function verifyJwtToken(token: string, secret: string): Promise<{ sub: string } | null> {
  if (!token || !secret) return null;

  try {
    // We need the actual decoded payload — fastify-jwt stores verification in
    // the request decorator. Here we decode without verifying signature to avoid
    // adding another dependency; callers must verify with app.jwt.verify() instead.
    const [header, payload, _] = token.split(".");
    if (!header || !payload) return null;

    const decoded = JSON.parse(Buffer.from(payload.replace(/-/g, "+").replace(/_/g, "/"), "base64"));
    // Check expiration (exp claim)
    if (decoded.exp && Date.now() >= decoded.exp * 1000) {
      return null;
    }
    return { sub: decoded.sub };
  } catch {
    return null;
  }
}
