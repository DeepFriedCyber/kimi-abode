"""HouseMetric CSV ingestion tests (no network access)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from app.ingestion.housemetric import (
    ImportReport,
    build_record,
    canonical_type,
    derive_town,
    import_csv,
    outcode_of,
    parse_month,
    parse_number,
    split_postcode,
)

HEADER = [
    "Address", "URL", "Last sold", "Price paid", "Floor area",
    "£ per square metre", "Type", "Beds", "Tenure", "Plot size",
]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


class TestParsing:
    def test_split_postcode_with_commas(self):
        street, postcode = split_postcode("51, Cloverfields, CW1 5AL")
        assert street == "51 Cloverfields"
        assert postcode == "CW1 5AL"
        assert outcode_of(postcode) == "CW1"

    def test_split_postcode_without_comma(self):
        street, postcode = split_postcode("10 St Johns Way CW11 2LY")
        assert street == "10 St Johns Way"
        assert postcode == "CW11 2LY"

    def test_split_postcode_absent(self):
        street, postcode = split_postcode("Somewhere without a postcode")
        assert postcode is None
        assert street == "Somewhere without a postcode"

    def test_canonical_types(self):
        assert canonical_type("Terrace") == "terraced"
        assert canonical_type("Semi-D") == "semi-detached"
        assert canonical_type("Detached") == "detached"
        assert canonical_type("Detached Bungalow") == "bungalow"
        assert canonical_type("Semi-D Bungalow") == "bungalow"
        assert canonical_type("Flat") == "flat"
        assert canonical_type("Other") == "other"
        assert canonical_type(None) == "other"

    def test_parse_month(self):
        assert parse_month("Mar 2025") == "2025-03-01"
        assert parse_month("Dec 2024") == "2024-12-01"
        assert parse_month("not a date") is None
        assert parse_month(None) is None

    def test_parse_number(self):
        assert parse_number("387,000") == 387000
        assert parse_number("£1,065,000") == 1065000
        assert parse_number("") is None
        assert parse_number("n/a") is None
        assert parse_number("0") is None

    def test_derive_town_keeps_multiword_wards(self):
        assert derive_town("Odd Rode", None, "Cheshire East") == "Odd Rode"
        assert derive_town("Sandbach Elworth", None, "Cheshire East") == "Sandbach"
        assert derive_town(None, "Haslington", "Cheshire East") == "Haslington"


class TestBuildRecord:
    def test_builds_canonical_record(self):
        record = build_record(
            {
                "Address": "51, Cloverfields, CW1 5AL",
                "URL": "https://housemetric.co.uk/30430832/CW1-5AL/51",
                "Last sold": "Mar 2025",
                "Price paid": "387000",
                "Floor area": "131",
                "£ per square metre": "2954",
                "Type": "Detached",
                "Beds": "4",
                "Tenure": "Freehold",
                "Plot size": "333",
            },
            {
                "admin_district": "Cheshire East",
                "admin_ward": "Haslington",
                "parish": "Haslington",
                "latitude": 53.097675,
                "longitude": -2.405048,
            },
        )

        assert record["address_line1"] == "51 Cloverfields"
        assert record["postcode"] == "CW1 5AL"
        assert record["outcode"] == "CW1"
        assert record["town"] == "Haslington"
        assert record["property_type"] == "detached"
        assert record["num_beds"] == 4
        assert record["price_paid"] == 387000
        assert record["floor_area_sqm"] == 131
        assert record["plot_size_sqm"] == 333
        assert record["price_per_sqm"] == pytest.approx(2954.2)
        assert record["date_sold"] == "2025-03-01"
        assert record["sold_precision"] == "month"
        assert record["latitude"] == pytest.approx(53.097675)
        assert record["source_url"].startswith("https://housemetric.co.uk/")

    def test_missing_fields_are_null(self):
        record = build_record({"Address": "1 Nowhere, CW1 1AA", "Price paid": "100000"})
        assert record["num_beds"] is None
        assert record["floor_area_sqm"] is None
        assert record["price_per_sqm"] is None
        assert record["date_sold"] is None


class TestImportCsv:
    def test_import_dedupes_and_geocodes(self, tmp_path):
        csv_path = tmp_path / "listings.csv"
        write_csv(
            csv_path,
            [
                ["51, Cloverfields, CW1 5AL", "u1", "Mar 2025", "387000", "131", "2954", "Detached", "4", "Freehold", "333"],
                ["51 Cloverfields, CW1 5AL", "u2", "Mar 2025", "387000", "131", "2954", "Detached", "", "Freehold", ""],
                # Same street/number, different postcode: must not merge.
                ["51 Cloverfields, CW11 1JD", "u3", "Feb 2025", "250000", "90", "2778", "Terrace", "3", "Freehold", ""],
                # Unresolved postcode -> outcode centroid fallback.
                ["9 Unknown Road, CW10 9PU", "u4", "Jan 2025", "200000", "80", "2500", "Flat", "2", "Freehold", ""],
            ],
        )

        def fake_postcodes(postcodes):
            data = {
                "CW1 5AL": {"admin_ward": "Haslington", "latitude": 53.1, "longitude": -2.4},
                "CW11 1JD": {"admin_ward": "Sandbach Elworth", "latitude": 53.14, "longitude": -2.38},
            }
            return {code: data[code] for code in postcodes if code in data}

        def fake_outcodes(outcodes):
            return {code: {"latitude": 53.19, "longitude": -2.44} for code in outcodes}

        records, report = import_csv(
            str(csv_path),
            enrich=True,
            postcode_fetcher=fake_postcodes,
            outcode_fetcher=fake_outcodes,
        )

        assert isinstance(report, ImportReport)
        assert report.input_rows == 4
        assert report.invalid == 0
        assert report.duplicates == 1
        assert report.postcodes_resolved == 2
        assert report.outcodes_resolved == 1
        assert len(records) == 3

        merged = next(r for r in records if r["postcode"] == "CW1 5AL")
        assert merged["num_beds"] == 4  # back-filled from the duplicate

        fallback = next(r for r in records if r["postcode"] == "CW10 9PU")
        assert fallback["geo_precision"] == "outcode"
        assert fallback["latitude"] == pytest.approx(53.19)

    def test_import_without_enrichment(self, tmp_path):
        csv_path = tmp_path / "one.csv"
        write_csv(
            csv_path,
            [["1 Test Street, CW1 1AA", "u", "Jan 2025", "150000", "70", "2143", "Flat", "2", "Freehold", ""]],
        )
        records, report = import_csv(str(csv_path), enrich=False)
        assert len(records) == 1
        assert records[0]["latitude"] is None
        assert report.postcodes_resolved == 0
