"""
Feed Monitor Tests
Tests health check aggregation and summary.
Run: python -m pytest tests/test_feed_monitor.py -v
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from core.registry import ModuleRegistry, OracleModule, QueryType, TemporalLayer
from core.feed_monitor import FeedMonitor


def _make_mock_module(prefix="commodity", module_id="test.module", health_result=None):
    m = MagicMock(spec=OracleModule)
    m.id = module_id
    m.domain_prefix = prefix
    m.query_types = [QueryType.PREDICTIVE]
    m.temporal_layers = [TemporalLayer.T2]
    m.confidence_range = (0.4, 0.9)
    m.health_check = AsyncMock(return_value=health_result or {
        "module": module_id,
        "feeds": {
            "test_feed": {"status": "ok", "last_fetched": 1000.0},
        },
    })
    return m


class TestFeedMonitor:

    @pytest.mark.asyncio
    async def test_check_all_feeds_healthy(self):
        registry = ModuleRegistry()
        module = _make_mock_module(health_result={
            "module": "test.module",
            "feeds": {
                "feed_a": {"status": "ok", "last_fetched": 1000.0},
                "feed_b": {"status": "ok", "last_fetched": 1000.0},
            },
        })
        registry.register(module)

        monitor = FeedMonitor(registry)
        results = await monitor.check_all_feeds()

        assert "test.module" in results
        assert results["test.module"]["feed_a"]["status"] == "ok"
        assert results["test.module"]["feed_b"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_summary_all_healthy(self):
        registry = ModuleRegistry()
        module = _make_mock_module(health_result={
            "module": "test.module",
            "feeds": {"feed_a": {"status": "ok"}},
        })
        registry.register(module)

        monitor = FeedMonitor(registry)
        await monitor.check_all_feeds()
        summary = monitor.summary()

        assert summary["status"] == "healthy"
        assert summary["healthy"] == 1
        assert summary["unhealthy"] == 0

    @pytest.mark.asyncio
    async def test_summary_degraded(self):
        registry = ModuleRegistry()
        module = _make_mock_module(health_result={
            "module": "test.module",
            "feeds": {
                "feed_ok": {"status": "ok"},
                "feed_bad": {"status": "no_api_key", "message": "Key not set"},
            },
        })
        registry.register(module)

        monitor = FeedMonitor(registry)
        await monitor.check_all_feeds()
        summary = monitor.summary()

        assert summary["status"] == "degraded"
        assert summary["healthy"] == 1
        assert summary["unhealthy"] == 1
        assert len(summary["warnings"]) == 1

    @pytest.mark.asyncio
    async def test_no_check_run_yet(self):
        registry = ModuleRegistry()
        monitor = FeedMonitor(registry)
        summary = monitor.summary()
        assert summary["status"] == "no_check_run"

    @pytest.mark.asyncio
    async def test_module_health_check_error(self):
        registry = ModuleRegistry()
        module = _make_mock_module()
        module.health_check = AsyncMock(side_effect=Exception("Connection failed"))
        registry.register(module)

        monitor = FeedMonitor(registry)
        results = await monitor.check_all_feeds()
        assert results["test.module"]["status"] == "error"
