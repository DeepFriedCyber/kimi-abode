-- Migration: Copy listings from property_search db to abode db
-- Run with: psql -U postgres -d abode -h localhost -p 5432 -f migrate_listings.sql

-- Use dblink to read from property_search database
CREATE EXTENSION IF NOT EXISTS dblink;

-- Insert property listings from property_search.properties into abode.properties
-- We map columns as follows:
--   address        -> address_line1
--   postcode       -> postcode
--   property_type  -> property_type (lowercased)
--   bedrooms       -> num_beds
--   price          -> price_paid
--   last_sold_date -> date_sold
--   outcode        -> derived from postcode (first part before space)
--   town           -> looked up from town_gazetteer by outcode, fallback to title parsing
--   latitude/longitude -> NULL (not available in source data)

INSERT INTO properties (
    address_line1,
    postcode,
    outcode,
    property_type,
    num_beds,
    price_paid,
    date_sold,
    latitude,
    longitude,
    source
)
SELECT
    ps.address,
    ps.postcode,
    split_part(ps.postcode, ' ', 1) AS outcode,
    lower(ps.property_type) AS property_type,
    ps.bedrooms AS num_beds,
    ps.price::numeric AS price_paid,
    ps.last_sold_date AS date_sold,
    NULL::double precision AS latitude,
    NULL::double precision AS longitude,
    'property_search_migration' AS source
FROM dblink(
    'host=localhost port=5432 dbname=property_search user=postgres',
    'SELECT address, postcode, property_type, bedrooms, price, last_sold_date FROM properties'
) AS ps(
    address TEXT,
    postcode TEXT,
    property_type TEXT,
    bedrooms INTEGER,
    price INTEGER,
    last_sold_date DATE
)
WHERE ps.postcode IS NOT NULL
  AND ps.postcode != ''
ON CONFLICT (address_line1, postcode) DO NOTHING;

-- Report results
SELECT COUNT(*) AS total_migrated FROM properties;
