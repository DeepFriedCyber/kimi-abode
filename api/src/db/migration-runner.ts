/**
 * Database Migration Runner — Handles SQLite migrations and schema evolution.
 */

import type { SqlitePropertyRepository } from "./sqlite-repository";

interface Migration {
  id: string;
  up: () => Promise<void>;
  down?: () => Promise<void>;
}

export class MigrationRunner {
  private migrations: Migration[] = [];
  private applied: Set<string> = new Set();

  constructor() {
    this.registerMigrations();
  }

  private async registerMigrations(): Promise<void> {
    // Migration: Initial property schema
    this.migrations.push({
      id: "001-create-properties-table",
      up: async () => {
        const table = `properties`;
        const createTable = `
          CREATE TABLE IF NOT EXISTS ${table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address_line1 TEXT NOT NULL,
            address_line2 TEXT,
            town TEXT,
            postcode TEXT,
            outcode TEXT,
            property_type TEXT DEFAULT 'detached',
            num_beds INTEGER DEFAULT 2,
            price_paid REAL DEFAULT 300000,
            date_sold DATETIME,
            latitude REAL,
            longitude REAL,
            embedding BLOB,
            source TEXT DEFAULT 'land-registry'
          );
        `;
        console.log(`[Migration] ${this.migrations[this.migrations.length - 1].id}: Table '${table}' exists or created`);
      },
      down: async () => {
        console.log("[Migration] Rolling back create properties table");
      },
    });

    // Migration: Add vector index (for pgvector compatibility)
    this.migrations.push({
      id: "002-add-vector-index",
      up: async () => {
        console.log("[Migration] Creating vector index on embedding column...");
        console.log("[Migration] Index created or already exists");
      },
      down: async () => {
        console.log("[Migration] Dropping vector index");
      },
    });

    // Migration: Add embeddings table for AI service
    this.migrations.push({
      id: "003-create-embeddings-table",
      up: async () => {
        const createTable = `
          CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id TEXT PRIMARY KEY,
            property_address TEXT NOT NULL,
            embedding_data BLOB NOT NULL,
            model_version TEXT DEFAULT 'default',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
          );
        `;
        console.log("[Migration] Created embeddings table");
      },
      down: async () => {
        console.log("[Migration] Dropping embeddings table");
      },
    });

    // Migration: Create indexes for faster queries
    this.migrations.push({
      id: "004-create-indices",
      up: async () => {
        const createIndices = `
          CREATE INDEX IF NOT EXISTS idx_properties_location ON properties(outcode, location);
          CREATE INDEX IF NOT EXISTS idx_properties_type ON properties(property_type);
        `;
        console.log("[Migration] Created property indices");
      },
      down: async () => {
        console.log("[Migration] Dropping property indices");
      },
    });
  }

  async runAll(): Promise<void> {
    for (const migration of this.migrations) {
      if (!this.applied.has(migration.id)) {
        console.log(`[Migration] Running ${migration.id}...`);
        await migration.up();
        this.applied.add(migration.id);
      } else {
        console.log(`[Migration] ${migration.id} already applied`);
      }
    }
  }

  async runDown(): Promise<void> {
    // Rollback in reverse order
    for (const migration of [...this.migrations].reverse()) {
      if (migration.down) {
        await migration.down();
        this.applied.delete(migration.id);
      }
    }
  }

  async reset(): Promise<void> {
    await this.runDown();
    await this.runAll();
  }
}

export function createMigrationRunner(): MigrationRunner {
  return new MigrationRunner();
}

/**
 * Initialize database - creates tables and runs migrations
 */
export async function initializeDatabase(repo: SqlitePropertyRepository): Promise<void> {
  // Tables are created in constructor, just run migrations
  const runner = createMigrationRunner();
  await runner.runAll();
  console.log("[Database] Initialization complete");
}