-- Migration 008: listings get their own id range
--
-- properties.id and listings.id both started at 1, so /property/{id} could
-- return an agent listing when the caller meant a sold record (resolve_property
-- checks listings first). Observed in the eval harness: property 1 was shadowed
-- by a demo upload.
--
-- The JSON fallback store already starts listings at 900_001; PostgreSQL now
-- reserves 1_000_001+ so the two id spaces can never overlap. Rows created
-- before this migration keep their ids, so any pre-existing listing below
-- 1_000_000 should be re-imported (or renumbered) before launch.

CREATE SEQUENCE IF NOT EXISTS listings_public_id_seq
    MINVALUE 1000001
    START WITH 1000001;

ALTER SEQUENCE listings_public_id_seq OWNED BY listings.id;

ALTER TABLE listings
    ALTER COLUMN id SET DEFAULT nextval('listings_public_id_seq');

COMMENT ON SEQUENCE listings_public_id_seq IS
    'Listing ids start at 1_000_001 so they never collide with properties.id';
