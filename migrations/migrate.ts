/**
 * PostgreSQL Database Migrations — Rebuilds and seeds the property search database
 */

import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 5,
});

export async function seedProperties(): Promise<void> {
  const client = await pool.connect();
  
  try {
    // Enable UUID extension
    await client.query("CREATE EXTENSION IF NOT EXISTS 'uuid-ossp';");
    
    // Create properties table
    await client.query(`
      CREATE TABLE IF NOT EXISTS properties (
        id SERIAL PRIMARY KEY,
        address_line1 VARCHAR(255) NOT NULL,
        town VARCHAR(100) NOT NULL,
        postcode VARCHAR(10) NOT NULL,
        outcode VARCHAR(7),
        property_type VARCHAR(50) NOT NULL,
        num_beds INTEGER,
        price_paid NUMERIC(12,2),
        date_sold DATE,
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        source VARCHAR(50) DEFAULT 'land-registry',
        embeddings TEXT,
        created_at TIMESTAMP DEFAULT NOW()
      );
    `);
    
    // Insert sample data
    const sampleProperties = [
      {
        address_line1: "2 Oakwood Close",
        town: "Manchester",
        postcode: "M1 1AA",
        outcode: "M1",
        property_type: "terraced",
        num_beds: 2,
        price_paid: 250000.00,
        date_sold: "2024-03-15",
        latitude: 53.4808,
        longitude: -2.2426,
      },
    ];

    for (const prop of sampleProperties) {
      await client.query(`
        INSERT INTO properties 
        (address_line1, town, postcode, outcode, property_type, num_beds, price_paid, date_sold, latitude, longitude)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (address_line1) DO UPDATE SET
          town = EXCLUDED.town,
          postcode = EXCLUDED.postcode,
          property_type = EXCLUDED.property_type;
      `, [
        prop.address_line1, prop.town, prop.postcode, prop.outcode,
        prop.property_type, prop.num_beds, prop.price_paid, prop.date_sold,
        prop.latitude, prop.longitude
      ]);
    }

    console.log("[Migration] Database seeded");
  } finally {
    client.release();
  }
}

export default seedProperties;
