/**
 * SQLite Repository — Fallback for development/testing when PostgreSQL is unavailable.
 */

import Database from "better-sqlite3";
import type { Property, PropertyStore } from "./types";
import path from "path";

// --- In-memory fallback (when DATABASE_URL is empty) ---
class InMemoryPropertyStore implements PropertyStore {
  private properties: Map<number, Property> = new Map();
  private counter = 1;

  async getAll(): Promise<Property[]> {
    return Array.from(this.properties.values());
  }

  async getLimited(limit: number): Promise<Property[]> {
    const all = await this.getAll();
    return all.slice(0, limit);
  }

  async count(): Promise<number> {
    return this.properties.size;
  }

  async find(query: string): Promise<Property[]> {
    const q = query.toLowerCase();
    const matches: Property[] = [];

    for (const prop of this.properties.values()) {
      const text = JSON.stringify(prop).toLowerCase();
      if (text.includes(q)) {
        matches.push(prop);
      }
    }

    return matches.slice(0, 50);
  }

  async upsert(property: Partial<Property>): Promise<number> {
    const id = this.counter++;
    const prop: Property = {
      id,
      address_line1: property.address_line1 ?? "",
      address_line2: property.address_line2 ?? undefined,
      town: property.town ?? undefined,
      postcode: property.postcode ?? undefined,
      outcode: property.outcode ?? undefined,
      property_type: property.property_type ?? "detached",
      num_beds: property.num_beds ?? 2,
      price_paid: property.price_paid ?? 300000,
      date_sold: property.date_sold ? new Date(property.date_sold) : new Date(),
      latitude: property.latitude ?? undefined,
      longitude: property.longitude ?? undefined,
      source: property.source ?? "land-registry",
    };

    this.properties.set(id, prop);
    return id;
  }

  async clear(): Promise<void> {
    this.properties.clear();
  }
}

export { InMemoryPropertyStore };

// --- SQLite Repository for file-backed storage ---
class SqlitePropertyRepository implements PropertyStore {
  private db: Database.Database;
  private initialized = false;

  constructor(dbPath: string) {
    const absPath = path.resolve(dbPath);
    this.db = new Database(absPath);
    
    // Create tables if not exist
    const createTableSQL = `
      CREATE TABLE IF NOT EXISTS properties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address_line1 TEXT NOT NULL DEFAULT "",
        address_line2 TEXT,
        town TEXT,
        postcode TEXT,
        outcode TEXT,
        property_type TEXT NOT NULL DEFAULT "detached",
        num_beds INTEGER NOT NULL DEFAULT 2,
        price_paid INTEGER NOT NULL DEFAULT 300000,
        date_sold TEXT,
        latitude REAL,
        longitude REAL,
        source TEXT NOT NULL DEFAULT "land-registry"
      );
    `;

    this.db.exec(createTableSQL);
    this.initialized = true;
    
    console.log(`[SqlitePropertyRepository] Initialized at ${absPath}`);
  }

  async getAll(): Promise<Property[]> {
    this.ensureInitialized();
    const stmt = this.db.prepare("SELECT * FROM properties ORDER BY id");
    return stmt.all() as any[];
  }

  async getLimited(limit: number): Promise<Property[]> {
    const all = await this.getAll();
    return all.slice(0, limit);
  }

  async count(): Promise<number> {
    this.ensureInitialized();
    const stmt = this.db.prepare("SELECT COUNT(*) as count FROM properties");
    const result = stmt.get() as any;
    return Number(result.count) ?? 0;
  }

  async find(query: string): Promise<Property[]> {
    const q = query.toLowerCase();
    const results = await this.getAll();
    const matches: Property[] = [];

    for (const prop of results) {
      const text = JSON.stringify(prop).toLowerCase();
      if (text.includes(q)) {
        matches.push(prop);
      }
    }

    return matches.slice(0, 50);
  }

  async upsert(property: Partial<Property>): Promise<number> {
    this.ensureInitialized();
    
    const existing = await this.getAll();
    for (const prop of existing) {
      if ((prop.address_line1 || "") === (property.address_line1 || "")) {
        const updateSQL = `
          UPDATE properties SET
            address_line2 = ?,
            town = ?,
            postcode = ?,
            outcode = ?,
            property_type = ?,
            num_beds = ?,
            price_paid = ?,
            date_sold = ?,
            latitude = ?,
            longitude = ?,
            source = ?
          WHERE id = ?;
        `;

        const stmt = this.db.prepare(updateSQL);
        stmt.run(
          property.address_line2 ?? undefined,
          property.town ?? undefined,
          property.postcode ?? undefined,
          property.outcode ?? undefined,
          property.property_type ?? "detached",
          property.num_beds ?? 2,
          property.price_paid ?? 300000,
          property.date_sold ? property.date_sold.toString() : new Date().toISOString(),
          property.latitude ?? undefined,
          property.longitude ?? undefined,
          property.source ?? "land-registry",
          prop.id,
        );

        return prop.id;
      }
    }

    // Insert new property
    const insertSQL = `
      INSERT INTO properties (
        address_line1,
        address_line2,
        town,
        postcode,
        outcode,
        property_type,
        num_beds,
        price_paid,
        date_sold,
        latitude,
        longitude,
        source
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    `;

    const stmt = this.db.prepare(insertSQL);
    const id = Number(stmt.run(
      property.address_line1 || "",
      property.address_line2 ?? undefined,
      property.town ?? undefined,
      property.postcode ?? undefined,
      property.outcode ?? undefined,
      property.property_type ?? "detached",
      property.num_beds ?? 2,
      property.price_paid ?? 300000,
      property.date_sold ? property.date_sold.toString() : new Date().toISOString(),
      property.latitude ?? undefined,
      property.longitude ?? undefined,
      property.source ?? "land-registry",
    ));

    return id;
  }

  async clear(): Promise<void> {
    this.ensureInitialized();
    this.db.exec("DELETE FROM properties");
    console.log("[SqlitePropertyRepository] Cleared all properties");
  }

  private ensureInitialized(): void {
    if (!this.initialized) {
      throw new Error("[SqlitePropertyRepository] Not initialized. Call constructor with a valid path first.");
    }
  }
}

export { SqlitePropertyRepository };

// Seed sample data function
export async function SeedProperties(dbPath: string): Promise<void> {
  const repo = new SqlitePropertyRepository(dbPath);
  
  // Always reseed for demo purposes - clear and repopulate
  repo.clear();
  
  const sampleProperties: Property[] = [
    { id: 1, address_line1: "2 Oakwood Close", town: "Manchester", postcode: "M1 1AA", outcode: "M1", property_type: "terraced", num_beds: 2, price_paid: 250000, date_sold: "2024-03-15", latitude: 53.4808, longitude: -2.2426, source: "land-registry" },
    { id: 2, address_line1: "45 Church Lane", town: "Leeds", postcode: "LS1 2BB", outcode: "LS1", property_type: "detached", num_beds: 4, price_paid: 450000, date_sold: "2023-11-20", latitude: 53.8008, longitude: -1.5491, source: "land-registry" },
  ];

  for (const prop of sampleProperties) {
    await repo.upsert(prop);
  }
}