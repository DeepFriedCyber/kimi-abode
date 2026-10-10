import Knex from 'knex';

export async function up(knex: Knex): Promise<void> {
  console.log('[Migrate] Upgrading properties schema...');
  
  // Drop and recreate properties table with fresh schema
  await knex.raw(`
    DROP TABLE IF EXISTS properties;
    DROP TABLE IF EXISTS categories;
    DROP TABLE IF EXISTS poi;
    
    CREATE TABLE categories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE NOT NULL,
      slug TEXT UNIQUE NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE properties (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      location TEXT,
      price REAL,
      bedrooms INTEGER,
      bathrooms INTEGER,
      sqft REAL,
      amenities TEXT,
      images TEXT,
      status TEXT DEFAULT 'available',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE poi (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      property_id INTEGER REFERENCES properties(id),
      name TEXT NOT NULL,
      category TEXT NOT NULL,
      distance_m REAL NOT NULL,
      walk_time_min REAL NOT NULL,
      decay_score REAL NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX idx_properties_location ON properties(location);
    CREATE INDEX idx_properties_type ON properties(property_type);
    CREATE INDEX idx_poi_property_id ON poi(property_id);
  `);
}

export async function down(knex: Knex): Promise<void> {
  console.log('[Migrate] Downgrading properties schema...');
  await knex.raw(`
    DROP TABLE IF EXISTS poi;
    DROP TABLE IF EXISTS properties;
    DROP TABLE IF EXISTS categories;
  `);
}