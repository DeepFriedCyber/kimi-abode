-- Migration 006: agent-uploaded listings (live inventory, distinct from sold data).

CREATE TABLE IF NOT EXISTS listings (
    id                SERIAL PRIMARY KEY,
    agent_id          TEXT NOT NULL,
    agent_ref         TEXT,
    address_line1     TEXT NOT NULL,
    address_line2     TEXT,
    town              TEXT,
    postcode          TEXT,
    outcode           TEXT,
    property_type     TEXT,
    num_beds          INTEGER,
    num_bathrooms     INTEGER,
    asking_price      NUMERIC(12, 2),
    price_qualifier   TEXT,
    price_period      TEXT,
    price_paid        NUMERIC(12, 2),
    date_sold         DATE,
    listing_status    TEXT NOT NULL DEFAULT 'available',
    tenure            TEXT,
    floor_area_sqm    NUMERIC(8, 2),
    plot_size_sqm     NUMERIC(10, 2),
    description       TEXT,
    features          JSONB NOT NULL DEFAULT '[]'::jsonb,
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    ward              TEXT,
    district          TEXT,
    source            TEXT,
    source_url        TEXT,
    listed_at         DATE,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Stable key for upserts: postcode may be missing, so coalesce it.
    dedupe_key        TEXT GENERATED ALWAYS AS (
                          lower(address_line1) || '|' || coalesce(postcode, '')
                      ) STORED
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_agent_dedupe
    ON listings (agent_id, dedupe_key);

CREATE INDEX IF NOT EXISTS idx_listings_status
    ON listings (listing_status, town);

CREATE INDEX IF NOT EXISTS idx_listings_price
    ON listings (asking_price) WHERE asking_price IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_listings_postcode
    ON listings (postcode) WHERE postcode IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_listings_beds
    ON listings (num_beds) WHERE num_beds IS NOT NULL;

-- Full-text search over the marketing description (agent uploads give us this,
-- unlike Land Registry data).
CREATE INDEX IF NOT EXISTS idx_listings_search
    ON listings USING gin(
        to_tsvector('english',
            coalesce(address_line1, '') || ' ' ||
            coalesce(town, '') || ' ' ||
            coalesce(description, ''))
    );
