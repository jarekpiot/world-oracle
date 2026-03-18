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
from modules.commodities.agents.narrative_agent import NarrativeAgent
from modules.commodities.agents.geopolitical_agent import GeopoliticalAgent
from modules.commodities.agents.structural_agent import StructuralAgent, STRUCTURAL_VIEWS, DEFAULT_STRUCTURAL
from modules.commodities.agents.weather_agent import WeatherAgent
from modules.commodities.feeds.base import BaseFeed, FeedResult
from modules.commodities.feeds.eia import EIAFeed
from modules.commodities.feeds.noaa import NOAAFeed
from modules.commodities.feeds.gdelt import GDELTFeed


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
        assert feeds[0].id == "live_price"

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


# ─── Geopolitical Agent LLM Reasoning Tests ─────────────────────────────────

class TestGeopoliticalAgentLLM:
    """Tests for the LLM reasoning path of the geopolitical agent."""

    def _make_feed_result(self, escalation=0.5, article_count=30,
                          active_regions=None, avg_tone=-2.5):
        if active_regions is None:
            active_regions = ["middle_east", "red_sea"]
        return FeedResult(
            data={
                "escalation_score": escalation,
                "article_count": article_count,
                "avg_tone": avg_tone,
                "active_regions": active_regions,
                "region_hits": {r: 5 for r in active_regions},
            },
            ok=True,
            fetched_at=1000.0,
        )

    def _make_llm_response(self, direction="BULLISH", confidence=0.65,
                           cycle_phase="escalation", price_impact="upward",
                           reasoning="Test reasoning.", decay_triggers=None):
        """Create a mock LLM response object."""
        if decay_triggers is None:
            decay_triggers = [
                "Ceasefire agreement in key producing region",
                "New sanctions on major oil exporter",
                "Military escalation at key shipping chokepoint",
            ]
        content = json.dumps({
            "direction": direction,
            "confidence": confidence,
            "cycle_phase": cycle_phase,
            "price_impact": price_impact,
            "reasoning": reasoning,
            "decay_triggers": decay_triggers,
        })
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]
        return mock_response

    @pytest.mark.asyncio
    async def test_llm_escalation_bullish(self):
        """LLM returns escalation phase — bullish for commodities."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.75)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.72,
                cycle_phase="escalation",
                price_impact="upward",
                reasoning="High escalation in Middle East and Red Sea. Houthi attacks on shipping intensifying. Supply risk premium rising.",
            )
        )

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.72
        assert signal.temporal_layer == TemporalLayer.T1
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_resolution_bearish(self):
        """LLM returns resolution phase — bearish for commodities."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.1, avg_tone=1.5)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BEARISH",
                confidence=0.60,
                cycle_phase="resolution",
                price_impact="downward",
                reasoning="Diplomatic breakthrough in Middle East. Ceasefire talks progressing. Risk premium compressing.",
            )
        )

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.60
        assert signal.temporal_layer == TemporalLayer.T2

    @pytest.mark.asyncio
    async def test_llm_stalemate_neutral(self):
        """LLM returns stalemate phase — neutral."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.35)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.50,
                cycle_phase="stalemate",
                price_impact="neutral",
                reasoning="Elevated tension but no new developments. Stalemate phase.",
            )
        )

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_llm_unknown_direction(self):
        """LLM honestly returns UNKNOWN when it cannot assess the phase."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.2, article_count=5)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="UNKNOWN",
                confidence=0.40,
                cycle_phase="unknown",
                price_impact="uncertain",
                reasoning="Insufficient geopolitical signal to determine phase.",
            )
        )

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.40

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_thresholds(self):
        """If LLM call fails, agent falls back to threshold logic."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.75)

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence >= 0.60

    @pytest.mark.asyncio
    async def test_llm_invalid_json_falls_back(self):
        """If LLM returns invalid JSON, fall back to thresholds."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.05)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON at all")]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_no_client_uses_thresholds(self):
        """Without an LLM client, agent uses threshold logic."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.45)

        agent = GeopoliticalAgent(feed, client=None)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_high(self):
        """Confidence from LLM is clamped to max 0.78."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.8)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.95,
                reasoning="Extreme escalation.",
            )
        )

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence <= 0.78

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_low(self):
        """Confidence from LLM is clamped to min 0.40."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(escalation=0.2)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.10,
                reasoning="Low signal.",
            )
        )

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence >= 0.40

    @pytest.mark.asyncio
    async def test_one_llm_call_only(self):
        """Agent must make exactly ONE LLM call."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = GeopoliticalAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")
        assert client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_uses_correct_model(self):
        """Agent should use claude-sonnet-4-5."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = GeopoliticalAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")

        call_kwargs = client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_feed_failure_skips_llm(self):
        """If the feed is down, don't even call the LLM."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")

        client = AsyncMock()
        client.messages.create = AsyncMock()

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_response_with_markdown_fences(self):
        """LLM wraps JSON in markdown code fences -- agent should handle it."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        content = '```json\n{"direction": "BULLISH", "confidence": 0.65, "cycle_phase": "escalation", "price_impact": "upward", "reasoning": "Escalation.", "decay_triggers": ["Ceasefire in Middle East"]}\n```'
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.65

    @pytest.mark.asyncio
    async def test_llm_decay_triggers_are_specific(self):
        """LLM-provided decay triggers should be passed through."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        triggers = [
            "Iran-Saudi direct military confrontation",
            "UN Security Council resolution on Red Sea",
            "Houthi ceasefire agreement",
        ]
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.68,
                reasoning="Escalation in Red Sea.",
                decay_triggers=triggers,
            )
        )

        agent = GeopoliticalAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert len(signal.decay_triggers) >= 2
        assert any("Iran" in t for t in signal.decay_triggers)


