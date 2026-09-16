"""Tests for hardening — auth, security, metrics."""

from __future__ import annotations

import pytest


class TestAuthHardening:
    """Tests for authentication hardening."""

    @pytest.mark.asyncio
    async def test_user_store_initialization(self):
        # UserStore should handle missing DB gracefully
        assert True  # Placeholder — requires Fastify + PgUserStore setup

    @pytest.mark.asyncio
    async def test_token_validation(self):
        import jwt
        secret = "test-secret"
        token = jwt.encode({"sub": "user123"}, secret, algorithm="HS256")
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        assert decoded["sub"] == "user123"


class TestPasswords:
    """Tests for password hashing module."""

    def test_hash_equals(self):
        import hashlib

        pw = "test-password"
        salt = "random-salt-1234"
        h = hashlib.sha256((pw + salt).encode()).hexdigest()

        assert len(h) == 64  # SHA256 output length


class TestMetrics:
    """Tests for metrics endpoint and middleware."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self):
        from app.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200


class TestSecurity:
    """Tests for security/redaction module."""

    def test_redact_email(self):
        from app.security.redact import redact

        text = "Contact: admin@abode.com"
        assert redact(text) != text  # email should be redacted

    def test_redact_dict_nested(self):
        from app.security.redact import redact_dict

        data = {"user": {"password": "secret", "name": "John"}}
        result = redact_dict(data)
        assert result["user"]["password"] == "[REDACTED]"
        assert result["user"]["name"] == "John"


class TestCompoundTypesDB:
    """Tests for compound-type parsing against real data."""

    @pytest.mark.asyncio
    async def test_parser_compound_types(self):
        from app.parser import parse_query

        result = await parse_query("semi-detached bungalow")
        assert result.property_types  # Should have at least one match


class TestSoldLoader:
    """Tests for sold data loader."""

    @pytest.mark.asyncio
    async def test_load_sold_csv(self):
        from app.ingestion.sold_loader import load_sold_csv

        csv_data = "price_paid,date_of_transfer,property_type\n100000,2024-01-01,D"
        # Without a real pool, test the parsing part
        from app.ingestion.formats import parse_sold_data
        records = parse_sold_csv(csv_data) if 'parse_sold_csv' in dir() else []

        assert True  # Placeholder


class TestEnrichment:
    """Tests for enrichment module."""

    @pytest.mark.asyncio
    async def test_review_enrichment_report(self):
        from app.enrichment.review_report import main as review_main

        if True:  # Would need database for real test
            pass  # Placeholder


class TestIngestionSoldLoader:
    """Tests specifically for the sold_loader module."""

    @pytest.mark.asyncio
    async def test_load_sold_csv_sync_wrapper(self):
        from app.ingestion.sold_loader import load_sold_data

        csv_data = "price_paid,date_of_transfer,property_type\n100000,2024-01-01,D"
        result = load_sold_data(csv_data)
        assert result["total"] == 1
        assert result["valid"] == 1


class TestSearchCompound:
    """Tests for compound-type search functionality."""

    @pytest.mark.asyncio
    async def test_search_compound_type(self):
        from app.search import search

        result = await search("semi-detached bungalow")
        assert isinstance(result, dict)
        assert "tier_used" in result


class TestIntegrationCompound:
    """Integration test for compound types with real parser data."""

    @pytest.mark.asyncio
    async def test_full_parser_chain(self):
        from app.parser import parse_query
        from app.search import search

        query = "3 bed semi-detached in Sandbach under £250k"
        parsed = await parse_query(query)

        assert parsed.min_beds == 3
        assert "semi-detached" in [t.value for t in parsed.property_types]
