"""Overpass client tests — parsing and endpoint failover (no network)."""

from __future__ import annotations

import pytest

from app.poi import overpass


class FakeResponse:
    def __init__(self, payload: dict | None = None, status: int = 200, error: Exception | None = None):
        self._payload = payload
        self.status = status
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *args):
        return None

    async def json(self, content_type=None):
        return self._payload


class FakeSession:
    """Maps endpoint -> FakeResponse (or a list of responses in order)."""

    def __init__(self, behaviours: dict[str, FakeResponse | list[FakeResponse]]):
        self.behaviours = behaviours
        self.calls: list[str] = []

    def post(self, endpoint: str, data=None, timeout=None):
        self.calls.append(endpoint)
        behaviour = self.behaviours.get(endpoint)
        if isinstance(behaviour, list):
            if not behaviour:
                return FakeResponse(error=RuntimeError("exhausted"))
            return behaviour.pop(0)
        return behaviour or FakeResponse(error=RuntimeError(f"no route for {endpoint}"))


PAYLOAD = {
    "elements": [
        {"type": "node", "id": 1, "lat": 53.1, "lon": -2.4, "tags": {"name": "Test School"}},
        {"type": "way", "id": 2, "center": {"lat": 53.2, "lon": -2.5}, "tags": {}},
        {"type": "node", "id": 3},  # no coordinates -> dropped
    ]
}


class TestParsing:
    def test_parses_nodes_and_ways(self):
        pois = overpass._parse_elements(PAYLOAD, "school")
        assert len(pois) == 2
        assert pois[0]["name"] == "Test School"
        assert pois[0]["lat"] == pytest.approx(53.1)
        assert pois[1]["name"] == "School"  # falls back to the category

    def test_bbox_ordering_is_south_west_north_east(self):
        assert overpass._format_bbox((53.0, -2.6, 53.3, -2.2)) == "53.0,-2.6,53.3,-2.2"


class TestFailover:
    @pytest.mark.asyncio
    async def test_uses_the_working_endpoint(self, monkeypatch):
        good = "https://good.example/interpreter"
        bad = "https://bad.example/interpreter"
        monkeypatch.setattr(overpass, "ENDPOINTS", [bad, good])
        monkeypatch.setattr(overpass, "_preferred_endpoint", 0)

        session = FakeSession({bad: FakeResponse(error=ConnectionError("down")), good: FakeResponse(PAYLOAD)})
        pois = await overpass.fetch_category(session, bad, "53.0,-2.6,53.3,-2.2", "school")

        assert len(pois) == 2
        assert session.calls == [bad, good]

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_endpoints_fail(self, monkeypatch):
        monkeypatch.setattr(overpass, "ENDPOINTS", ["https://a.example", "https://b.example"])
        session = FakeSession({})
        pois = await overpass.fetch_category(session, "https://a.example", "0,0,1,1", "school")
        assert pois == []

    @pytest.mark.asyncio
    async def test_non_json_response_is_skipped(self, monkeypatch):
        monkeypatch.setattr(overpass, "ENDPOINTS", ["https://a.example", "https://b.example"])
        session = FakeSession(
            {
                "https://a.example": FakeResponse(payload="<html>not json</html>"),
                "https://b.example": FakeResponse(PAYLOAD),
            }
        )
        pois = await overpass.fetch_category(session, "https://a.example", "0,0,1,1", "school")
        assert len(pois) == 2

    @pytest.mark.asyncio
    async def test_select_endpoint_probes_once(self, monkeypatch):
        monkeypatch.setattr(overpass, "ENDPOINTS", ["https://down.example", "https://up.example"])
        monkeypatch.setattr(overpass, "_preferred_endpoint", 0)
        session = FakeSession(
            {
                "https://down.example": FakeResponse(status=504),
                "https://up.example": FakeResponse(PAYLOAD),
            }
        )

        endpoint = await overpass._select_endpoint(session, "0,0,1,1", "school")
        assert endpoint == "https://up.example"
