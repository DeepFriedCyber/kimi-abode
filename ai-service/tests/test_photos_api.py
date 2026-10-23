"""Listing photo API tests — upload, dedupe, cover, delete, ownership, serving."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


def jpeg_bytes(width: int = 800, height: int = 600, colour: tuple[int, int, int] = (40, 90, 160)) -> bytes:
    image = Image.new("RGB", (width, height), colour)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    import app.media as media
    import app.ingestion.agent_store as store_module
    from app.routers import listings as listings_router
    from app.routers import photos as photos_router

    store = store_module.ListingStore(tmp_path / "agent_listings.json")
    media_root = tmp_path / "media"
    monkeypatch.setattr(store_module, "listing_store", store)
    monkeypatch.setattr(listings_router, "listing_store", store)
    monkeypatch.setattr(photos_router, "listing_store", store)
    monkeypatch.setattr(media, "MEDIA_ROOT", media_root)
    media.ensure_media_root()
    monkeypatch.setattr(listings_router, "enrich_postcodes", lambda postcodes: {})
    listings_router._limiter._buckets.clear()
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    return {"store": store, "media": media_root}


def create_listing(client, *, agent: str = "acme", address: str = "1 Photo Road") -> int:
    response = client.post(
        "/listings/",
        json={
            "address_line1": address,
            "town": "Sandbach",
            "postcode": "CW11 1JD",
            "asking_price": 400000,
            "num_beds": 4,
            "property_type": "detached",
        },
        headers={"x-agent-id": agent},
    )
    assert response.status_code == 200, response.text
    return response.json()["listing"]["id"]


def upload(client, listing_id: int, images: list[bytes], *, cover: bool = False, agent: str = "acme"):
    files = [
        ("files", (f"photo-{index}.jpg", payload, "image/jpeg"))
        for index, payload in enumerate(images)
    ]
    return client.post(
        f"/listings/{listing_id}/photos",
        files=files,
        data={"cover": str(cover).lower()},
        headers={"x-agent-id": agent},
    )


class TestUpload:
    def test_uploads_and_generates_derivatives(self, client, isolated):
        listing_id = create_listing(client)
        response = upload(client, listing_id, [jpeg_bytes(), jpeg_bytes(colour=(200, 10, 10))])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["added"] == 2
        assert body["total"] == 2
        assert body["photos"][0]["is_cover"] is True
        assert body["photos"][0]["url"].startswith(f"/media/listings/{listing_id}/")

        photo = body["photos"][0]
        for url in (photo["url"], photo["thumb_url"]):
            served = client.get(url)
            assert served.status_code == 200
            assert served.headers["content-type"] == "image/webp"
            assert served.headers["cache-control"].startswith("public")
            assert len(served.content) > 100

    def test_reupload_is_idempotent(self, client, isolated):
        listing_id = create_listing(client)
        image = jpeg_bytes()
        first = upload(client, listing_id, [image]).json()
        second = upload(client, listing_id, [image]).json()

        assert first["total"] == 1
        assert second["added"] == 0
        assert second["total"] == 1

    def test_cover_flag_on_upload(self, client, isolated):
        listing_id = create_listing(client)
        upload(client, listing_id, [jpeg_bytes(colour=(10, 10, 10))])
        response = upload(client, listing_id, [jpeg_bytes(colour=(250, 250, 250))], cover=True)

        photos = response.json()["photos"]
        covers = [photo for photo in photos if photo["is_cover"]]
        assert len(covers) == 1
        assert covers[0]["id"] == photos[-1]["id"]

    def test_first_photo_becomes_cover(self, client, isolated):
        listing_id = create_listing(client)
        photos = upload(client, listing_id, [jpeg_bytes()]).json()["photos"]
        assert photos[0]["is_cover"] is True

    def test_rejects_non_images(self, client, isolated):
        listing_id = create_listing(client)
        response = client.post(
            f"/listings/{listing_id}/photos",
            files=[("files", ("evil.jpg", b"<svg onload=alert(1)></svg>", "image/jpeg"))],
            headers={"x-agent-id": "acme"},
        )
        assert response.status_code == 415

    def test_rejects_too_many_files(self, client, isolated):
        listing_id = create_listing(client)
        response = upload(client, listing_id, [jpeg_bytes(colour=(i, i, i)) for i in range(11)])
        assert response.status_code == 400

    def test_enforces_per_listing_cap(self, client, isolated, monkeypatch):
        from app.routers import photos as photos_router

        monkeypatch.setattr(photos_router, "MAX_PHOTOS_PER_LISTING", 2)
        listing_id = create_listing(client)
        assert upload(client, listing_id, [jpeg_bytes(colour=(1, 2, 3))]).status_code == 200
        response = upload(client, listing_id, [jpeg_bytes(colour=(4, 5, 6))] * 2)
        assert response.status_code == 422


class TestOwnership:
    def test_rejects_another_agent(self, client, isolated):
        listing_id = create_listing(client, agent="acme")
        response = upload(client, listing_id, [jpeg_bytes()], agent="other-agent")
        assert response.status_code == 403

    def test_unknown_listing(self, client, isolated):
        response = upload(client, 999_999, [jpeg_bytes()])
        assert response.status_code == 404

    def test_delete_requires_ownership(self, client, isolated):
        listing_id = create_listing(client, agent="acme")
        photo_id = upload(client, listing_id, [jpeg_bytes()]).json()["photos"][0]["id"]

        denied = client.delete(
            f"/listings/{listing_id}/photos/{photo_id}", headers={"x-agent-id": "other"}
        )
        assert denied.status_code == 403


class TestManage:
    def test_set_cover_and_delete(self, client, isolated):
        listing_id = create_listing(client)
        photos = upload(
            client,
            listing_id,
            [jpeg_bytes(colour=(10, 20, 30)), jpeg_bytes(colour=(200, 10, 10))],
        ).json()["photos"]

        cover_response = client.post(
            f"/listings/{listing_id}/photos/{photos[1]['id']}/cover",
            headers={"x-agent-id": "acme"},
        )
        assert cover_response.status_code == 200
        covers = [photo for photo in cover_response.json()["photos"] if photo["is_cover"]]
        assert covers[0]["id"] == photos[1]["id"]

        deleted = client.delete(
            f"/listings/{listing_id}/photos/{photos[1]['id']}",
            headers={"x-agent-id": "acme"},
        )
        assert deleted.status_code == 200
        remaining = deleted.json()["photos"]
        assert len(remaining) == 1
        assert remaining[0]["is_cover"] is True  # promoted

    def test_delete_unknown_photo(self, client, isolated):
        listing_id = create_listing(client)
        response = client.delete(
            f"/listings/{listing_id}/photos/0123456789abcdef",
            headers={"x-agent-id": "acme"},
        )
        assert response.status_code == 404

    def test_invalid_photo_id(self, client, isolated):
        listing_id = create_listing(client)
        response = client.delete(
            f"/listings/{listing_id}/photos/not-a-hash",
            headers={"x-agent-id": "acme"},
        )
        assert response.status_code == 400

    def test_list_and_property_include_photos(self, client, isolated):
        listing_id = create_listing(client)
        upload(client, listing_id, [jpeg_bytes()])

        listing = client.get("/listings/").json()["listings"][0]
        assert listing["id"] == listing_id
        assert len(listing["photos"]) == 1

        detail = client.get("/property", params={"id": listing_id}).json()
        assert detail["photos"][0]["is_cover"] is True

        public = client.get(f"/listings/{listing_id}/photos").json()
        assert len(public["photos"]) == 1

    def test_media_path_traversal_is_blocked(self, client):
        response = client.get("/media/listings/1/../../etc/passwd")
        assert response.status_code == 404
