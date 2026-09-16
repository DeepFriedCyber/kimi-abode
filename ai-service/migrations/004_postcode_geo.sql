-- Migration 004: Postcode geo data for town enrichment

CREATE TABLE IF NOT EXISTS postcode_geo (
    id          SERIAL PRIMARY KEY,
    postcode    TEXT UNIQUE NOT NULL,
    outcode     TEXT NOT NULL,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    district    TEXT,
    town        TEXT,
    country     TEXT,
    enriched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_postcode_geo_outcode ON postcode_geo (outcode);
CREATE INDEX IF NOT EXISTS idx_postcode_geo_town ON postcode_geo (town) WHERE town IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_postcode_geo_geo ON postcode_geo USING gist(
    ll_to_earth(latitude, longitude)
);

-- Town gazetteer table for fast town lookups
CREATE TABLE IF NOT EXISTS town_gazetteer (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    outcode     TEXT,
    district    TEXT,
    country     TEXT DEFAULT 'England',
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION
);

INSERT INTO town_gazetteer (name, outcode, district) VALUES
    ('Sandbach', 'CW11', 'Cheshire East'),
    ('Crewe', 'CW1', 'Crewe and Nantwich'),
    ('Nantwich', 'CW5', 'Cheshire East'),
    ('Macclesfield', 'SK10', 'Cheshire East'),
    ('Wilmslow', 'SK9', 'Cheshire East'),
    ('Knutsford', 'WA16', 'Cheshire East'),
    ('Eccleston', 'WA8', 'St Helens'),
    ('Congleton', 'CW12', 'Cheshire East')
ON CONFLICT (name) DO NOTHING;
