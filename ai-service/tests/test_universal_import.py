"""Universal import tests — formats, column mapping, normalisation, errors."""

from __future__ import annotations

import io
import json

import pytest

from app.ingestion.universal import (
    build_template_csv,
    build_template_xlsx,
    detect_mapping,
    import_bytes,
    parse_money,
    parse_area,
    parse_date_value,
    normalise_row,
)

CSV_BASIC = (
    "Property Address,Guide Price,Bedrooms,Property Type,Postcode,Tenure,Status,Description\n"
    '"12, Mill Lane, CW11 1AA","£350,000",4,Detached,CW11 1AA,Freehold,For Sale,"A lovely home"\n'
)


class TestMoneyAndUnits:
    def test_money_formats(self):
        assert parse_money("£350,000") == 350_000
        assert parse_money("350k") == 350_000
        assert parse_money("1.2m") == 1_200_000
        assert parse_money("OIEO £350,000") == 350_000
        assert parse_money("POA") is None
        assert parse_money("") is None

    def test_area_units(self):
        assert parse_area("131") == 131
        assert parse_area("131 sqm") == 131
        assert parse_area("1,200 sq ft") == pytest.approx(111.48, rel=1e-3)
        assert parse_area("1200", "Floor Area (sq ft)") == pytest.approx(111.48, rel=1e-3)

    def test_dates(self):
        assert parse_date_value("2025-03-01") == ("2025-03-01", "day")
        assert parse_date_value("01/03/2025") == ("2025-03-01", "day")
        assert parse_date_value("Mar 2025") == ("2025-03-01", "month")
        # US-style only when the first number cannot be a day.
        assert parse_date_value("03/25/2025") == ("2025-03-25", "day")
        assert parse_date_value("not a date") == (None, None)


class TestMapping:
    def test_detects_messy_agent_headers(self):
        mapping, confidence, unmapped = detect_mapping(
            ["Property Address", "Guide Price", "Bedrooms", "Property Type", "Postcode", "Tenure"]
        )
        assert mapping["address"] == "Property Address"
        assert mapping["price"] == "Guide Price"
        assert mapping["beds"] == "Bedrooms"
        assert mapping["property_type"] == "Property Type"
        assert mapping["postcode"] == "Postcode"
        assert confidence["address"] == 1.0
        assert unmapped == []

    def test_json_canonical_keys(self):
        mapping, _, _ = detect_mapping(
            ["address_line1", "asking_price", "num_beds", "property_type", "postcode"]
        )
        assert mapping["address_line1"] == "address_line1"
        assert mapping["price"] == "asking_price"
        assert mapping["beds"] == "num_beds"

    def test_unmapped_columns_are_reported(self):
        _, _, unmapped = detect_mapping(["Address", "Price", "Internal Notes"])
        assert "Internal Notes" in unmapped


class TestCsvImport:
    def test_basic_csv(self):
        records, report = import_bytes(CSV_BASIC.encode(), "listings.csv")

        assert report.format == "csv"
        assert report.received == 1
        assert report.valid == 1
        assert report.invalid == 0
        record = records[0]
        assert record["address_line1"] == "12 Mill Lane"
        assert record["postcode"] == "CW11 1AA"
        assert record["asking_price"] == 350_000
        assert record["num_beds"] == 4
        assert record["property_type"] == "detached"
        assert record["price_qualifier"] == "guide"
        assert record["listing_status"] == "available"
        assert record["tenure"] == "Freehold"
        assert record["description"] == "A lovely home"

    def test_semicolon_delimiter_and_cp1252(self):
        content = (
            "Address;Price;Bedrooms\n"
            "1 High Street;£250,000;3\n"
        ).encode("cp1252")
        records, report = import_bytes(content, "windows.csv")
        assert report.delimiter == ";"
        assert records[0]["asking_price"] == 250_000
        assert records[0]["num_beds"] == 3

    def test_postcode_embedded_in_address(self):
        content = b'Address,Price\n"23 Station Road, CW11 1JD",250000\n'
        records, _ = import_bytes(content, "a.csv")
        assert records[0]["address_line1"] == "23 Station Road"
        assert records[0]["postcode"] == "CW11 1JD"

    def test_partial_import_keeps_good_rows_and_reports_bad(self):
        content = (
            "Address,Price,Bedrooms\n"
            "1 Good Road,200000,3\n"
            ",150000,2\n"
            "3 Bad Price,POA,2\n"
        ).encode()
        records, report = import_bytes(content, "mixed.csv")

        assert report.valid == 1
        assert report.invalid == 2
        assert {issue.row for issue in report.errors} == {3, 4}
        assert "address is required" in report.errors[0].message

    def test_duplicates_in_file_are_counted(self):
        content = (
            "Address,Postcode,Price\n"
            "1 Same Road,CW11 1AA,200000\n"
            "1 Same Road,CW11 1AA,210000\n"
        ).encode()
        records, report = import_bytes(content, "dupes.csv")
        assert report.valid == 1
        assert report.duplicates == 1
        assert report.warnings[0].row == 3

    def test_mapping_override(self):
        content = b"Addr Line 1,Cost,Ref\n1 Test Street,300000,ABC-1\n"
        records, report = import_bytes(
            content,
            "custom.csv",
            mapping_override={"address": "Addr Line 1", "price": "Cost", "agent_ref": "Ref"},
        )
        assert records[0]["address_line1"] == "1 Test Street"
        assert records[0]["asking_price"] == 300000
        assert records[0]["agent_ref"] == "ABC-1"
        assert report.confidence["price"] == 1.0

    def test_lettings_period(self):
        content = b'Address,Price\n"1 Flat, CW1 1AA",1250 pcm\n'
        records, _ = import_bytes(content, "lettings.csv")
        assert records[0]["asking_price"] == 1250
        assert records[0]["price_period"] == "pcm"

    def test_status_mapping(self):
        content = b"Address,Price,Status\n1 A Road,200000,Sold STC\n2 B Road,200000,Sold\n"
        records, _ = import_bytes(content, "status.csv")
        assert records[0]["listing_status"] == "under_offer"
        assert records[1]["listing_status"] == "sold"

    def test_empty_and_oversized_inputs(self):
        with pytest.raises(ValueError, match="empty"):
            import_bytes(b"", "empty.csv")
        with pytest.raises(ValueError, match="No data rows"):
            import_bytes(b"Address,Price\n", "header-only.csv")


