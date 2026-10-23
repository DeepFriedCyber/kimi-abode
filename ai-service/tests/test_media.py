"""Media processing tests — validation, EXIF stripping, derivatives, dedupe."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app import media


def jpeg_bytes(width: int = 1200, height: int = 800, *, exif: Image.Exif | None = None) -> bytes:
    image = Image.new("RGB", (width, height), (30, 120, 200))
    buffer = io.BytesIO()
    options = {"format": "JPEG", "quality": 90}
    if exif is not None:
        options["exif"] = exif
    image.save(buffer, **options)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def temp_media_root(tmp_path, monkeypatch):
    root = tmp_path / "media"
    monkeypatch.setattr(media, "MEDIA_ROOT", root)
    monkeypatch.setattr(media, "MAX_FILE_BYTES", 2 * 1024 * 1024)
    media.ensure_media_root()
    return root


class TestValidation:
    def test_accepts_jpeg_and_writes_derivatives(self, temp_media_root: Path):
        photo = media.save_photo(jpeg_bytes(), listing_id=1)

        assert photo.width == 1200 and photo.height == 800
        display = temp_media_root / photo.display_path
        thumb = temp_media_root / photo.thumb_path
        assert display.exists() and thumb.exists()
        assert display.suffix == ".webp" and thumb.suffix == ".webp"

        with Image.open(display) as image:
            assert image.format == "WEBP"
            assert max(image.size) <= media.DISPLAY_MAX_EDGE
            assert image.size == (1200, 800)  # never upscales
        with Image.open(thumb) as image:
            assert max(image.size) <= media.THUMB_MAX_EDGE

    def test_downscales_large_images(self, temp_media_root: Path):
        photo = media.save_photo(jpeg_bytes(2400, 1600), listing_id=2)
        with Image.open(temp_media_root / photo.display_path) as image:
            assert max(image.size) == media.DISPLAY_MAX_EDGE

    def test_exif_is_stripped(self, temp_media_root: Path):
        exif = Image.Exif()
        exif[0x010F] = "TestCam"  # Make
        photo = media.save_photo(jpeg_bytes(exif=exif), listing_id=3)

        with Image.open(temp_media_root / photo.display_path) as image:
            assert not dict(image.getexif())

    def test_exif_orientation_is_applied(self, temp_media_root: Path):
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90°
        photo = media.save_photo(jpeg_bytes(600, 200, exif=exif), listing_id=4)
        assert (photo.width, photo.height) == (200, 600)

    @pytest.mark.parametrize(
        "payload",
        [
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            b"just some text pretending to be a photo",
            b"\x89PNG\r\n\x1a\n" + b"garbage",
        ],
    )
    def test_rejects_non_images(self, payload: bytes):
        with pytest.raises(media.MediaError) as excinfo:
            media.save_photo(payload, listing_id=5)
        assert excinfo.value.status_code in {415}

    def test_accepts_heic_from_iphones(self, temp_media_root: Path):
        pytest.importorskip("pillow_heif")
        from pillow_heif import register_heif_opener

        register_heif_opener()
        image = Image.new("RGB", (640, 480), (10, 20, 30))
        buffer = io.BytesIO()
        image.save(buffer, format="HEIF")

        photo = media.save_photo(buffer.getvalue(), listing_id=13)

        assert (photo.width, photo.height) == (640, 480)
        with Image.open(temp_media_root / photo.display_path) as saved:
            assert saved.format == "WEBP"

    def test_rejects_gif(self):
        image = Image.new("RGB", (300, 300), (1, 2, 3))
        buffer = io.BytesIO()
        image.save(buffer, format="GIF")
        with pytest.raises(media.MediaError) as excinfo:
            media.save_photo(buffer.getvalue(), listing_id=6)
        assert excinfo.value.status_code == 415

    def test_rejects_tiny_images(self):
        with pytest.raises(media.MediaError) as excinfo:
            media.save_photo(jpeg_bytes(100, 100), listing_id=7)
        assert excinfo.value.status_code == 422

    def test_rejects_oversized_files(self, monkeypatch):
        monkeypatch.setattr(media, "MAX_FILE_BYTES", 100)
        with pytest.raises(media.MediaError) as excinfo:
            media.save_photo(jpeg_bytes(), listing_id=8)
        assert excinfo.value.status_code == 413

    def test_rejects_oversized_pixel_count(self, monkeypatch):
        monkeypatch.setattr(media, "MAX_PIXELS", 50_000)  # 300x300 = 90k
        with pytest.raises(media.MediaError) as excinfo:
            media.save_photo(jpeg_bytes(300, 300), listing_id=9)
        assert excinfo.value.status_code == 413

    def test_rejects_empty(self):
        with pytest.raises(media.MediaError):
            media.save_photo(b"", listing_id=10)


class TestStorage:
    def test_deduplicates_identical_content(self, temp_media_root: Path):
        first = media.save_photo(jpeg_bytes(), listing_id=11)
        second = media.save_photo(jpeg_bytes(), listing_id=11)

        assert first.id == second.id
        files = list((temp_media_root / "listings" / "11").glob("*.webp"))
        assert len(files) == 2  # display + thumb, not four

    def test_delete_removes_files(self, temp_media_root: Path):
        photo = media.save_photo(jpeg_bytes(), listing_id=12)
        media.delete_photos(12, [photo.as_dict() | {"display_path": photo.display_path, "thumb_path": photo.thumb_path}])

        assert not (temp_media_root / photo.display_path).exists()
        assert not (temp_media_root / photo.thumb_path).exists()

    def test_safe_media_paths(self):
        assert media.is_safe_media_path("listings/1/0123456789abcdef-display.webp")
        assert not media.is_safe_media_path("listings/1/../../etc/passwd")
        assert not media.is_safe_media_path("listings/1/notahash-display.webp")
        assert not media.is_safe_media_path("other/1/0123456789abcdef-display.webp")
