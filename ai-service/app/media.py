"""Listing photo storage and processing.

Security posture:
  * the declared content type and filename are ignored — the image is decoded
    and its real format checked;
  * everything is re-encoded to WebP, which strips EXIF (including GPS) and
    neutralises polyglot files;
  * decompression bombs are bounded by pixel count and file size;
  * filenames are generated from a content hash (never client input);
  * derivatives are immutable, so they can be cached forever.

Storage is the local filesystem for now; the interface is small enough to swap
for S3 later.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

try:  # iPhone photos are HEIC/HEIF; register the decoder when available.
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - optional dependency
    pass

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(
    os.getenv(
        "MEDIA_ROOT",
        str(Path(__file__).resolve().parent.parent / "data" / "media"),
    )
)
MEDIA_URL_PREFIX = "/media"

MAX_FILE_BYTES = int(os.getenv("MEDIA_MAX_FILE_BYTES", str(12 * 1024 * 1024)))
MAX_FILES_PER_REQUEST = int(os.getenv("MEDIA_MAX_FILES", "10"))
MAX_PHOTOS_PER_LISTING = int(os.getenv("MEDIA_MAX_PER_LISTING", "20"))
MAX_PIXELS = int(os.getenv("MEDIA_MAX_PIXELS", "30_000_000"))
DISPLAY_MAX_EDGE = 1_600
THUMB_MAX_EDGE = 480

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC", "AVIF"}
SAFE_ID = re.compile(r"^[a-f0-9]{16}$")


class MediaError(Exception):
    """A user-facing media error with an HTTP status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class Photo:
    id: str
    hash: str
    width: int
    height: int
    bytes: int
    display_path: str
    thumb_path: str
    created_at: str
    is_cover: bool = False
    position: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": f"{MEDIA_URL_PREFIX}/{self.display_path}",
            "thumb_url": f"{MEDIA_URL_PREFIX}/{self.thumb_path}",
            "width": self.width,
            "height": self.height,
            "bytes": self.bytes,
            "is_cover": self.is_cover,
            "position": self.position,
        }


def ensure_media_root() -> Path:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    return MEDIA_ROOT


def _listing_dir(listing_id: int) -> Path:
    directory = MEDIA_ROOT / "listings" / str(int(listing_id))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _open_verified(content: bytes) -> Image.Image:
    """Decode the image, enforce format/pixel limits, and fix orientation."""
    if not content:
        raise MediaError(400, "Empty file")
    if len(content) > MAX_FILE_BYTES:
        raise MediaError(
            413, f"Each photo must be at most {MAX_FILE_BYTES // (1024 * 1024)} MB"
        )

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS

    try:
        with Image.open(io.BytesIO(content)) as probe:
            probe.verify()
    except Image.DecompressionBombError as exc:
        raise MediaError(413, "Image resolution is too large") from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise MediaError(415, "Not a supported image") from exc

    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Image.DecompressionBombError as exc:
        raise MediaError(413, "Image resolution is too large") from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise MediaError(415, "Image could not be decoded") from exc

    if image.format not in ALLOWED_FORMATS:
        raise MediaError(415, "Only JPEG, PNG and WebP photos are accepted")

    width, height = image.size
    if width * height > MAX_PIXELS:
        raise MediaError(413, "Image resolution is too large")
    if width < 200 or height < 200:
        raise MediaError(422, "Image is too small (minimum 200×200)")

    # Apply the EXIF orientation before the metadata is discarded.
    image = ImageOps.exif_transpose(image)

    # WebP supports alpha; flatten CMYK/16-bit modes that WebP cannot encode.
    if image.mode in {"RGBA", "LA"}:
        image = image.convert("RGBA")
    else:
        image = image.convert("RGB")

    return image


def _encode(image: Image.Image, max_edge: int, quality: int) -> bytes:
    copy = image.copy()
    copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format="WEBP", quality=quality, method=4)
    return buffer.getvalue()


def save_photo(content: bytes, listing_id: int) -> Photo:
    """Validate, re-encode and store one photo. Returns its metadata."""
    image = _open_verified(content)
    digest = hashlib.sha256(content).hexdigest()
    photo_id = digest[:16]

    directory = _listing_dir(listing_id)
    display_rel = f"listings/{int(listing_id)}/{photo_id}-display.webp"
    thumb_rel = f"listings/{int(listing_id)}/{photo_id}-thumb.webp"
    display_file = MEDIA_ROOT / display_rel
    thumb_file = MEDIA_ROOT / thumb_rel

    if not display_file.exists():
        _atomic_write(display_file, _encode(image, DISPLAY_MAX_EDGE, 82))
    if not thumb_file.exists():
        _atomic_write(thumb_file, _encode(image, THUMB_MAX_EDGE, 75))

    width, height = image.size
    return Photo(
        id=photo_id,
        hash=digest,
        width=width,
        height=height,
        bytes=display_file.stat().st_size,
        display_path=display_rel,
        thumb_path=thumb_rel,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def delete_photos(listing_id: int, photos: list[dict[str, Any]]) -> None:
    """Remove derivative files for the given photo records."""
    for photo in photos:
        for key in ("display_path", "thumb_path"):
            rel = photo.get(key)
            if not rel:
                continue
            candidate = (MEDIA_ROOT / rel).resolve()
            root = MEDIA_ROOT.resolve()
            if root not in candidate.parents:
                logger.warning("[Media] refusing to delete outside media root: %s", rel)
                continue
            try:
                candidate.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("[Media] could not delete %s: %s", candidate, exc)


def delete_listing_media(listing_id: int) -> None:
    """Remove the whole directory for a listing (used on withdrawal)."""
    directory = (MEDIA_ROOT / "listings" / str(int(listing_id))).resolve()
    root = MEDIA_ROOT.resolve()
    if root not in directory.parents:
        return
    shutil.rmtree(directory, ignore_errors=True)


def public_url(rel_path: str) -> str:
    return f"{MEDIA_URL_PREFIX}/{rel_path}"


def is_safe_media_path(rel_path: str) -> bool:
    """Only serve generated files from listings/<id>/<hash>-<variant>.webp."""
    return bool(
        re.fullmatch(r"listings/\d+/[a-f0-9]{16}-(display|thumb)\.webp", rel_path)
    )
