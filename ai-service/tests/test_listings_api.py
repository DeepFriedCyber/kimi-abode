"""Agent listing upload API tests — dry run, commit, auth, formats."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

CSV_TWO = (
    "Address,Town,Postcode,Price,Bedrooms,Type,Description\n"
    '"1 Agent Way, CW11 1JD",Sandbach,CW11 1JD,450000,4,Detached,"Lovely garden"\n'
    '"2 Agent Way, CW11 1JD",Sandbach,CW11 1JD,375000,3,Semi-Detached,"Near station"\n'
)


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from app.ingestion import agent_store
    from app.routers import listings as listings_router

    store = agent_store.ListingStore(tmp_path / "agent_listings.json")
    monkeypatch.setattr(agent_store, "listing_store", store)
    monkeypatch.setattr(listings_router, "listing_store", store)
    monkeypatch.setattr(listings_router, "enrich_postcodes", lambda postcodes: {})
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    listings_router._limiter._buckets.clear()
    return store


def upload(client, content: bytes, filename: str = "listings.csv", **form):
    data = {"dry_run": "true", **{key: str(value) for key, value in form.items()}}
    return client.post(
        "/listings/import",
        files={"file": (filename, content, "application/octet-stream")},
        data=data,
    )


class TestDryRunAndCommit:
    def test_dry_run_previews_without_writing(self, client, isolated):
        response = upload(client, CSV_TWO.encode())

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["received"] == 2
        assert body["valid"] == 2
        assert body["imported"] == 0
        assert len(body["preview"]) == 2
        assert body["preview"][0]["asking_price"] == 450000
        assert isolated.count() == 0

    def test_commit_writes_and_is_idempotent(self, client, isolated):
        first = upload(client, CSV_TWO.encode(), dry_run="false")
        assert first.status_code == 200
        assert first.json()["imported"] == 2
        assert isolated.count() == 2

        second = upload(client, CSV_TWO.encode(), dry_run="false")
        assert second.json()["imported"] == 2
        assert isolated.count() == 2  # updated, not duplicated

        stored = isolated.all_listings()[0]
        assert stored["agent_id"] == "anonymous"
        assert stored["listing_status"] == "available"

    def test_partial_import_and_row_numbers(self, client, isolated):
        content = (
            "Address,Price\n"
            "1 Good Road,200000\n"
            ",150000\n"
            "3 Also Good,220000\n"
        ).encode()
        response = upload(client, content, dry_run="false")

        body = response.json()
        assert body["valid"] == 2
        assert body["invalid"] == 1
        assert body["imported"] == 2
        # Header is row 1, so the missing-address row is row 3.
        assert any(issue["row"] == 3 for issue in body["errors"])
        assert isolated.count() == 2

    def test_duplicate_rows_in_one_file(self, client, isolated):
        content = (
            "Address,Postcode,Price\n"
            "1 Same Road,CW11 1AA,200000\n"
            "1 Same Road,CW11 1AA,210000\n"
        ).encode()
        response = upload(client, content)
        body = response.json()
        assert body["duplicates"] == 1
        assert body["valid"] == 1

    def test_column_mapping_is_reported(self, client):
        content = b"Property Address,Guide Price,Bedrooms,Internal Notes\n1 A Road,200000,3,x\n"
        body = upload(client, content).json()
        assert body["columns"]["address"] == "Property Address"
        assert body["columns"]["price"] == "Guide Price"
        assert "Internal Notes" in body["unmapped_columns"]

    def test_mapping_override(self, client, isolated):
        content = b"Addr,Cost\n1 Override Road,310000\n"
        response = upload(
            client,
            content,
            dry_run="false",
            mapping=json.dumps({"address": "Addr", "price": "Cost"}),
        )
        assert response.json()["imported"] == 1
        assert isolated.all_listings()[0]["asking_price"] == 310000

    def test_rejects_empty_and_oversized_payloads(self, client, monkeypatch):
        from app.routers import listings as listings_router

        empty = upload(client, b"")
        assert empty.status_code == 400

        monkeypatch.setattr(listings_router, "MAX_UPLOAD_BYTES", 10)
        oversized = upload(client, b"Address,Price\n1 A,2\n" + b"x" * 50)
        assert oversized.status_code == 413

    def test_rejects_invalid_mapping_json(self, client):
        response = upload(client, CSV_TWO.encode(), mapping="{not-json")
        assert response.status_code == 400


class TestFormats:
    def test_xlsx_upload(self, client, isolated):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Address", "Asking Price", "Bedrooms", "Postcode"])
        sheet.append(["7 Excel Road", 325000, 4, "CW11 1JD"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        response = upload(
            client,
            buffer.getvalue(),
            filename="listings.xlsx",
            dry_run="false",
        )
        assert response.json()["format"] == "xlsx"
        assert response.json()["imported"] == 1
        assert isolated.all_listings()[0]["num_beds"] == 4

    def test_json_upload(self, client):
        payload = json.dumps(
            [{"address": "8 Json Road", "price": 400000, "bedrooms": 4}]
        ).encode()
        body = upload(client, payload, filename="listings.json").json()
        assert body["format"] == "json"
        assert body["valid"] == 1

    def test_text_paste(self, client):
        response = client.post(
            "/listings/import/text",
            json={"text": "Lovely 3 bed semi in Sandbach, CW11 1JD. Offers over £325,000."},
        )
        body = response.json()
        assert response.status_code == 200
        assert body["format"] == "text"
        assert body["valid"] == 1
        assert body["preview"][0]["asking_price"] == 325000
        assert body["preview"][0]["num_beds"] == 3

    def test_templates(self, client):
        csv_response = client.get("/listings/import/template", params={"format": "csv"})
        assert csv_response.status_code == 200
        assert csv_response.text.startswith("Address,Town,Postcode")

        xlsx_response = client.get("/listings/import/template", params={"format": "xlsx"})
        assert xlsx_response.status_code == 200
        assert xlsx_response.content[:2] == b"PK"

    def test_column_catalogue(self, client):
        body = client.get("/listings/import/columns").json()
        assert "address" in body["canonical"]
        assert "csv" in body["formats"]


class TestAuthAndIdentity:
    def test_api_key_required_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("AGENT_API_KEY", "super-secret-key")

        unauthorized = upload(client, CSV_TWO.encode())
        assert unauthorized.status_code == 401

        authorized = client.post(
            "/listings/import",
            files={"file": ("listings.csv", CSV_TWO.encode(), "text/csv")},
            data={"dry_run": "true"},
            headers={"x-api-key": "super-secret-key"},
        )
        assert authorized.status_code == 200

    def test_agent_id_is_sanitised(self, client, isolated):
        client.post(
            "/listings/",
            json={"address": "9 Identity Road", "price": 250000},
            headers={"x-agent-id": "bad id!"},
        )
        assert isolated.all_listings()[0]["agent_id"] == "anonymous"

        client.post(
            "/listings/",
            json={"address": "10 Identity Road", "price": 260000},
            headers={"x-agent-id": "acme-lettings"},
        )
        agents = {item["agent_id"] for item in isolated.all_listings()}
        assert "acme-lettings" in agents

    def test_listing_list_is_scoped_to_the_caller(self, client, isolated, monkeypatch):
        client.post(
            "/listings/",
            json={"address": "1 Scoped Road", "price": 200000},
            headers={"x-agent-id": "agent-a"},
        )
        client.post(
            "/listings/",
            json={"address": "2 Scoped Road", "price": 210000},
            headers={"x-agent-id": "agent-b"},
        )

        monkeypatch.setenv("AGENT_API_KEY", "key-123")

        missing_identity = client.get("/listings/", headers={"x-api-key": "key-123"})
        assert missing_identity.status_code == 400

        scoped = client.get(
            "/listings/",
            headers={"x-api-key": "key-123", "x-agent-id": "agent-a"},
        )
        assert scoped.status_code == 200
        assert scoped.json()["total"] == 1
        assert scoped.json()["listings"][0]["agent_id"] == "agent-a"

        cross_agent = client.get(
            "/listings/",
            params={"agent_id": "agent-b"},
            headers={"x-api-key": "key-123", "x-agent-id": "agent-a"},
        )
        assert cross_agent.status_code == 403


class TestSingleListingAndSearch:
    def test_single_listing(self, client, isolated):
        response = client.post(
            "/listings/",
            json={
                "address_line1": "11 Single Road",
                "postcode": "CW11 1JD",
                "asking_price": 525000,
                "num_beds": 5,
                "property_type": "detached",
                "description": "Five bed detached with a large garden",
            },
            headers={"x-agent-id": "acme"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["imported"] == 1
        assert body["listing"]["asking_price"] == 525000
        assert isolated.count() == 1

    def test_single_listing_validation(self, client):
        response = client.post("/listings/", json={"price": 100000})
        assert response.status_code == 422
        assert "errors" in response.json()["detail"]

    def test_uploaded_listing_is_searchable_and_retrievable(self, client, isolated):
        created = client.post(
            "/listings/",
            json={
                "address_line1": "12 Searchable Road",
                "town": "Sandbach",
                "postcode": "CW11 1JD",
                "asking_price": 610000,
                "num_beds": 6,
                "property_type": "detached",
            },
        ).json()
        listing_id = isolated.all_listings()[0]["id"]

        search = client.get("/search", params={"query": "6 bed detached in Sandbach"})
        addresses = [item["address_line1"] for item in search.json()["properties"]]
        assert "12 Searchable Road" in addresses

        detail = client.get("/property", params={"id": listing_id})
        assert detail.status_code == 200
        assert detail.json()["address_line1"] == "12 Searchable Road"

        listing = client.get("/listings/").json()
        assert listing["total"] == 1
        assert listing["listings"][0]["id"] == listing_id

    def test_uploaded_listing_is_found_by_address_text(self, client, isolated):
        client.post(
            "/listings/",
            json={
                "address_line1": "77 Text Search Lane",
                "postcode": "CW11 1JD",
                "asking_price": 300000,
            },
        )
        response = client.get("/search", params={"query": "text search lane"})
        addresses = [item["address_line1"] for item in response.json()["properties"]]
        assert "77 Text Search Lane" in addresses

    def test_uploaded_listing_is_found_by_description(self, client, isolated):
        client.post(
            "/listings/",
            json={
                "address_line1": "5 Workshop Road",
                "postcode": "CW11 1JD",
                "asking_price": 280000,
                "description": "South facing garden with a workshop and studio",
            },
        )
        response = client.get("/search", params={"query": "workshop"})
        addresses = [item["address_line1"] for item in response.json()["properties"]]
        assert "5 Workshop Road" in addresses
