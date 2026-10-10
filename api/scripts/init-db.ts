/**
 * Database initialization — creates tables and seeds sample data.
 * Run automatically on API startup when using SQLite.
 */

import Database from "better-sqlite3";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import fs from "fs";


const __dirname = dirname(fileURLToPath(import.meta.url));
const dbPath = process.env.DATABASE_PATH || join(__dirname, "../../api/data.db");

console.log(`[DB] Opening database at: ${dbPath}`);

// Auto-create .db file if it doesn't exist (SQLite handles this)
if (!fs.existsSync(dbPath)) {
  fs.writeFileSync(dbPath, ""); // Create empty file
  console.log("[DB] Created empty database file");
}

const db = new Database(dbPath);

// Enable foreign keys
db.pragma("foreign_keys = ON");

console.log("[Migrate] Running database migrations...");

// Initialize schema (drop and recreate for fresh start)
db.exec(`
    DROP TABLE IF EXISTS poi;
    DROP TABLE IF EXISTS properties;
    DROP TABLE IF EXISTS categories;

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
        category_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories(id),
        INDEX (status),
        INDEX (price)
    );

    CREATE TABLE poi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
`);

// Seed categories
const cats = ["Rentals", "Buy", "Off Market", "Commercial", "Student Housing"];
for (const cat of cats) {
  db.prepare("INSERT OR REPLACE INTO categories (name, slug) VALUES (?, ?)").run(
    cat, 
    cat.toLowerCase().replace(/\s+/g, "-").trim()
  );
}

// Seed sample properties
const properties = [
  { title: "Modern Loft in Downtown", description: "Stunning 2-bedroom loft with high ceilings and large windows. Perfect for urban living.", location: "Downtown", price: 450000, bedrooms: 2, bathrooms: 1, sqft: 1200, amenities: "WiFi, Parking, Gym", images: '["https://picsum.photos/seed/loft1/800/600"]', status: "available" },
  { title: "Suburban Family Home", description: "Spacious 3-bedroom family home with large backyard and modern kitchen.", location: "Westside", price: 520000, bedrooms: 3, bathrooms: 2, sqft: 2100, amenities: "WiFi, Parking, Garden, Pool", images: '["https://picsum.photos/seed/home1/800/600"]', status: "available" },
  { title: "Cozy Studio Apartment", description: "Affordable studio with modern amenities. Great starter home or investment property.", location: "East End", price: 280000, bedrooms: 1, bathrooms: 0, sqft: 650, amenities: "WiFi, Parking", images: '["https://picsum.photos/seed/studio/800/600"]', status: "available" },
  { title: "Luxury Penthouse", description: "Ultra-luxury penthouse with panoramic city views and premium finishes.", location: "Downtown", price: 890000, bedrooms: 3, bathrooms: 2, sqft: 2400, amenities: "WiFi, Parking, Gym, Pool", images: '["https://picsum.photos/seed/penthouse1/800/600"]', status: "available" },
  { title: "Budget Friendly Room", description: "Private room in shared house. Perfect for students or young professionals.", location: "North End", price: 800, bedrooms: 0, bathrooms: 0, sqft: null, amenities: "WiFi", images: '["https://picsum.photos/seed/room1/800/600"]', status: "available" },
];

const insert = db.prepare("INSERT OR REPLACE INTO properties (title, description, location, price, bedrooms, bathrooms, sqft, amenities, images, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
for (const p of properties) {
  insert.run(p.title, p.description, p.location, p.price, p.bedrooms, p.bathrooms, p.sqft, p.amenities, p.images, p.status);
}

// Seed POIs
db.prepare("INSERT OR REPLACE INTO poi (name, description, url) VALUES (?, ?, ?)").run("City Park", "Large green space with playground, walking trails, and events.", "https://maps.google.com/search?q=city+park");
db.prepare("INSERT OR REPLACE INTO poi (name, description, url) VALUES (?, ?, ?)").run("Downtown Market", "Weekly farmers market featuring local produce and artisan foods.", "https://maps.google.com/search?q=downtown+market");

const count = db.prepare("SELECT COUNT(*) as count FROM properties").get().count;
console.log(`[Migrate] Database initialized with ${count} sample properties!`);
console.log("[Migrate] Migration completed successfully!");

// Close database when process exits
process.on("beforeExit", () => {
  console.log("[DB] Closing database connection");
  db.close();
});

export {}; // Ensure module exports something (empty)