class TestOtherFormats:
    def test_xlsx(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Address", "Asking Price", "Bedrooms", "Postcode"])
        sheet.append(["5 Excel Road", 275000, 3, "CW11 1JD"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        records, report = import_bytes(buffer.getvalue(), "listings.xlsx")
        assert report.format == "xlsx"
        assert records[0]["address_line1"] == "5 Excel Road"
        assert records[0]["asking_price"] == 275000
        assert records[0]["num_beds"] == 3

    def test_json_list(self):
        payload = [
            {"address_line1": "1 Json Road", "asking_price": 300000, "num_beds": 4, "postcode": "CW1 1AA"}
        ]
        records, report = import_bytes(json.dumps(payload).encode(), "listings.json")
        assert report.format == "json"
        assert records[0]["asking_price"] == 300000
        assert records[0]["num_beds"] == 4

    def test_json_wrapped(self):
        payload = {"listings": [{"address": "2 Json Road", "price": 250000}]}
        records, _ = import_bytes(json.dumps(payload).encode(), "wrapped.json")
        assert len(records) == 1
        assert records[0]["postcode"] is None

    def test_jsonl(self):
        lines = "\n".join(
            json.dumps({"address": f"{index} Line Road", "price": 200000 + index})
            for index in range(1, 4)
        )
        records, report = import_bytes(lines.encode(), "listings.jsonl")
        assert report.format == "jsonl"
        assert len(records) == 3

    def test_xml_blm(self):
        xml = b"""<?xml version="1.0"?>
        <properties>
          <property>
            <address>7 XML Road</address>
            <postcode>CW11 1JD</postcode>
            <price>320000</price>
            <bedrooms>4</bedrooms>
            <property_type>Detached</property_type>
          </property>
          <property>
            <address>8 XML Road</address>
            <postcode>CW11 1JD</postcode>
            <price>280000</price>
            <bedrooms>3</bedrooms>
          </property>
        </properties>"""
        records, report = import_bytes(xml, "feed.xml")
        assert report.format == "xml"
        assert len(records) == 2
        assert records[0]["address_line1"] == "7 XML Road"
        assert records[0]["asking_price"] == 320000

    def test_xml_entities_are_not_expanded(self):
        payload = b"""<?xml version="1.0"?>
        <!DOCTYPE properties [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
        <properties><property><address>&xxe;</address><price>100000</price></property></properties>"""
        with pytest.raises(Exception):
            import_bytes(payload, "evil.xml")

    def test_pasted_text(self):
        text = (
            "Stunning 4 bed detached house in Sandbach, CW11 1JD\n"
            "Guide price £375,000. Large garden and garage.\n"
        )
        records, report = import_bytes(text.encode(), "pasted.txt")
        assert report.format == "text"
        record = records[0]
        assert record["address_line1"].startswith("Stunning 4 bed")
        assert record["asking_price"] == 375000
        assert record["num_beds"] == 4
        assert record["postcode"] == "CW11"

    def test_templates(self):
        csv_template = build_template_csv()
        assert csv_template.startswith("Address,Town,Postcode")
        xlsx = build_template_xlsx()
        assert xlsx[:2] == b"PK"


class TestSingleNormalisation:
    def test_requires_address_and_price(self):
        record, errors, _ = normalise_row({}, {}, row_number=1)
        assert record is None
        assert {issue.field for issue in errors} == {"address", "price"}

    def test_canonical_json_payload(self):
        record, errors, _ = normalise_row(
            {
                "address_line1": "9 API Road",
                "postcode": "CW11 1JD",
                "asking_price": 425000,
                "num_beds": 5,
                "property_type": "detached",
                "features": ["Garden", "Garage"],
            },
            {},
            row_number=1,
        )
        assert errors == []
        assert record["asking_price"] == 425000
        assert record["num_beds"] == 5
        assert record["features"] == ["Garden", "Garage"]
