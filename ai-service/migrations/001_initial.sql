-- Migration 001: Initial schema — properties and sales tables

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS properties (
    id              SERIAL PRIMARY KEY,
    address_line1   TEXT NOT NULL,
    address_line2   TEXT,
    town            TEXT,
    postcode        TEXT,
    outcode         TEXT,
    property_type   TEXT,
    num_beds        INTEGER,
    price_paid      NUMERIC(12, 2),
    date_sold       DATE,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    embedding       vector(768),
    source          TEXT DEFAULT 'land-registry',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_addr_postcode
    ON properties (address_line1, postcode);

CREATE INDEX IF NOT EXISTS idx_properties_town ON properties (town) WHERE town IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_properties_outcode ON properties (outcode) WHERE outcode IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_properties_type ON properties (property_type) WHERE property_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_properties_beds ON properties (num_beds) WHERE num_beds IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_properties_embedding ON properties USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- GIN index for text search on address/town
CREATE INDEX IF NOT EXISTS idx_properties_search_gin ON properties
    USING gin(to_tsvector('english', coalesce(address_line1, '') || ' ' || coalesce(town, '')));

-- Chat cache table (for caching LLM responses)
CREATE TABLE IF NOT EXISTS chat_cache (
    id          SERIAL PRIMARY KEY,
    query       TEXT NOT NULL,
    embedding   vector(768),
    result      JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_cache_embedding ON chat_cache USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
