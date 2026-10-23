"""JSON-backed store for agent-uploaded listings (development / demo mode).

In production uploads go to Postgres (`listings` table, migration 006); this
store keeps the feature usable without a database and makes the demo searchable
immediately. Writes are atomic and guarded by a lock.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(
    os.getenv(
        "AGENT_LISTINGS_PATH",
        str(Path(__file__).resolve().parent.parent.parent / "data" / "agent_listings.json"),
    )
)

FIRST_ID = 900_001  # keep clear of fixture ids (1..500)


class ListingStore:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._mtime: float = 0.0

    # -- internal ----------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return {"updated_at": None, "next_id": FIRST_ID, "listings": []}

        if self._cache is not None and mtime == self._mtime:
            return self._cache

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"updated_at": None, "next_id": FIRST_ID, "listings": []}

        payload.setdefault("next_id", FIRST_ID)
        payload.setdefault("listings", [])
        self._cache = payload
        self._mtime = mtime
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)
        self._cache = payload
        try:
            self._mtime = self.path.stat().st_mtime
        except OSError:
            self._mtime = 0.0

    @staticmethod
    def _key(record: dict[str, Any]) -> tuple[str, str]:
        return (
            (record.get("address_line1") or "").strip().lower(),
            (record.get("postcode") or "").strip().lower(),
        )

    # -- public API --------------------------------------------------------
    def upsert_many(self, records: list[dict[str, Any]], agent_id: str) -> dict[str, Any]:
        """Insert or update listings. Returns counts plus the affected ids."""
        created = 0
        updated = 0
        ids: list[int] = []

        with self._lock:
            payload = self._load()
            index = {self._key(item): position for position, item in enumerate(payload["listings"])}
            now = datetime.now(timezone.utc).isoformat()

            for record in records:
                key = self._key(record)
                cleaned = {k: v for k, v in record.items() if k != "source_row"}

                if key in index:
                    position = index[key]
                    existing = payload["listings"][position]
                    merged = {**existing, **{k: v for k, v in cleaned.items() if v not in (None, "", [])}}
                    merged["id"] = existing["id"]
                    merged["agent_id"] = agent_id
                    merged["updated_at"] = now
                    payload["listings"][position] = merged
                    updated += 1
                    ids.append(existing["id"])
                else:
                    listing_id = payload["next_id"]
                    payload["next_id"] = listing_id + 1
                    payload["listings"].append(
                        {
                            **cleaned,
                            "id": listing_id,
                            "agent_id": agent_id,
                            "ingested_at": now,
                            "updated_at": now,
                            "photos": [],
                        }
                    )
                    index[key] = len(payload["listings"]) - 1
                    created += 1
                    ids.append(listing_id)

            self._save(payload)

        return {"created": created, "updated": updated, "ids": ids}

    def all_listings(self) -> list[dict[str, Any]]:        return list(self._load()["listings"])

    def get_by_id(self, listing_id: int) -> dict[str, Any] | None:
        return next(
            (item for item in self._load()["listings"] if item.get("id") == listing_id),
            None,
        )

    def add_photos(self, listing_id: int, photos: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Attach processed photos to a listing (dedupe by photo id)."""
        from ..media import MAX_PHOTOS_PER_LISTING

        with self._lock:
            payload = self._load()
            for item in payload["listings"]:
                if item.get("id") != listing_id:
                    continue

                existing = item.setdefault("photos", [])
                known = {photo.get("id") for photo in existing}

                for photo in photos:
                    if photo.get("id") in known:
                        continue
                    if len(existing) >= MAX_PHOTOS_PER_LISTING:
                        break
                    existing.append(
                        {
                            **photo,
                            "position": len(existing),
                            "is_cover": len(existing) == 0,
                        }
                    )
                    known.add(photo.get("id"))

                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(payload)
                return item

        return None

    def remove_photo(self, listing_id: int, photo_id: str) -> dict[str, Any] | None:
        """Remove one photo and return its metadata (for file deletion)."""
        with self._lock:
            payload = self._load()
            for item in payload["listings"]:
                if item.get("id") != listing_id:
                    continue

                photos = item.get("photos", [])
                removed = next((photo for photo in photos if photo.get("id") == photo_id), None)
                if removed is None:
                    return None

                remaining = [photo for photo in photos if photo.get("id") != photo_id]
                for position, photo in enumerate(remaining):
                    photo["position"] = position

                had_cover = bool(removed.get("is_cover"))
                if remaining and (had_cover or not any(p.get("is_cover") for p in remaining)):
                    for photo in remaining:
                        photo["is_cover"] = False
                    remaining[0]["is_cover"] = True

                item["photos"] = remaining
                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(payload)
                return removed

        return None

    def set_cover_photo(self, listing_id: int, photo_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._load()
            for item in payload["listings"]:
                if item.get("id") != listing_id:
                    continue

                photos = item.get("photos", [])
                if not any(photo.get("id") == photo_id for photo in photos):
                    return None

                for photo in photos:
                    photo["is_cover"] = photo.get("id") == photo_id

                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(payload)
                return item

        return None

    def list(self, *, limit: int = 50, offset: int = 0, agent_id: str | None = None) -> dict[str, Any]:
        listings = self._load()["listings"]
        if agent_id:
            listings = [item for item in listings if item.get("agent_id") == agent_id]

        total = len(listings)
        page = listings[offset : offset + limit]
        return {"total": total, "limit": limit, "offset": offset, "listings": page}

    def count(self) -> int:
        return len(self._load()["listings"])

    def clear(self) -> None:
        with self._lock:
            self._save({"updated_at": None, "next_id": FIRST_ID, "listings": []})


listing_store = ListingStore()
