/**
 * SQLite-backed property store (opt-in via SQLITE_PATH).
 *
 * Uses a unique index on (address_line1, postcode) and `ON CONFLICT` so upserts
 * are a single statement instead of a full-table scan per write.
 */

import Database from "better-sqlite3";
import path from "node:path";
import { InMemoryPropertyStore, type Property, type PropertyStore } from "./types";

export { InMemoryPropertyStore };

const SCHEMA = `
  CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address_line1 TEXT NOT NULL,
    address_line2 TEXT,
    town TEXT,
    postcode TEXT,
    outcode TEXT,
    property_type TEXT NOT NULL DEFAULT 'unknown',
    num_beds INTEGER,
    price_paid REAL,
    date_sold TEXT,
    latitude REAL,
    longitude REAL,
    source TEXT NOT NULL DEFAULT 'land-registry'
  );
  CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_address_postcode
    ON properties (address_line1, postcode);
  CREATE INDEX IF NOT EXISTS idx_properties_town ON properties (town);
  CREATE INDEX IF NOT EXISTS idx_properties_outcode ON properties (outcode);
`;

export class SqlitePropertyRepository implements PropertyStore {
  readonly driver = "sqlite";

  private readonly db: Database.Database;

  constructor(dbPath: string) {
    const absolutePath = path.resolve(dbPath);
    this.db = new Database(absolutePath);
    this.db.pragma("journal_mode = WAL");
    this.db.pragma("foreign_keys = ON");
    this.db.exec(SCHEMA);
    console.log(`[SqlitePropertyRepository] Initialised at ${absolutePath}`);
  }

  async getAll(): Promise<Property[]> {
    return this.db.prepare("SELECT * FROM properties ORDER BY id").all() as Property[];
  }

  async getLimited(limit: number): Promise<Property[]> {
    const safeLimit = Math.max(0, Math.floor(limit));
    return this.db
      .prepare("SELECT * FROM properties ORDER BY id LIMIT ?")
      .all(safeLimit) as Property[];
  }

  async count(): Promise<number> {
    const row = this.db.prepare("SELECT COUNT(*) AS count FROM properties").get() as {
      count: number;
    };
    return Number(row.count) || 0;
  }

  async find(query: string): Promise<Property[]> {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];

    // Filter in SQL rather than loading the table into memory.
    return this.db
      .prepare(
        `SELECT * FROM properties
         WHERE LOWER(COALESCE(address_line1, '') || ' ' ||
                     COALESCE(address_line2, '') || ' ' ||
                     COALESCE(town, '') || ' ' ||
                     COALESCE(postcode, '') || ' ' ||
                     COALESCE(property_type, '')) LIKE ?
         ORDER BY id
         LIMIT 50`,
      )
      .all(`%${needle}%`) as Property[];
  }

  async upsert(property: Partial<Property>): Promise<number> {
    const dateSold = toIsoDate(property.date_sold);

    const row = this.db
      .prepare(
        `INSERT INTO properties (
           address_line1, address_line2, town, postcode, outcode, property_type,
           num_beds, price_paid, date_sold, latitude, longitude, source
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (address_line1, postcode) DO UPDATE SET
           address_line2 = excluded.address_line2,
           town = excluded.town,
           outcode = excluded.outcode,
           property_type = excluded.property_type,
           num_beds = excluded.num_beds,
           price_paid = excluded.price_paid,
           date_sold = excluded.date_sold,
           latitude = excluded.latitude,
           longitude = excluded.longitude,
           source = excluded.source
         RETURNING id`,
      )
      .get(
        property.address_line1 ?? "",
        property.address_line2 ?? null,
        property.town ?? null,
        property.postcode ?? null,
        property.outcode ?? null,
        property.property_type ?? "unknown",
        property.num_beds ?? null,
        property.price_paid ?? null,
        dateSold,
        property.latitude ?? null,
        property.longitude ?? null,
        property.source ?? "land-registry",
      ) as { id: number };

    return row.id;
  }

  async clear(): Promise<void> {
    this.db.exec("DELETE FROM properties");
  }

  close(): void {
    this.db.close();
  }
}

function toIsoDate(value: Property["date_sold"]): string | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 10);
}

/** Seed a couple of rows for local demos. Idempotent (uses upsert). */
export async function seedProperties(dbPath: string): Promise<void> {
  const repo = new SqlitePropertyRepository(dbPath);
  const samples: Array<Partial<Property>> = [
    {
      address_line1: "2 Oakwood Close", town: "Manchester", postcode: "M1 1AA",
      outcode: "M1", property_type: "terraced", num_beds: 2, price_paid: 250_000,
      date_sold: "2024-03-15", latitude: 53.4808, longitude: -2.2426,
    },
    {
      address_line1: "45 Church Lane", town: "Leeds", postcode: "LS1 2BB",
      outcode: "LS1", property_type: "detached", num_beds: 4, price_paid: 450_000,
      date_sold: "2023-11-20", latitude: 53.8008, longitude: -1.5491,
    },
  ];

  for (const sample of samples) await repo.upsert(sample);
  repo.close();
}
