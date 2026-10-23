-- Migration 005: richer property attributes from listing feeds
-- (floor area, plot size, £/m², tenure, ward/district, provenance).

ALTER TABLE properties
    ADD COLUMN IF NOT EXISTS floor_area_sqm   NUMERIC(8, 2),
    ADD COLUMN IF NOT EXISTS plot_size_sqm    NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS price_per_sqm    NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS tenure          TEXT,
    ADD COLUMN IF NOT EXISTS ward            TEXT,
    ADD COLUMN IF NOT EXISTS district        TEXT,
    ADD COLUMN IF NOT EXISTS source_url      TEXT,
    ADD COLUMN IF NOT EXISTS geo_precision   TEXT;

-- `district` was referenced by the search builder but only existed on
-- postcode_geo; properties needs its own copy for filtering.
CREATE INDEX IF NOT EXISTS idx_properties_district
    ON properties (district) WHERE district IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_properties_ward
    ON properties (ward) WHERE ward IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_properties_floor_area
    ON properties (floor_area_sqm) WHERE floor_area_sqm IS NOT NULL;

-- Supports "£/m²" comparisons and value-based ranking.
CREATE INDEX IF NOT EXISTS idx_properties_price_per_sqm
    ON properties (price_per_sqm) WHERE price_per_sqm IS NOT NULL;
