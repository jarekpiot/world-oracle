"""
Agent Tests — All 7 commodity agents.
Tests signal direction, confidence, ZERO FABRICATION compliance, and decay triggers.
Run: python -m pytest tests/test_agents.py -v
"""

import pytest
from unittest.mock import MagicMock

from core.registry import SignalDirection, TemporalLayer
from modules.commodities.feeds.base import FeedResult
from modules.commodities.feeds.gdelt import GDELTFeed
from modules.commodities.feeds.noaa import NOAAFeed
from modules.commodities.feeds.baltic import BalticDryFeed
from modules.commodities.feeds.cot import COTFeed
from modules.commodities.agents.geopolitical_agent import GeopoliticalAgent
from modules.commodities.agents.weather_agent import WeatherAgent
from modules.commodities.agents.shipping_agent import ShippingAgent
from modules.commodities.agents.positioning_agent import PositioningAgent
from modules.commodities.agents.narrative_agent import NarrativeAgent
from modules.commodities.agents.structural_agent import StructuralAgent


DOMAIN = "commodity.energy.crude_oil"


# ─── Geopolitical Agent ─────────────────────────────────────────────────────

class TestGeopoliticalAgent:

    def _make_feed(self, escalation, article_count=30, regions=None):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(
            data={
                "article_count": article_count,
                "avg_tone": -escalation * 5,
                "escalation_score": escalation,
                "active_regions": regions or [],
                "region_hits": {},
            },
            ok=True,
            fetched_at=1000.0,
        )
        return feed

    @pytest.mark.asyncio
    async def test_high_escalation_is_bullish(self):
        feed = self._make_feed(0.7, regions=["middle_east"])
        agent = GeopoliticalAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence >= 0.60

    @pytest.mark.asyncio
    async def test_moderate_escalation_is_bullish(self):
        feed = self._make_feed(0.4)
        agent = GeopoliticalAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_low_escalation_is_neutral(self):
        feed = self._make_feed(0.2)
        agent = GeopoliticalAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_calm_is_bearish(self):
        feed = self._make_feed(0.05)
        agent = GeopoliticalAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BEARISH

    @pytest.mark.asyncio
    async def test_feed_down_returns_unknown(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="timeout")
        agent = GeopoliticalAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25

    @pytest.mark.asyncio
    async def test_has_decay_triggers(self):
        feed = self._make_feed(0.5)
        agent = GeopoliticalAgent(feed)
        signal = await agent.run(DOMAIN)
        assert len(signal.decay_triggers) >= 2


# ─── Weather Agent ───────────────────────────────────────────────────────────

class TestWeatherAgent:

    def _make_feed(self, hurricane=False, drought=False, cold_snap=False, severe_count=0):
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = FeedResult(
            data={
                "alert_count": severe_count + 2,
                "severe_count": severe_count,
                "hurricane_active": hurricane,
                "drought_active": drought,
                "cold_snap_active": cold_snap,
                "alerts": [],
            },
            ok=True,
            fetched_at=1000.0,
        )
        return feed

    @pytest.mark.asyncio
    async def test_hurricane_energy_is_bullish(self):
        feed = self._make_feed(hurricane=True)
        agent = WeatherAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.80

    @pytest.mark.asyncio
    async def test_drought_agriculture_is_bullish(self):
        feed = self._make_feed(drought=True)
        agent = WeatherAgent(feed)
        signal = await agent.run("commodity.agriculture.wheat")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.75

    @pytest.mark.asyncio
    async def test_cold_snap_energy_is_bullish(self):
        feed = self._make_feed(cold_snap=True)
        agent = WeatherAgent(feed)
        signal = await agent.run("commodity.energy.natural_gas")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.70

    @pytest.mark.asyncio
    async def test_clear_skies_is_neutral(self):
        feed = self._make_feed()
        agent = WeatherAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_feed_down_returns_unknown(self):
        feed = MagicMock(spec=NOAAFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="timeout")
        agent = WeatherAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25


# ─── Shipping Agent ──────────────────────────────────────────────────────────

class TestShippingAgent:

    @pytest.mark.asyncio
    async def test_no_feed_returns_unknown(self):
        """BDI has no free API — agent should honestly return UNKNOWN."""
        feed = BalticDryFeed()
        agent = ShippingAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        assert "not connected" in signal.reasoning.lower() or "pending" in signal.reasoning.lower()


# ─── Positioning Agent ───────────────────────────────────────────────────────

