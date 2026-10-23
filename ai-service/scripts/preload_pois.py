"""Preload POIs for the demo dataset's bounding box.

Two sources:
  * local OSM extract (recommended) — 221 MB download, then offline filtering
  * Overpass API — no download, but public instances are unreliable

Usage (from ai-service/):
    python -m scripts.preload_pois --download
    python -m scripts.preload_pois --pbf data/cache/north_west.osm.pbf
    python -m scripts.preload_pois --source overpass
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_EXTRACT_URL = (
    "https://download.openstreetmap.fr/extracts/europe/united_kingdom/england/"
    "north_west-latest.osm.pbf"
)
DEFAULT_PBF = Path("data/cache/north_west.osm.pbf")
USER_AGENT = "AbodeAI/0.1 (offline POI cache)"


def fixture_bbox(fixture: Path, padding: float) -> tuple[float, float, float, float]:
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    records = payload.get("records", payload)

    lats = [record["latitude"] for record in records if record.get("latitude") is not None]
    lons = [record["longitude"] for record in records if record.get("longitude") is not None]
    if not lats or not lons:
        raise SystemExit(f"No coordinates in {fixture}; import with --enrich first")

    return (
        min(lats) - padding,
        min(lons) - padding,
        max(lats) + padding,
        max(lons) + padding,
    )


def download(url: str, destination: Path) -> Path:
    """Download with resume support; skips when the file already exists."""
    if destination.exists() and destination.stat().st_size > 0:
        print(f"using existing extract: {destination} "
              f"({destination.stat().st_size / 1_048_576:.0f} MB)")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
        print(f"resuming download at {offset / 1_048_576:.0f} MB")

    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0) + offset
        mode = "ab" if offset else "wb"
        with partial.open(mode) as handle:
            downloaded = offset
            last_reported = -1
            while True:
                chunk = response.read(4 * 1_048_576)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if total:
                    percent = int(downloaded * 100 / total)
                    if percent >= last_reported + 5:
                        last_reported = percent
                        print(f"  {percent:3d}%  {downloaded / 1_048_576:6.1f}/{total / 1_048_576:.0f} MB")

    partial.replace(destination)
    print(f"downloaded {destination} ({destination.stat().st_size / 1_048_576:.0f} MB)")
    return destination


async def from_overpass(bbox: tuple[float, float, float, float]) -> list[dict]:
    from app.poi.overpass import fetch_pois

    return await fetch_pois(bbox)


def from_extract(pbf: Path, bbox: tuple[float, float, float, float]) -> list[dict]:
    from app.poi.osm_extract import build_pois_from_pbf, dedupe

    return dedupe(build_pois_from_pbf(str(pbf), bbox))


def write_cache(path: Path, bbox: tuple[float, float, float, float], pois: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "bbox": bbox,
                "count": len(pois),
                "pois": pois,
            },
            indent=1,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="data/demo_listings.json")
    parser.add_argument("--output", default="data/poi_cache.json")
    parser.add_argument("--padding", type=float, default=0.02)
    parser.add_argument(
        "--source",
        choices=["auto", "extract", "overpass"],
        default="auto",
        help="auto: use the cached extract when present, otherwise Overpass",
    )
    parser.add_argument("--pbf", default=None, help="Path to a local .osm.pbf extract")
    parser.add_argument(
        "--download",
        action="store_true",
        help=f"Download the default extract ({DEFAULT_EXTRACT_URL.split('/')[-1]}, ~221 MB)",
    )
    args = parser.parse_args()

    bbox = fixture_bbox(Path(args.fixture), args.padding)
    print(f"bbox (south,west,north,east) = {bbox}")

    pbf = Path(args.pbf) if args.pbf else DEFAULT_PBF
    source = args.source

    if source == "auto":
        source = "extract" if pbf.exists() else "overpass"

    if args.download and not pbf.exists():
        try:
            download(DEFAULT_EXTRACT_URL, pbf)
        except Exception as exc:  # noqa: BLE001
            print(f"download failed: {exc}", file=sys.stderr)
            return 1
        source = "extract"

    if source == "extract":
        if not pbf.exists():
            print(
                f"Extract not found: {pbf}\n"
                f"Run with --download, or pass --pbf <file>.\n"
                f"Default source: {DEFAULT_EXTRACT_URL}",
                file=sys.stderr,
            )
            return 1
        pois = from_extract(pbf, bbox)
    else:
        pois = asyncio.run(from_overpass(bbox))

    if not pois:
        print("No POIs found (source unreachable or empty area)")
        return 1

    write_cache(Path(args.output), bbox, pois)

    by_category: dict[str, int] = {}
    for poi in pois:
        by_category[poi["category"]] = by_category.get(poi["category"], 0) + 1

    print(f"wrote {len(pois)} POIs to {args.output}")
    print(f"by category: {by_category}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