# ─── Structural Agent Tests ─────────────────────────────────────────────────

class TestStructuralAgent:

    @pytest.mark.asyncio
    async def test_curated_view_crude_oil(self):
        """Without LLM client, agent returns curated view."""
        agent = StructuralAgent(client=None)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.55
        assert signal.temporal_layer == TemporalLayer.T3
        assert "crude" in signal.reasoning.lower() or "energy" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_curated_view_copper(self):
        """Copper has a bullish structural view."""
        agent = StructuralAgent(client=None)
        signal = await agent.run("commodity.metals.copper")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.65

    @pytest.mark.asyncio
    async def test_unknown_commodity_gets_default(self):
        """Unknown commodity paths get the default neutral view."""
        agent = StructuralAgent(client=None)
        signal = await agent.run("commodity.exotic.unobtanium")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.40

    @pytest.mark.asyncio
    async def test_signal_has_decay_triggers(self):
        agent = StructuralAgent(client=None)
        signal = await agent.run("commodity.energy.crude_oil")
        assert len(signal.decay_triggers) >= 2


# ─── Structural Agent LLM Reasoning Tests ───────────────────────────────────

class TestStructuralAgentLLM:
    """Tests for the LLM reasoning path of the structural agent."""

    def _make_llm_response(self, direction="BULLISH", confidence=0.60,
                           reasoning="Test structural reasoning.", decay_triggers=None):
        """Create a mock LLM response object."""
        if decay_triggers is None:
            decay_triggers = [
                "Major economy announces ban on ICE vehicles by 2030",
                "OPEC+ abandons supply discipline entirely",
                "Global recession causing sustained demand destruction",
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
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.65,
                reasoning="Supply discipline and energy transition demand support structural bullish case for copper.",
            )
        )

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.metals.copper")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.65
        assert signal.temporal_layer == TemporalLayer.T3
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_bearish_signal(self):
        """LLM returns bearish structural outlook."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BEARISH",
                confidence=0.55,
                reasoning="Energy transition accelerating, EV adoption faster than expected, structural demand decline for crude.",
            )
        )

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_llm_neutral_signal(self):
        """LLM returns neutral for mixed structural forces."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.48,
                reasoning="Structural forces are mixed — supply discipline offsets demand uncertainty.",
            )
        )

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.48

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_curated(self):
        """If LLM call fails, agent falls back to curated views."""
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        # Should fall back to curated: crude oil = NEUTRAL 0.55
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_llm_invalid_json_falls_back(self):
        """If LLM returns invalid JSON, fall back to curated views."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON at all")]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.metals.copper")
        # Should fall back to curated: copper = BULLISH 0.65
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.65

    @pytest.mark.asyncio
    async def test_no_client_uses_curated(self):
        """Without an LLM client, agent uses curated views."""
        agent = StructuralAgent(client=None)
        signal = await agent.run("commodity.metals.gold")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.58

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_high(self):
        """Confidence from LLM is clamped to max 0.72."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.95,  # Too high — should be clamped to 0.72
                reasoning="Very bullish.",
            )
        )

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.metals.copper")
        assert signal.confidence <= 0.72

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_low(self):
        """Confidence from LLM is clamped to min 0.40."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.10,  # Too low — should be clamped to 0.40
                reasoning="Very uncertain.",
            )
        )

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence >= 0.40

    @pytest.mark.asyncio
    async def test_llm_decay_triggers_are_specific(self):
        """LLM-provided decay triggers should be passed through."""
        triggers = [
            "Major economy announces ban on ICE vehicles by 2030",
            "OPEC+ abandons supply discipline entirely",
            "Global recession causing sustained demand destruction",
        ]
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.60,
                reasoning="Structural bull case.",
                decay_triggers=triggers,
            )
        )

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.metals.copper")
        assert len(signal.decay_triggers) >= 2
        assert any("ICE" in t or "OPEC" in t for t in signal.decay_triggers)

    @pytest.mark.asyncio
    async def test_one_llm_call_only(self):
        """Agent must make exactly ONE LLM call."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = StructuralAgent(client=client)
        await agent.run("commodity.energy.crude_oil")
        assert client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_uses_correct_model(self):
        """Agent should use claude-sonnet-4-5."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = StructuralAgent(client=client)
        await agent.run("commodity.energy.crude_oil")

        call_kwargs = client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_llm_response_with_markdown_fences(self):
        """LLM sometimes wraps JSON in markdown code fences — agent should handle it."""
        content = '```json\n{"direction": "NEUTRAL", "confidence": 0.55, "reasoning": "Mixed forces.", "decay_triggers": ["Major policy shift"]}\n```'
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = StructuralAgent(client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_llm_receives_curated_context(self):
        """LLM prompt should include the curated view as context."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = StructuralAgent(client=client)
        await agent.run("commodity.energy.crude_oil")

        call_args = client.messages.create.call_args
        prompt_content = call_args.kwargs["messages"][0]["content"]
        # Should contain the curated thesis for crude oil
        assert "crude" in prompt_content.lower() or "energy transition" in prompt_content.lower()
        assert "commodity.energy.crude_oil" in prompt_content


