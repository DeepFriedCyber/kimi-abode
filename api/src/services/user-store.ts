/**
 * In-memory user store.
 *
 * This is a development/test implementation: data is lost on restart. The
 * interface is deliberately async and narrow so it can be replaced by a
 * Postgres-backed store without touching the routes.
 */

import {
  DUMMY_PASSWORD_HASH,
  hashPassword,
  validatePassword,
  verifyPassword,
} from "./passwords";

export interface User {
  id: number;
  email: string;
  name: string;
  createdAt: string;
}

interface StoredUser extends User {
  passwordHash: string;
}

export class EmailAlreadyExistsError extends Error {
  constructor(email: string) {
    super(`An account with email ${email} already exists`);
    this.name = "EmailAlreadyExistsError";
  }
}

export class InMemoryUserStore {
  private readonly byEmail = new Map<string, StoredUser>();
  private nextId = 1;

  async createUser(input: {
    email: string;
    password: string;
    name?: string;
  }): Promise<User> {
    const email = input.email.trim().toLowerCase();
    const name = (input.name ?? "").trim();

    if (this.byEmail.has(email)) {
      throw new EmailAlreadyExistsError(email);
    }

    const passwordHash = await hashPassword(input.password);
    const record: StoredUser = {
      id: this.nextId++,
      email,
      name,
      passwordHash,
      createdAt: new Date().toISOString(),
    };

    this.byEmail.set(email, record);
    return toPublicUser(record);
  }

  async findByEmail(email: string): Promise<User | null> {
    const record = this.byEmail.get(email.trim().toLowerCase());
    return record ? toPublicUser(record) : null;
  }

  async findById(id: number): Promise<User | null> {
    for (const record of this.byEmail.values()) {
      if (record.id === id) return toPublicUser(record);
    }
    return null;
  }

  /**
   * Verify credentials. Always performs a bcrypt comparison — even when the
   * user does not exist — so response time does not leak account existence.
   */
  async authenticate(email: string, password: string): Promise<User | null> {
    const record = this.byEmail.get(email.trim().toLowerCase());
    const hash = record?.passwordHash ?? DUMMY_PASSWORD_HASH;
    const matches = await verifyPassword(password, hash);
    return record && matches ? toPublicUser(record) : null;
  }

  async updateUser(
    id: number,
    patch: { email?: string; name?: string },
  ): Promise<User | null> {
    for (const [key, record] of this.byEmail) {
      if (record.id !== id) continue;

      if (patch.email && patch.email.trim().toLowerCase() !== key) {
        const nextEmail = patch.email.trim().toLowerCase();
        if (this.byEmail.has(nextEmail)) {
          throw new EmailAlreadyExistsError(nextEmail);
        }
        this.byEmail.delete(key);
        record.email = nextEmail;
        this.byEmail.set(nextEmail, record);
      }

      if (patch.name !== undefined) {
        record.name = patch.name.trim();
      }

      return toPublicUser(record);
    }
    return null;
  }

  async deleteUser(id: number): Promise<boolean> {
    for (const [key, record] of this.byEmail) {
      if (record.id === id) {
        this.byEmail.delete(key);
        return true;
      }
    }
    return false;
  }

  async count(): Promise<number> {
    return this.byEmail.size;
  }

  /** Test helper. */
  async clear(): Promise<void> {
    this.byEmail.clear();
    this.nextId = 1;
  }
}

function toPublicUser(record: StoredUser): User {
  return {
    id: record.id,
    email: record.email,
    name: record.name,
    createdAt: record.createdAt,
  };
}

export const userStore = new InMemoryUserStore();

/**
 * Create a user after applying the password policy.
 * Throws `Error` with a user-facing message when validation fails.
 */
export async function registerUser(input: {
  email: string;
  password: string;
  name?: string;
}): Promise<User> {
  const validation = validatePassword(input.password, {
    email: input.email,
    name: input.name,
  });
  if (!validation.valid) {
    throw new Error(validation.message ?? "Invalid password");
  }
  return userStore.createUser(input);
}

/** Normalise an email for storage/comparison. */
export function normaliseEmail(email: string): string {
  return email.trim().toLowerCase();
}
