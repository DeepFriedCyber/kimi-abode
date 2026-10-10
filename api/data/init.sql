-- Initialize properties database schema and seed sample data

-- Drop existing tables if they exist (idempotent)
DROP TABLE IF EXISTS poi;
DROP TABLE IF EXISTS properties;
DROP TABLE IF EXISTS categories;

-- Create categories table
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create properties table with all necessary columns
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
    images TEXT,  -- JSON array of image URLs
    status TEXT DEFAULT 'available',  -- available, sold, rented, off_market
    category_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    INDEX (status),
    INDEX (price)
);

-- Create poi table for Points of Interest
CREATE TABLE poi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed categories
INSERT INTO categories (name, slug) VALUES
('Rentals', 'rentals'),
('Buy', 'buy'),
('Off Market', 'off-market'),
('Commercial', 'commercial'),
('Student Housing', 'student-housing');

-- Seed sample properties
INSERT INTO properties (title, description, location, price, bedrooms, bathrooms, sqft, amenities, images, status) VALUES
('Modern Loft in Downtown', 'Stunning 2-bedroom loft with high ceilings and large windows. Perfect for urban living.', 'Downtown', 450000.00, 2, 1, 1200.0, 'WiFi, Parking, Gym', '[\"https://picsum.photos/seed/loft1/800/600\"]', 'available'),
('Suburban Family Home', 'Spacious 3-bedroom family home with large backyard and modern kitchen.', 'Westside', 520000.00, 3, 2, 2100.0, 'WiFi, Parking, Garden, Pool', '[\"https://picsum.photos/seed/home1/800/600\", \"https://picsum.photos/seed/kitchen/800/600\"]', 'available'),
('Cozy Studio Apartment', 'Affordable studio with modern amenities. Great starter home or investment property.', 'East End', 280000.00, 1, 0, 650.0, 'WiFi, Parking', '[\"https://picsum.photos/seed/studio/800/600\"]', 'available'),
('Luxury Penthouse', 'Ultra-luxury penthouse with panoramic city views and premium finishes.', 'Downtown', 890000.00, 3, 2, 2400.0, 'WiFi, Parking, Gym, Pool, Doorman', '[\"https://picsum.photos/seed/penthouse1/800/600\"]', 'available'),
('Budget Friendly Room', 'Private room in shared house. Perfect for students or young professionals.', 'North End', 800.00, 0, 0, NULL, 'WiFi, Parking', '[\"https://picsum.photos/seed/room1/800/600\"]', 'available'),
('Investment Property', 'Multi-unit investment property with great rental income potential.', 'South Side', 350000.00, 4, 2, NULL, 'Parking, Laundry', '[\"https://picsum.photos/seed/investment1/800/600\"]', 'available');

-- Seed POIs
INSERT INTO poi (name, description, url) VALUES
('City Park', 'Large green space with playground, walking trails, and events.', 'https://maps.google.com/search?q=city+park'),
('Downtown Market', 'Weekly farmers market featuring local produce and artisan foods.', 'https://maps.google.com/search?q=downtown+market'),
('University Campus', 'Educational institution with excellent programs and student housing.', 'https://maps.google.com/search?q=university+campus');

-- Verification query
SELECT COUNT(*) as total_properties FROM properties;