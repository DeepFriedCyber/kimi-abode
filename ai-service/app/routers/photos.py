"""Listing photos — upload, list, delete and set cover.

Files are validated and re-encoded by app.media. Ownership is enforced against
the listing's `agent_id`; a caller can only modify their own inventory.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from ..ingestion.agent_store import listing_store
from ..media import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_REQUEST,
    MAX_PHOTOS_PER_LISTING,
    MediaError,
    delete_photos,
    save_photo,
)
from .listings import _agent_id, _check_rate, _require_key

logger = logging.getLogger(__name__)
router = APIRouter()

PHOTO_ID_RE = re.compile(r"^[a-f0-9]{16}$")


async def _owned_listing(request: Request, listing_id: int, agent_id: str) -> dict:
    """Load a listing and assert the caller owns it."""
    pool = getattr(request.app.state, "pool", None)

    if pool is not None:
        from ..repository import fetch_listing_owner

        owner = await fetch_listing_owner(pool, listing_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="Listing not found")
        if owner != agent_id:
            raise HTTPException(status_code=403, detail="Not your listing")
        return {"id": listing_id, "agent_id": owner}

    record = listing_store.get_by_id(listing_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    if record.get("agent_id") != agent_id:
        raise HTTPException(status_code=403, detail="Not your listing")
    return record


def _validate_photo_id(photo_id: str) -> str:
    if not PHOTO_ID_RE.match(photo_id):
        raise HTTPException(status_code=400, detail="Invalid photo id")
    return photo_id


@router.post("/{listing_id}/photos")
async def upload_photos(
    request: Request,
    listing_id: int,
    files: Annotated[list[UploadFile], File(description="JPEG, PNG or WebP photos")],
    cover: Annotated[bool, Form()] = False,
):
    """Upload one or more photos for a listing. Duplicates are ignored."""
    _require_key(request)
    agent_id = _agent_id(request)
    _check_rate(agent_id)

    listing = await _owned_listing(request, listing_id, agent_id)
    existing = listing.get("photos", []) if isinstance(listing, dict) else []

    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        from ..repository import list_listing_photos

        before_count = len(await list_listing_photos(pool, listing_id))
    else:
        before_count = len(existing)

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_FILES_PER_REQUEST} photos per request",
        )
    if before_count + len(files) > MAX_PHOTOS_PER_LISTING:
        raise HTTPException(
            status_code=422,
            detail=f"A listing can have at most {MAX_PHOTOS_PER_LISTING} photos",
        )

    processed: list[dict] = []
    try:
        for upload in files:
            content = await upload.read(MAX_FILE_BYTES + 1)
            photo = save_photo(content, listing_id)
            processed.append({**photo.as_dict(), "hash": photo.hash, "display_path": photo.display_path, "thumb_path": photo.thumb_path})
    except MediaError as exc:
        delete_photos(listing_id, processed)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception:
        delete_photos(listing_id, processed)
        raise

    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        from ..repository import (
            insert_listing_photo,
            list_listing_photos,
            set_cover_photo,
        )

        for photo in processed:
            await insert_listing_photo(pool, listing_id, photo)

        photos = await list_listing_photos(pool, listing_id)
        target = processed[0]["id"] if (cover or not any(p["is_cover"] for p in photos)) else None
        if target and await set_cover_photo(pool, listing_id, target):
            photos = await list_listing_photos(pool, listing_id)
    else:
        record = listing_store.add_photos(listing_id, processed)
        photos = (record or {}).get("photos", [])
        if cover and processed:
            updated = listing_store.set_cover_photo(listing_id, processed[0]["id"])
            photos = (updated or {}).get("photos", photos)

    added = max(0, len(photos) - before_count)
    return {"added": added, "total": len(photos), "photos": photos}


@router.get("/{listing_id}/photos")
async def get_photos(request: Request, listing_id: int):
    """List photos for a listing (public)."""
    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        from ..repository import list_listing_photos

        return {"photos": await list_listing_photos(pool, listing_id)}

    record = listing_store.get_by_id(listing_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return {"photos": record.get("photos", [])}


@router.delete("/{listing_id}/photos/{photo_id}")
async def delete_photo(request: Request, listing_id: int, photo_id: str):
    """Delete a photo. If it was the cover, the first remaining photo becomes one."""
    _require_key(request)
    agent_id = _agent_id(request)
    _validate_photo_id(photo_id)
    await _owned_listing(request, listing_id, agent_id)

    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        from ..repository import delete_listing_photo, list_listing_photos

        removed = await delete_listing_photo(pool, listing_id, photo_id)
        if removed is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        delete_photos(listing_id, [removed])
        photos = await list_listing_photos(pool, listing_id)
    else:
        removed = listing_store.remove_photo(listing_id, photo_id)
        if removed is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        delete_photos(listing_id, [removed])
        record = listing_store.get_by_id(listing_id) or {}
        photos = record.get("photos", [])

    return {"deleted": photo_id, "total": len(photos), "photos": photos}


@router.post("/{listing_id}/photos/{photo_id}/cover")
async def set_cover(request: Request, listing_id: int, photo_id: str):
    """Mark a photo as the listing's cover image."""
    _require_key(request)
    agent_id = _agent_id(request)
    _validate_photo_id(photo_id)
    await _owned_listing(request, listing_id, agent_id)

    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        from ..repository import list_listing_photos, set_cover_photo

        if not await set_cover_photo(pool, listing_id, photo_id):
            raise HTTPException(status_code=404, detail="Photo not found")
        return {"photos": await list_listing_photos(pool, listing_id)}

    record = listing_store.set_cover_photo(listing_id, photo_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return {"photos": record.get("photos", [])}
