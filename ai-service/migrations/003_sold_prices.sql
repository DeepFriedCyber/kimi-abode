-- Migration 003: Sold prices table (Land Registry data)

CREATE TABLE IF NOT EXISTS sales (
    id                  SERIAL PRIMARY KEY,
    property_address    TEXT NOT NULL,
    property_town       TEXT,
    postcode            TEXT,
    price_paid          NUMERIC(12, 2) NOT NULL,
    date_sold           DATE,
    property_type       TEXT,
    is_multi_property   BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sales_address ON sales (property_address);
CREATE INDEX IF NOT EXISTS idx_sales_town ON sales (property_town) WHERE property_town IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sales_postcode ON sales (postcode) WHERE postcode IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sales_price_range ON sales (price_paid) WHERE price_paid IS NOT NULL;
