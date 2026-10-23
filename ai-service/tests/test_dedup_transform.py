"""Deduplication and ingestion transform tests."""

from __future__ import annotations

from app.ingestion.dedup import (
    addresses_match,
    deduplicate_listings,
    normalise_address,
)
from app.ingestion.transform import transform_listing


class TestAddressNormalisation:
    def test_expands_abbreviations(self):
        assert normalise_address("23 Station Rd") == normalise_address("23 Station Road")

    def test_strips_unit_prefix(self):
        assert normalise_address("Flat 2, 23 Station Road") == "23 station road"


class TestHouseNumbers:
    def test_different_numbers_are_never_merged(self):
        # Regression: the old heuristic merged numbers within 5 of each other.
        assert not addresses_match("23 Station Road", "25 Station Road")
        assert not addresses_match("1 High Street", "4 High Street")

    def test_same_number_matches(self):
        assert addresses_match("23 Station Road", "23 Station Rd")

    def test_flat_prefix_does_not_create_a_conflict(self):
        assert addresses_match("Flat 2, 23 Station Road", "23 Station Road")

    def test_deduplicate_keeps_both_numbers(self):
        listings = [
            {"address_line1": "23 Station Road", "num_beds": 3},
            {"address_line1": "25 Station Road", "num_beds": 3},
        ]
        assert len(deduplicate_listings(listings)) == 2

    def test_merges_missing_fields(self):
        listings = [
            {"address_line1": "23 Station Road", "num_beds": 3},
            {"address_line1": "23 Station Rd", "postcode": "CW11 1JD"},
        ]
        merged = deduplicate_listings(listings)
        assert len(merged) == 1
        assert merged[0]["num_beds"] == 3
        assert merged[0]["postcode"] == "CW11 1JD"

    def test_same_street_in_different_postcodes_is_not_merged(self):
        listings = [
            {"address_line1": "23 Station Road", "postcode": "CW11 1AA"},
            {"address_line1": "23 Station Road", "postcode": "CW1 1AA"},
        ]
        assert len(deduplicate_listings(listings)) == 2


class TestTransform:
    def test_postcode_keeps_its_space(self):
        assert transform_listing({"address": "1 A St", "postcode": "cw111jd"})["postcode"] == "CW11 1JD"

    def test_outcode_only_is_preserved(self):
        assert transform_listing({"address": "1 A St", "postcode": "cw11"})["postcode"] == "CW11"

    def test_invalid_long_postcode_is_left_uppercase(self):
        assert transform_listing({"address": "1 A St", "postcode": "notapostcode"})["postcode"] == "NOTAPOSTCODE"

    def test_price_formats(self):
        assert transform_listing({"address": "1 A St", "price": "£250,000"})["price_paid"] == 250000.0
        assert transform_listing({"address": "1 A St", "price": "n/a"})["price_paid"] is None

    def test_beds_from_text(self):
        assert transform_listing({"address": "1 A St", "beds": "3 bedroom"})["num_beds"] == 3
        assert transform_listing({"address": "1 A St", "beds": None})["num_beds"] is None
