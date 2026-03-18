"""
Commodities Module Tests
Tests the seed module, inventory agent, and EIA feed.
Run: python -m pytest tests/test_commodities.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.registry import (
    DecomposedQuery, QueryType, TemporalLayer, SignalDirection, OracleModule,
)
from modules.commodities import CommoditiesModule
from modules.commodities.agents.inventory_agent import InventoryAgent
from modules.commodities.feeds.base import BaseFeed, FeedResult
from modules.commodities.feeds.eia import EIAFeed


# ─── Feed Tests ──────────────────────────────────────────────────────────────

class TestBaseFeed:

    def test_feed_result_defaults(self):
        r = FeedResult()
        assert r.ok is False
        assert r.data is None
        assert r.error is None

    def test_feed_result_with_data(self):
        r = FeedResult(data={"test": 1}, ok=True, fetched_at=1000.0)
        assert r.ok is True
        assert r.data["test"] == 1


class TestEIAFeed:

    def test_no_api_key_returns_error(self):
        feed = EIAFeed(api_key=None)
        # Clear env var if set
        with patch.dict("os.environ", {}, clear=True):
            feed.api_key = None
            result = feed.fetch()
            assert result.ok is False

    def test_parse_valid_response(self):
        feed = EIAFeed(api_key="test")
        raw = {
            "response": {
                "data": [
                    {"period": "2025-03-14", "value": 440000, "product-name": "crude oil"},
                    {"period": "2025-03-07", "value": 443000, "product-name": "crude oil"},
                ]
            }
        }
        parsed = feed._parse(raw)
        assert parsed["latest"] == 440000
        assert parsed["previous"] == 443000
        assert parsed["change"] == -3000  # draw

    def test_parse_empty_response(self):
        feed = EIAFeed(api_key="test")
        raw = {"response": {"data": []}}
        parsed = feed._parse(raw)
        assert parsed["latest"] is None
        assert parsed["change"] is None

    def test_health_no_key(self):
        feed = EIAFeed(api_key=None)
        with patch.dict("os.environ", {}, clear=True):
            feed.api_key = None
            h = feed.health()
            assert h["status"] == "no_api_key"


# ─── Inventory Agent Tests ───────────────────────────────────────────────────

class TestInventoryAgent:

    def _make_feed_result(self, change, latest=440000):
        return FeedResult(
            data={
                "readings": [],
                "latest": latest,
                "previous": latest - change,
                "change": change,
                "unit": "thousand barrels",
                "series": "weekly_crude_stocks_excl_spr",
            },
            ok=True,
            fetched_at=1000.0,
        )

    @pytest.mark.asyncio
    async def test_large_draw_is_bullish(self):
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-4000)
        agent = InventoryAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.85
        assert signal.temporal_layer == TemporalLayer.T2

    @pytest.mark.asyncio
    async def test_moderate_draw_is_bullish(self):
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-1500)
        agent = InventoryAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.72

    @pytest.mark.asyncio
    async def test_flat_is_neutral(self):
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(100)
        agent = InventoryAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.60

    @pytest.mark.asyncio
    async def test_moderate_build_is_bearish(self):
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(2000)
        agent = InventoryAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.72

    @pytest.mark.asyncio
    async def test_large_build_is_bearish(self):
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(5000)
        agent = InventoryAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.85

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        """ZERO FABRICATION — if feed is down, return UNKNOWN, not a guess."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")
        agent = InventoryAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        assert "unavailable" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_signal_has_decay_triggers(self):
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-2000)
        agent = InventoryAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert len(signal.decay_triggers) >= 2
        assert any("OPEC" in t for t in signal.decay_triggers)


# ─── Commodities Module Tests ───────────────────────────────────────────────

class TestCommoditiesModule:

    def test_implements_oracle_module(self):
        client = MagicMock()
        module = CommoditiesModule(client)
        assert isinstance(module, OracleModule)

    def test_module_properties(self):
        client = MagicMock()
        module = CommoditiesModule(client)
        assert module.id == "commodities.v1"
        assert module.domain_prefix == "commodity"
        assert TemporalLayer.T2 in module.temporal_layers
        assert module.confidence_range == (0.25, 0.88)

    def test_feeds_list(self):
        client = MagicMock()
        module = CommoditiesModule(client)
        feeds = module.feeds
        assert len(feeds) >= 1
        assert feeds[0].id == "eia_spot_price"

    @pytest.mark.asyncio
    async def test_handle_returns_module_response(self):
        client = MagicMock()
        module = CommoditiesModule(client)

        # Mock the feed to return a draw
        module.eia_feed = MagicMock(spec=EIAFeed)
        module.eia_feed.fetch.return_value = FeedResult(
            data={
                "readings": [],
                "latest": 440000,
                "previous": 443000,
                "change": -3000,
                "unit": "thousand barrels",
                "series": "weekly_crude_stocks_excl_spr",
            },
            ok=True,
            fetched_at=1000.0,
        )
        module.inventory_agent = InventoryAgent(module.eia_feed)

        query = DecomposedQuery(
            raw="Will crude oil rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="commodity.energy.crude_oil",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.65,
            sub_tasks=[],
        )

        response = await module.handle(query)
        assert response.module_id == "commodities.v1"
        assert len(response.signals) >= 1
        assert response.synthesised_view == SignalDirection.BULLISH
        assert len(response.sources) >= 1

    @pytest.mark.asyncio
    async def test_handle_with_feeds_down_inventory_unknown(self):
        """When EIA feed is down, inventory agent returns UNKNOWN."""
        client = MagicMock()
        module = CommoditiesModule(client)

        # Mock EIA feeds as down
        down_result = FeedResult(ok=False, error="timeout")
        module.eia_feed = MagicMock(spec=EIAFeed)
        module.eia_feed.fetch.return_value = down_result
        module.inventory_agent = InventoryAgent(module.eia_feed)

        # Mock price feed as down too
        from modules.commodities.feeds.price import PriceFeed
        from modules.commodities.agents.price_agent import PriceAgent
        module.price_feed = MagicMock(spec=PriceFeed)
        module.price_feed.fetch.return_value = down_result
        module.price_agent = PriceAgent(module.price_feed)

        query = DecomposedQuery(
            raw="Will crude oil rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="commodity.energy.crude_oil",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.65,
            sub_tasks=[],
        )

        response = await module.handle(query)
        assert response.module_id == "commodities.v1"
        # Inventory agent should be UNKNOWN with 0.25 confidence
        inv_signals = [s for s in response.signals if s.agent_id == "inventory_agent"]
        assert len(inv_signals) == 1
        assert inv_signals[0].direction == SignalDirection.UNKNOWN
        assert inv_signals[0].confidence == 0.25
