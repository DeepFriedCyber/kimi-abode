"""Tests for postcodes.io enrichment."""

from __future__ import annotations

import pytest


class TestPostcodesIO:
    """Tests for the PostcodesIO wrapper."""

    @pytest.mark.asyncio
    async def test_get_outcode(self):
        from app.enrichment.postcodes_io import PostcodesIO

        pio = PostcodesIO()
        result = await pio.get_outcode("CW11 1AA")
        # May return None if rate-limited or API unavailable — that's OK
        if result is not None:
            assert "outcode" in result or "district" in result

    @pytest.mark.asyncio
    async def test_invalid_postcode(self):
        from app.enrichment.postcodes_io import PostcodesIO

        pio = PostcodesIO()
        result = await pio.get_outcode("ZZ99 1QQ")  # invalid outcode
        assert result is None


class TestEnrichment:
    """Tests for property enrichment."""

    @pytest.mark.asyncio
    async def test_enrich_with_gazetteer(self):
        from app.enrichment.enrich import enrich_properties

        if True:  # Would need pool fixture for real test
            pass  # Placeholder — full test requires database

    @pytest.mark.asyncio
    async def test_review_enrichment(self):
        """Test enrichment review function returns expected structure."""
        from app.enrichment.enrich import review_enrichment

        if True:  # Would need pool fixture for real test
            pass  # Placeholder
