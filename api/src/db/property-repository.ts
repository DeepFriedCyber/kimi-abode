/**
 * Property store facade.
 *
 * Selects a backend once at process start and exposes a single instance so
 * health checks and routes observe the same data. Previously each request
 * created a fresh store, which is why health always reported zero rows.
 */

import { InMemoryPropertyStore, type Property, type PropertyStore } from "./types";
import { SqlitePropertyRepository } from "./sqlite-repository";

export class PropertyRepository implements PropertyStore {
  constructor(private readonly store: PropertyStore = new InMemoryPropertyStore()) {}

  get driver(): string {
    return this.store.driver;
  }

  getAll(): Promise<Property[]> {
    return this.store.getAll();
  }

  getLimited(limit: number): Promise<Property[]> {
    return this.store.getLimited(limit);
  }

  count(): Promise<number> {
    return this.store.count();
  }

  find(query: string): Promise<Property[]> {
    return this.store.find(query);
  }

  upsert(property: Partial<Property>): Promise<number> {
    return this.store.upsert(property);
  }

  clear(): Promise<void> {
    return this.store.clear();
  }
}

/**
 * Build the store for this process.
 *
 * SQLite is opt-in via SQLITE_PATH so that a stray DATABASE_URL cannot make the
 * gateway create an empty database file it never uses (search lives in the AI
 * service's Postgres).
 */
export function createPropertyRepository(sqlitePath?: string): PropertyRepository {
  if (sqlitePath) {
    try {
      return new PropertyRepository(new SqlitePropertyRepository(sqlitePath));
    } catch (error) {
      console.error("[PropertyRepository] Failed to open SQLite store:", error);
    }
  }
  return new PropertyRepository(new InMemoryPropertyStore());
}

export const propertyRepository = createPropertyRepository(
  process.env.SQLITE_PATH?.trim() || undefined,
);

export type { Property, PropertyStore };