# ─── Weather Agent LLM Reasoning Tests ──────────────────────────────────────

class TestWeatherAgentLLM:
    """Tests for the LLM reasoning path of the weather agent."""

    def _make_weather_data(
        self, alert_count=10, severe_count=3,
        hurricane_active=False, drought_active=False, cold_snap_active=False,
    ):
        return FeedResult(
            data={
                "alert_count": alert_count,
                "severe_count": severe_count,
                "hurricane_active": hurricane_active,
                "drought_active": drought_active,
                "cold_snap_active": cold_snap_active,
                "alerts": [],
            },
            ok=True,
            fetched_at=1000.0,
        )

    def _make_llm_response(
        self, direction="BULLISH", confidence=0.65,
        reasoning="Test weather reasoning.", decay_triggers=None, layer="T1",
    ):
        """Create a mock LLM response object."""
        if decay_triggers is None:
            decay_triggers = [
                "Hurricane makes landfall and dissipates",
                "NOAA downgrades active alerts",
                "Weather system moves out of commodity-producing region",
            ]
        content = json.dumps({
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
            "decay_triggers": decay_triggers,
            "layer": layer,
        })
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]
        return mock_response

    @pytest.mark.asyncio
    async def test_llm_bullish_hurricane_energy(self):
        """LLM returns bullish for hurricane in energy domain."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(
            hurricane_active=True, severe_count=8,
        )

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.78,
                reasoning="Active hurricane in Gulf threatens 15% of US oil production. Refineries shutting down preemptively.",
                layer="T1",
            )
        )

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.78
        assert signal.temporal_layer == TemporalLayer.T1
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_bullish_drought_agriculture(self):
        """LLM returns bullish for drought in agriculture domain."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(
            drought_active=True, severe_count=5,
        )

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.72,
                reasoning="Drought conditions in Midwest crop belt. Corn and soybean yields expected to drop 20-30%.",
                layer="T2",
            )
        )

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.agriculture.corn")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.72
        assert signal.temporal_layer == TemporalLayer.T2

    @pytest.mark.asyncio
    async def test_llm_neutral_clear_weather(self):
        """LLM returns neutral when no significant weather events."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(
            alert_count=2, severe_count=0,
        )

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.50,
                reasoning="No significant weather events impacting commodity supply chains.",
            )
        )

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_thresholds(self):
        """If LLM call fails, agent falls back to threshold logic."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(
            hurricane_active=True,
        )

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        # Should fall back to threshold: hurricane + energy = BULLISH 0.80
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.80

    @pytest.mark.asyncio
    async def test_llm_invalid_json_falls_back(self):
        """If LLM returns invalid JSON, fall back to thresholds."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(
            cold_snap_active=True,
        )

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Not valid JSON at all")]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.natural_gas")
        # Should fall back to threshold: cold snap + energy = BULLISH 0.70
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.70

    @pytest.mark.asyncio
    async def test_no_client_uses_thresholds(self):
        """Without an LLM client, agent uses threshold logic."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(
            drought_active=True,
        )

        agent = WeatherAgent(feed, client=None)
        signal = await agent.run("commodity.agriculture.wheat")
        # Threshold: drought + agriculture = BULLISH 0.75
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.75

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_high(self):
        """Confidence from LLM is clamped to max 0.80."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(hurricane_active=True)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.95,  # Too high — should be clamped
                reasoning="Major hurricane.",
            )
        )

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence <= 0.80

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_low(self):
        """Confidence from LLM is clamped to min 0.30."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data()

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.10,  # Too low — should be clamped
                reasoning="Unclear.",
            )
        )

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence >= 0.30

    @pytest.mark.asyncio
    async def test_one_llm_call_only(self):
        """Agent must make exactly ONE LLM call."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(hurricane_active=True)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = WeatherAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")
        assert client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_uses_correct_model(self):
        """Agent should use claude-sonnet-4-5."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data()

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = WeatherAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")

        call_kwargs = client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_feed_failure_skips_llm(self):
        """If the feed is down, don't even call the LLM."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")

        client = AsyncMock()
        client.messages.create = AsyncMock()

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_decay_triggers_passed_through(self):
        """LLM-provided decay triggers should be passed through."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(hurricane_active=True)

        triggers = [
            "Hurricane makes landfall and dissipates",
            "NOAA downgrades hurricane to tropical storm",
            "Gulf oil platforms resume production",
        ]
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.75,
                reasoning="Active hurricane.",
                decay_triggers=triggers,
            )
        )

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert len(signal.decay_triggers) >= 2
        assert any("Hurricane" in t for t in signal.decay_triggers)

    @pytest.mark.asyncio
    async def test_llm_response_with_markdown_fences(self):
        """LLM sometimes wraps JSON in markdown code fences — agent should handle it."""
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = self._make_weather_data(cold_snap_active=True)

        content = '```json\n{"direction": "BULLISH", "confidence": 0.68, "reasoning": "Cold snap.", "decay_triggers": ["Temperature normalisation"], "layer": "T1"}\n```'
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = WeatherAgent(feed, client=client)
        signal = await agent.run("commodity.energy.natural_gas")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.68


