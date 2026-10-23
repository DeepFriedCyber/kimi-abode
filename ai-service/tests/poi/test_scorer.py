"""Tests for POI scorer and router."""

from __future__ import annotations

import pytest


class TestPOIScorer:
    """Tests for POI scoring functions."""

    def test_haversine_close(self):
        from app.poi.scorer import haversine_m

        # Same point → distance ≈ 0
        dist = haversine_m(53.1, -2.4, 53.1, -2.4)
        assert dist < 10  # < 10m tolerance

    def test_haversine_far(self):
        from app.poi.scorer import haversine_m

        # London → Manchester ≈ 280km
        dist = haversine_m(51.5, -0.1, 53.5, -2.2)
        assert 200_000 < dist < 400_000

    def test_decay_score(self):
        from app.poi.scorer import decay_score

        # At half_life distance, score = 0.5
        score = decay_score(500.0)
        assert abs(score - 0.5) < 0.01

    def test_decay_score_at_zero(self):
        from app.poi.scorer import decay_score

        score = decay_score(0)
        assert score == 1.0


class TestPOIRouter:
    """Tests for the POI router endpoints."""

    @pytest.mark.asyncio
    async def test_ingest_pois(self, monkeypatch):
        from types import SimpleNamespace

        from app.routers import poi

        async def fake_fetch(bbox, categories=None):
            return [
                {"name": "School A", "osm_id": 1, "lat": 53.1, "lon": -2.4, "category": "school"},
                {"name": "School A", "osm_id": 1, "lat": 53.1, "lon": -2.4, "category": "school"},
                {"name": "The Pub", "osm_id": 2, "lat": 53.1, "lon": -2.4, "category": "pub"},
            ]

        monkeypatch.setattr(poi, "fetch_pois", fake_fetch)
        monkeypatch.delenv("POI_INGEST_API_KEY", raising=False)
        monkeypatch.delenv("POI_INJECTION_SECRET", raising=False)

        poi.set_poi_data([])
        request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))

        result = await poi.ingest_pois({"bbox": "53.0,-2.7,53.3,-2.1"}, request)

        assert result["ingested"] == 2  # duplicate (osm_id, category) collapsed
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_ingest_requires_the_configured_key(self, monkeypatch):
        from types import SimpleNamespace

        from fastapi import HTTPException

        from app.routers import poi

        monkeypatch.setenv("POI_INGEST_API_KEY", "a-very-secret-key")
        poi.set_poi_data([])

        request = SimpleNamespace(
            headers={"x-api-key": "wrong"},
            client=SimpleNamespace(host="127.0.0.1"),
        )

        with pytest.raises(HTTPException) as excinfo:
            await poi.ingest_pois({"bbox": "53.0,-2.7,53.3,-2.1"}, request)

        assert excinfo.value.status_code == 401


class TestPoiQA:
    """Tests for POI QA functions."""

    def test_qa_poi_data(self):
        from app.poi.qa import qa_poi_data

        pois = [
            {"name": "Test Pub", "osm_id": 1, "lat": 53.0, "lon": -2.4, "category": "pub"},
            {"name": "Duplicate", "osm_id": 1, "lat": 53.1, "lon": -2.5, "category": "restaurant"},
        ]
        result = qa_poi_data(pois)
        assert result["total"] == 2
        assert len(result["issues"]) >= 1  # should flag duplicate osm_id


class TestScorerImportFix:
    """Verify the corrected import works (addresses setup-guide §4 note)."""

    def test_scorer_exports(self):
        from app.poi.scorer import PoiPoint, decay_score, haversine_m, nearest, score_property

        assert callable(decay_score)
        assert callable(haversine_m)
        assert callable(nearest)
        assert callable(score_property)


class TestAskRoutes:
    """Tests for the ask/POI routes integration."""

    @pytest.mark.asyncio
    async def test_nearby_pois_empty(self):
        from app.routers.poi import set_poi_data, nearby_pois

        set_poi_data([])
        result = await nearby_pois(lat=53.0, lon=-2.4)
        assert "nearby" in result


class TestObservabilityMetrics:
    """Tests for metrics in the API server."""

    @pytest.mark.asyncio
    async def test_metrics_increment(self):
        from app.observability.metrics import Metrics

        m = Metrics()
        m.inc("test_requests")
        assert m._requests["test_requests"] == 1

    @pytest.mark.asyncio
    async def test_metrics_render(self):
        from app.observability.metrics import Metrics

        m = Metrics()
        m.inc("test_total")
        rendered = m.render()
        assert "test_total" in rendered


class TestHardening:
    """Tests for hardening measures — auth, security, etc."""

    def test_redact_sensitive_data(self):
        from app.security.redact import redact

        text = "My email is test@example.com and password=mysecretpassword123"
        result = redact(text)
        assert "test@example.com" not in result  # email should be redacted
        assert "mysecretpassword123" not in result  # password should be redacted
        assert "[REDACTED_" in result  # contains at least one redaction marker

    def test_redact_dict(self):
        from app.security.redact import redact_dict

        data = {"email": "test@example.com", "password": "secret123", "name": "John"}
        result = redact_dict(data)
        assert result["password"] == "[REDACTED]"
        assert result["name"] == "John"