class TestPositioningAgent:

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        """ZERO FABRICATION — feed failure = UNKNOWN, not a guess."""
        feed = MagicMock(spec=COTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")
        agent = PositioningAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25


# ─── Narrative Agent ─────────────────────────────────────────────────────────

class TestNarrativeAgent:

    def _make_feed(self, article_count, avg_tone):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(
            data={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "escalation_score": 0.3,
                "active_regions": [],
                "region_hits": {},
            },
            ok=True,
            fetched_at=1000.0,
        )
        return feed

    @pytest.mark.asyncio
    async def test_strong_negative_narrative_is_bullish(self):
        """Fear narrative = bullish for commodities (supply disruption concerns)."""
        feed = self._make_feed(article_count=30, avg_tone=-3.0)
        agent = NarrativeAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.60

    @pytest.mark.asyncio
    async def test_low_volume_is_neutral(self):
        feed = self._make_feed(article_count=2, avg_tone=-1.0)
        agent = NarrativeAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.35

    @pytest.mark.asyncio
    async def test_positive_narrative_is_bearish(self):
        feed = self._make_feed(article_count=25, avg_tone=2.0)
        agent = NarrativeAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BEARISH

    @pytest.mark.asyncio
    async def test_feed_down_returns_unknown(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="timeout")
        agent = NarrativeAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25


# ─── Structural Agent ────────────────────────────────────────────────────────

class TestStructuralAgent:

    @pytest.mark.asyncio
    async def test_crude_oil_has_structural_view(self):
        agent = StructuralAgent()
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.temporal_layer == TemporalLayer.T3
        assert signal.direction in (SignalDirection.BULLISH, SignalDirection.BEARISH, SignalDirection.NEUTRAL)
        assert signal.confidence > 0.0
        assert "transition" in signal.reasoning.lower() or "crude" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_copper_is_bullish(self):
        agent = StructuralAgent()
        signal = await agent.run("commodity.metals.copper")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.65

    @pytest.mark.asyncio
    async def test_unknown_domain_gets_default(self):
        agent = StructuralAgent()
        signal = await agent.run("commodity.exotic.unobtanium")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.40

    @pytest.mark.asyncio
    async def test_has_decay_triggers(self):
        agent = StructuralAgent()
        signal = await agent.run(DOMAIN)
        assert len(signal.decay_triggers) >= 2
        assert signal.temporal_layer == TemporalLayer.T3


# ─── Full Module Integration ─────────────────────────────────────────────────

class TestCommoditiesModuleFullAgent:

    @pytest.mark.asyncio
    async def test_all_agents_produce_signals(self):
        """Module should return 7 signals — one per agent."""
        from modules.commodities import CommoditiesModule
        from core.registry import DecomposedQuery, QueryType

        client = MagicMock()
        module = CommoditiesModule(client)

        # Mock all feeds that hit the network
        module.eia_feed = MagicMock()
        module.eia_feed.fetch.return_value = FeedResult(
            data={"readings": [], "latest": 440000, "previous": 443000,
                  "change": -3000, "unit": "thousand barrels",
                  "series": "weekly_crude_stocks_excl_spr"},
            ok=True, fetched_at=1000.0,
        )
        module.gdelt_feed = MagicMock()
        module.gdelt_feed.fetch.return_value = FeedResult(
            data={"article_count": 20, "avg_tone": -1.5, "escalation_score": 0.3,
                  "active_regions": [], "region_hits": {}},
            ok=True, fetched_at=1000.0,
        )
        module.noaa_feed = MagicMock()
        module.noaa_feed.fetch.return_value = FeedResult(
            data={"alert_count": 2, "severe_count": 0, "hurricane_active": False,
                  "drought_active": False, "cold_snap_active": False, "alerts": []},
            ok=True, fetched_at=1000.0,
        )

        # Mock price feed
        module.price_feed = MagicMock()
        module.price_feed.fetch.return_value = FeedResult(
            data={"price": 72.5, "previous": 71.0, "change": 1.5,
                  "pct_change": 2.113, "unit": "USD/barrel", "series": "WTI",
                  "period": "2025-03-14", "readings": []},
            ok=True, fetched_at=1000.0,
        )

        # Rebuild agents with mocked feeds
        from modules.commodities.agents.inventory_agent import InventoryAgent
        from modules.commodities.agents.geopolitical_agent import GeopoliticalAgent
        from modules.commodities.agents.weather_agent import WeatherAgent
        from modules.commodities.agents.shipping_agent import ShippingAgent
        from modules.commodities.agents.positioning_agent import PositioningAgent
        from modules.commodities.agents.narrative_agent import NarrativeAgent
        from modules.commodities.agents.price_agent import PriceAgent

        module.price_agent = PriceAgent(module.price_feed)
        module.inventory_agent = InventoryAgent(module.eia_feed)
        module.geopolitical_agent = GeopoliticalAgent(module.gdelt_feed)
        module.weather_agent = WeatherAgent(module.noaa_feed)
        module.shipping_agent = ShippingAgent(BalticDryFeed())
        module.positioning_agent = PositioningAgent(COTFeed())
        module.narrative_agent = NarrativeAgent(module.gdelt_feed)
        # structural_agent needs no feed

        query = DecomposedQuery(
            raw="Will crude oil rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="commodity.energy.crude_oil",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.65,
            sub_tasks=[],
        )

        response = await module.handle(query)
        assert len(response.signals) == 8
        assert response.module_id == "commodities.v1"

        # Check we have signals from all agents
        agent_ids = {s.agent_id for s in response.signals}
        assert "price_agent" in agent_ids
        assert "inventory_agent" in agent_ids
        assert "geopolitical_agent" in agent_ids
        assert "weather_agent" in agent_ids
        assert "shipping_agent" in agent_ids
        assert "positioning_agent" in agent_ids
        assert "narrative_agent" in agent_ids
        assert "structural_agent" in agent_ids

        # Check temporal coverage — all four layers now
        layers = {s.temporal_layer for s in response.signals}
        assert TemporalLayer.T0 in layers  # price
        assert TemporalLayer.T2 in layers  # inventory
        assert TemporalLayer.T3 in layers  # structural
