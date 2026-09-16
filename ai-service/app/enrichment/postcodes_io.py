"""Postcodes.io integration — enrich properties with postcode data."""

from __future__ import annotations

import asyncio
from typing import Any


class PostcodesIO:
    """Wrapper for the free postcodes.io API (no key needed, rate-limited).

    Provides:
    - Outcode → town mapping
    - Lat/lon lookup for postcodes
    """

    BASE_URL = "https://api.postcodes.io/postcodes"

    async def get_outcode(self, postcode: str) -> dict[str, Any] | None:
        """Get outcode info (town, district) for a postcode."""
        import aiohttp

        outcode = postcode.strip().split()[0].upper() if postcode else None
        if not outcode:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/{outcode}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return {
                        "outcode": outcode,
                        "district": data.get("result", {}).get("admin_district"),
                        "parish": data.get("result", {}).get("parish"),
                        "country": data.get("result", {}).get("country"),
                    }
        except Exception:
            return None

    async def get_location(self, postcode: str) -> dict[str, float] | None:
        """Get lat/lon for a postcode."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/{postcode}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    result = data.get("result", {})
                    return {
                        "latitude": float(result.get("latitude", 0)),
                        "longitude": float(result.get("longitude", 0)),
                    }
        except Exception:
            return None

    async def batch_lookup(self, postcodes: list[str]) -> dict[str, dict]:
        """Batch lookup postcodes (one at a time — API has no batch endpoint)."""
        tasks = [self.get_location(pc) for pc in postcodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            pc: r if isinstance(r, dict) else None
            for pc, r in zip(postcodes, results)
        }
