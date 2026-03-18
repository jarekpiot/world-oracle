"""
API Server Tests
Tests all endpoints using FastAPI test client.
Run: python -m pytest tests/test_api.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from core.registry import (
    DecomposedQuery, QueryType, TemporalLayer, SignalDirection,
    ModuleResponse, Signal,
)


@pytest.fixture
def client(tmp_path):
    """Create a test client with mocked oracle components."""
    # Must import after patching to avoid module-level side effects
    import api.server as server_module

    # Reset server state
    server_module.registry = MagicMock()
    server_module.registry.is_healthy.return_value = True
    server_module.registry.list_modules.return_value = [
        {"id": "commodities.v1", "prefix": "commodity",
         "query_types": ["predictive"], "temporal_layers": ["strategic"],
         "confidence_range": (0.25, 0.88)},
    ]

    server_module.signal_store = MagicMock()
    server_module.signal_store.get_history.return_value = []
    server_module.signal_store.get_track_record.return_value = {
        "total_calls": 0, "responded": 0, "abstained": 0,
        "scored": 0, "outcomes": {}, "win_rate": None,
    }

    server_module.feed_monitor = MagicMock()
    server_module.feed_monitor.last_check = {"commodities.v1": {"eia": {"status": "ok"}}}
    server_module.feed_monitor.last_check_at = "2025-01-01T00:00:00Z"
    server_module.feed_monitor.summary.return_value = {
        "status": "healthy", "total_feeds": 5, "healthy": 3, "unhealthy": 2, "warnings": [],
    }

    server_module.query_engine = MagicMock()
    server_module.synthesiser = MagicMock()
    server_module.rate_limiter = server_module.RateLimiter()

    # Use TestClient without lifespan to avoid re-init
    with TestClient(server_module.app, raise_server_exceptions=False) as c:
        yield c, server_module


class TestHealthEndpoint:

    def test_health_returns_ok(self, client):
        c, _ = client
        resp = c.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["modules_registered"] == 1

    def test_health_no_modules(self, client):
        c, server = client
        server.registry.is_healthy.return_value = False
        resp = c.get("/api/health")
        assert resp.json()["status"] == "no_modules"


class TestModulesEndpoint:

    def test_list_modules(self, client):
        c, _ = client
        resp = c.get("/api/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["modules"][0]["id"] == "commodities.v1"


class TestHistoryEndpoint:

    def test_empty_history(self, client):
        c, _ = client
        resp = c.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["calls"] == []

    def test_history_with_domain_filter(self, client):
        c, server = client
        c.get("/api/history?domain=commodity")
        server.signal_store.get_history.assert_called_with(limit=50, domain="commodity")


class TestQueryEndpoint:

    def test_query_routed_and_logged(self, client):
        c, server = client

        # Mock Layer 1 decomposition
        server.query_engine.decompose = AsyncMock(return_value=DecomposedQuery(
            raw="Will oil rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="commodity.energy.crude_oil",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.65,
            sub_tasks=[],
        ))

        # Mock module
        mock_module = MagicMock()
        mock_signal = Signal(
            agent_id="inventory_agent", source="EIA", value={},
            direction=SignalDirection.BULLISH, confidence=0.80,
            temporal_layer=TemporalLayer.T2,
            generated_at="2025-01-01T00:00:00Z", valid_horizon="8 weeks",
            decay_triggers=["OPEC surprise"], domain_path="commodity.energy.crude_oil",
        )
        mock_module.handle = AsyncMock(return_value=ModuleResponse(
            module_id="commodities.v1",
            domain_path="commodity.energy.crude_oil",
            signals=[mock_signal],
            synthesised_view=SignalDirection.BULLISH,
            confidence=0.80,
            reasoning_trace={},
            invalidators=["OPEC surprise"],
            sources=[{"agent": "inventory_agent", "feed": "EIA", "timestamp": "now"}],
            temporal_layer=TemporalLayer.T2,
        ))
        server.registry.resolve.return_value = mock_module

        # Mock Layer 3 synthesis
        from core.confidence_engine import ConfidenceResult
        mock_confidence = ConfidenceResult(
            score=0.75, band=(0.69, 0.81), meets_threshold=True,
            verdict=SignalDirection.BULLISH, limiting_factor="test",
            alignment_score=0.85, signal_count=1,
        )
        server.synthesiser.synthesise = AsyncMock(return_value=(
            {
                "synthesised_view": "bullish",
                "dominant_thesis": "Supply tightening",
                "time_horizon": "T2 — 6 weeks",
                "invalidators": ["OPEC surprise"],
                "devils_advocate": "China could slow",
                "conflicts_found": [],
                "key_supporting_signals": [],
                "reasoning": "test",
                "reasoning_trace": {},
            },
            mock_confidence,
        ))

        server.signal_store.log_call.return_value = 42

        resp = c.post("/api/query", json={"query": "Will crude oil rise over 6 weeks?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ORACLE_RESPONSE"
        assert data["call_id"] == 42
        assert data["view"]["direction"] == "bullish"

        # Verify it was logged
        server.signal_store.log_call.assert_called_once()

    def test_query_no_module(self, client):
        c, server = client

        server.query_engine.decompose = AsyncMock(return_value=DecomposedQuery(
            raw="Will bitcoin rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="crypto.l1.bitcoin",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.65,
            sub_tasks=[],
        ))
        server.registry.resolve.return_value = None

        resp = c.post("/api/query", json={"query": "Will bitcoin rise over 6 weeks?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "NO_MODULE"

    def test_query_validation(self, client):
        c, _ = client
        resp = c.post("/api/query", json={"query": "hi"})  # too short
        assert resp.status_code == 422


class TestRateLimiter:

    def test_allows_within_limit(self):
        from api.server import RateLimiter
        limiter = RateLimiter(max_requests=5)
        for _ in range(5):
            assert limiter.allow() is True
        assert limiter.allow() is False

    def test_remaining_count(self):
        from api.server import RateLimiter
        limiter = RateLimiter(max_requests=10)
        limiter.allow()
        limiter.allow()
        assert limiter.remaining == 8
