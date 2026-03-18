"""
Commodities Module Tests
Tests the seed module, inventory agent, and EIA feed.
Run: python -m pytest tests/test_commodities.py -v
"""

import json
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


# ─── Inventory Agent LLM Reasoning Tests ────────────────────────────────────

class TestInventoryAgentLLM:
    """Tests for the LLM reasoning path of the inventory agent."""

    def _make_feed_result(self, change, latest=440000, readings=None):
        if readings is None:
            readings = [
                {"period": "2025-03-14", "value": latest, "product": "crude oil"},
                {"period": "2025-03-07", "value": latest - change, "product": "crude oil"},
                {"period": "2025-02-28", "value": latest - change + 500, "product": "crude oil"},
                {"period": "2025-02-21", "value": latest - change + 1000, "product": "crude oil"},
                {"period": "2025-02-14", "value": latest - change + 1500, "product": "crude oil"},
                {"period": "2025-02-07", "value": latest - change + 2000, "product": "crude oil"},
            ]
        return FeedResult(
            data={
                "readings": readings,
                "latest": latest,
                "previous": latest - change,
                "change": change,
                "unit": "thousand barrels",
                "series": "weekly_crude_stocks_excl_spr",
            },
            ok=True,
            fetched_at=1000.0,
        )

    def _make_llm_response(self, direction="BULLISH", confidence=0.78,
                           reasoning="Test reasoning.", decay_triggers=None):
        """Create a mock LLM response object."""
        if decay_triggers is None:
            decay_triggers = [
                "OPEC announces output increase >500k bpd",
                "US SPR release >20M barrels announced",
                "EIA revises prior week data by >2M barrels",
            ]
        content = json.dumps({
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
            "decay_triggers": decay_triggers,
        })
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]
        return mock_response

    @pytest.mark.asyncio
    async def test_llm_bullish_signal(self):
        """LLM returns bullish — agent should produce bullish signal."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-4000)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.82,
                reasoning="Large draw of 4M bbl against seasonal norms. Trend shows 5 consecutive weeks of draws, accelerating.",
            )
        )

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.82
        assert signal.temporal_layer == TemporalLayer.T2
        assert "draw" in signal.reasoning.lower() or "4M" in signal.reasoning
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_bearish_signal(self):
        """LLM returns bearish — agent should produce bearish signal."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(5000)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BEARISH",
                confidence=0.75,
                reasoning="Large 5M bbl build. Seasonal builds expected but this exceeds norms.",
            )
        )

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.75

    @pytest.mark.asyncio
    async def test_llm_neutral_signal(self):
        """LLM returns neutral for ambiguous data."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(200)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.55,
                reasoning="Negligible 200k bbl build. Mixed trend. No clear signal.",
            )
        )

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_llm_unknown_direction(self):
        """LLM honestly returns UNKNOWN when it cannot determine direction."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(0)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="UNKNOWN",
                confidence=0.30,
                reasoning="Insufficient context to determine direction.",
            )
        )

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.30

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_thresholds(self):
        """If LLM call fails, agent falls back to threshold logic."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-4000)

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        # Should fall back to threshold: large draw = BULLISH 0.85
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.85

    @pytest.mark.asyncio
    async def test_llm_invalid_json_falls_back(self):
        """If LLM returns invalid JSON, fall back to thresholds."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(2000)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON at all")]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        # Should fall back to threshold: moderate build = BEARISH 0.72
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.72

    @pytest.mark.asyncio
    async def test_no_client_uses_thresholds(self):
        """Without an LLM client, agent uses threshold logic."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-1500)

        agent = InventoryAgent(feed, client=None)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.72

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_high(self):
        """Confidence from LLM is clamped to max 0.88."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-5000)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.99,  # Too high — should be clamped
                reasoning="Massive draw.",
            )
        )

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence <= 0.88

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_low(self):
        """Confidence from LLM is clamped to min 0.30."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(100)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.10,  # Too low — should be clamped
                reasoning="Flat.",
            )
        )

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence >= 0.30

    @pytest.mark.asyncio
    async def test_llm_decay_triggers_are_specific(self):
        """LLM-provided decay triggers should be passed through."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-2000)

        triggers = [
            "OPEC announces output increase >500k bpd",
            "US SPR release >20M barrels announced",
            "EIA revises prior week data by >2M barrels",
        ]
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.72,
                reasoning="Moderate draw.",
                decay_triggers=triggers,
            )
        )

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert len(signal.decay_triggers) >= 2
        assert any("OPEC" in t for t in signal.decay_triggers)

    @pytest.mark.asyncio
    async def test_one_llm_call_only(self):
        """Agent must make exactly ONE LLM call."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-3000)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = InventoryAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")
        assert client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_uses_correct_model(self):
        """Agent should use claude-sonnet-4-5."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-3000)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = InventoryAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")

        call_kwargs = client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_feed_failure_skips_llm(self):
        """If the feed is down, don't even call the LLM."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")

        client = AsyncMock()
        client.messages.create = AsyncMock()

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_response_with_markdown_fences(self):
        """LLM sometimes wraps JSON in markdown code fences — agent should handle it."""
        feed = MagicMock(spec=EIAFeed)
        feed.fetch.return_value = self._make_feed_result(-3000)

        content = '```json\n{"direction": "BULLISH", "confidence": 0.78, "reasoning": "Draw.", "decay_triggers": ["Next EIA release"]}\n```'
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = InventoryAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.78


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