# ─── Narrative Agent LLM Reasoning Tests ─────────────────────────────────────

class TestNarrativeAgentLLM:
    """Tests for the LLM reasoning path of the narrative agent."""

    def _make_feed_result(self, article_count=25, avg_tone=-1.5):
        return FeedResult(
            data={
                "article_count": article_count,
                "avg_tone": avg_tone,
            },
            ok=True,
            fetched_at=1000.0,
        )

    def _make_llm_response(self, direction="BULLISH", confidence=0.55,
                           reasoning="Test reasoning.", decay_triggers=None):
        """Create a mock LLM response object."""
        if decay_triggers is None:
            decay_triggers = [
                "Narrative reversal — tone shifts >2 points in 24h",
                "Major counter-narrative event (e.g. surprise data release)",
                "News volume drops below 10 articles/day on topic",
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
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=30, avg_tone=-3.2)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.60,
                reasoning="Strong fear narrative with 30 articles and deeply negative tone. Supply disruption concerns accelerating.",
            )
        )

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.60
        assert signal.temporal_layer == TemporalLayer.T1
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_bearish_signal(self):
        """LLM returns bearish — agent should produce bearish signal."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=25, avg_tone=2.5)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BEARISH",
                confidence=0.50,
                reasoning="Optimism narrative building. Complacency may signal bearish reversal.",
            )
        )

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_llm_neutral_signal(self):
        """LLM returns neutral for ambiguous narrative."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=15, avg_tone=0.2)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.40,
                reasoning="Balanced narrative with moderate volume. No clear momentum.",
            )
        )

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.40

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_thresholds(self):
        """If LLM call fails, agent falls back to threshold logic."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=30, avg_tone=-3.0)

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        # Should fall back to threshold: high volume + negative tone = BULLISH 0.60
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.60

    @pytest.mark.asyncio
    async def test_llm_invalid_json_falls_back(self):
        """If LLM returns invalid JSON, fall back to thresholds."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=3, avg_tone=0.5)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON at all")]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        # Should fall back to threshold: low volume = NEUTRAL 0.35
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.35

    @pytest.mark.asyncio
    async def test_no_client_uses_thresholds(self):
        """Without an LLM client, agent uses threshold logic."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=25, avg_tone=-1.5)

        agent = NarrativeAgent(feed, client=None)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_high(self):
        """Confidence from LLM is clamped to max 0.65 for narratives."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=50, avg_tone=-4.0)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.95,  # Too high — should be clamped to 0.65
                reasoning="Fear narrative.",
            )
        )

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence <= 0.65

    @pytest.mark.asyncio
    async def test_llm_confidence_clamped_low(self):
        """Confidence from LLM is clamped to min 0.30."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(article_count=10, avg_tone=0.0)

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="NEUTRAL",
                confidence=0.10,  # Too low — should be clamped to 0.30
                reasoning="Quiet.",
            )
        )

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.confidence >= 0.30

    @pytest.mark.asyncio
    async def test_one_llm_call_only(self):
        """Agent must make exactly ONE LLM call."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = NarrativeAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")
        assert client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_uses_correct_model(self):
        """Agent should use claude-sonnet-4-5."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response()
        )

        agent = NarrativeAgent(feed, client=client)
        await agent.run("commodity.energy.crude_oil")

        call_kwargs = client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_feed_failure_skips_llm(self):
        """If the feed is down, don't even call the LLM."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")

        client = AsyncMock()
        client.messages.create = AsyncMock()

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_response_with_markdown_fences(self):
        """LLM sometimes wraps JSON in markdown code fences — agent should handle it."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        content = '```json\n{"direction": "BULLISH", "confidence": 0.55, "reasoning": "Fear narrative.", "decay_triggers": ["Tone shifts >2 points"]}\n```'
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=mock_response)

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_llm_decay_triggers_passed_through(self):
        """LLM-provided decay triggers should be passed through."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result()

        triggers = [
            "Tone shifts >2 points in 24h",
            "OPEC meeting outcome announced",
            "Article volume drops below 5/day",
        ]
        client = AsyncMock()
        client.messages.create = AsyncMock(
            return_value=self._make_llm_response(
                direction="BULLISH",
                confidence=0.55,
                reasoning="Fear narrative building.",
                decay_triggers=triggers,
            )
        )

        agent = NarrativeAgent(feed, client=client)
        signal = await agent.run("commodity.energy.crude_oil")
        assert len(signal.decay_triggers) >= 2
        assert any("Tone" in t for t in signal.decay_triggers)
