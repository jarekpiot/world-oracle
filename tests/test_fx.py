"""
FX Module Tests
Tests the FX module, all three agents, and feed failure behaviour.
Run: python -m pytest tests/test_fx.py -v
"""

import pytest
from unittest.mock import MagicMock

from core.registry import (
    DecomposedQuery, QueryType, TemporalLayer, SignalDirection, OracleModule,
)
from modules.commodities.feeds.base import FeedResult
from modules.commodities.feeds.gdelt import GDELTFeed
from modules.fx import FXModule
from modules.fx.agents.rate_differential_agent import (
    RateDifferentialAgent, RATE_DIFFERENTIAL_VIEWS,
)
from modules.fx.agents.flow_agent import FlowAgent
from modules.fx.agents.sentiment_agent import SentimentAgent


# ─── FX Module Tests ─────────────────────────────────────────────────────────

class TestFXModule:

    def test_implements_oracle_module(self):
        client = MagicMock()
        module = FXModule(client)
        assert isinstance(module, OracleModule)

    def test_module_properties(self):
        client = MagicMock()
        module = FXModule(client)
        assert module.id == "fx.v1"
        assert module.domain_prefix == "fx"
        assert TemporalLayer.T0 in module.temporal_layers
        assert TemporalLayer.T1 in module.temporal_layers
        assert TemporalLayer.T2 in module.temporal_layers
        assert TemporalLayer.T3 in module.temporal_layers
        assert module.confidence_range == (0.30, 0.85)
        assert QueryType.PREDICTIVE in module.query_types
        assert QueryType.FACTUAL in module.query_types
        assert QueryType.CAUSAL in module.query_types
        assert QueryType.COMPARATIVE in module.query_types

    def test_feeds_list(self):
        client = MagicMock()
        module = FXModule(client)
        feeds = module.feeds
        assert len(feeds) >= 1
        assert feeds[0].id == "gdelt_fx"

    @pytest.mark.asyncio
    async def test_handle_returns_correct_signal_count(self):
        """Full module handle() returns one signal per agent (3 agents)."""
        client = MagicMock()
        module = FXModule(client)

        # Mock GDELT feed for flow and sentiment agents
        mock_feed = MagicMock(spec=GDELTFeed)
        mock_feed.fetch.return_value = FeedResult(
            data={
                "article_count": 30,
                "avg_tone": -3.0,
                "escalation_score": 0.7,
                "active_regions": ["middle_east"],
                "region_hits": {"middle_east": 5},
            },
            ok=True,
            fetched_at=1000.0,
        )
        module.gdelt_feed = mock_feed
        module.flow_agent = FlowAgent(mock_feed)
        module.sentiment_agent = SentimentAgent(mock_feed)

        query = DecomposedQuery(
            raw="Will EUR/USD rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="fx.major.eurusd",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.50,
            sub_tasks=[],
        )

        response = await module.handle(query)
        assert response.module_id == "fx.v1"
        assert len(response.signals) == 3  # rate_diff + flow + sentiment
        assert len(response.sources) == 3

    @pytest.mark.asyncio
    async def test_handle_with_feeds_down(self):
        """Module still returns a response when feeds are down — agents return UNKNOWN."""
        client = MagicMock()
        module = FXModule(client)

        mock_feed = MagicMock(spec=GDELTFeed)
        mock_feed.fetch.return_value = FeedResult(ok=False, error="timeout")
        module.gdelt_feed = mock_feed
        module.flow_agent = FlowAgent(mock_feed)
        module.sentiment_agent = SentimentAgent(mock_feed)

        query = DecomposedQuery(
            raw="Will EUR/USD rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="fx.major.eurusd",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.50,
            sub_tasks=[],
        )

        response = await module.handle(query)
        assert response.module_id == "fx.v1"
        # Still get 3 signals — rate_diff is structural (no feed), flow+sentiment UNKNOWN
        assert len(response.signals) == 3

        # Flow and sentiment should be UNKNOWN
        feed_agents = [s for s in response.signals if s.agent_id in ("flow_agent", "fx_sentiment_agent")]
        for s in feed_agents:
            assert s.direction == SignalDirection.UNKNOWN
            assert s.confidence == 0.25


# ─── Rate Differential Agent Tests ───────────────────────────────────────────

class TestRateDifferentialAgent:

    @pytest.mark.asyncio
    async def test_produces_signal(self):
        agent = RateDifferentialAgent()
        signal = await agent.run("fx.major.eurusd")
        assert signal is not None
        assert signal.agent_id == "rate_differential_agent"
        assert signal.temporal_layer in (TemporalLayer.T2, TemporalLayer.T3)

    @pytest.mark.asyncio
    async def test_has_structural_views_for_major_pairs(self):
        """Rate differential agent must have curated views for all major pairs."""
        agent = RateDifferentialAgent()
        major_pairs = ["fx.major.eurusd", "fx.major.usdjpy", "fx.major.gbpusd", "fx.major.usdchf"]
        for pair in major_pairs:
            assert pair in RATE_DIFFERENTIAL_VIEWS, f"Missing structural view for {pair}"
            signal = await agent.run(pair)
            assert signal.direction != SignalDirection.UNKNOWN
            assert signal.confidence >= 0.40

    @pytest.mark.asyncio
    async def test_unknown_pair_returns_neutral(self):
        agent = RateDifferentialAgent()
        signal = await agent.run("fx.exotic.usdtry")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.40

    @pytest.mark.asyncio
    async def test_decay_triggers_are_specific(self):
        agent = RateDifferentialAgent()
        signal = await agent.run("fx.major.eurusd")
        assert len(signal.decay_triggers) >= 2
        assert any("central bank" in t.lower() for t in signal.decay_triggers)

    @pytest.mark.asyncio
    async def test_valid_horizon_set(self):
        agent = RateDifferentialAgent()
        signal = await agent.run("fx.major.eurusd")
        assert signal.valid_horizon is not None
        assert "month" in signal.valid_horizon.lower()


# ─── Flow Agent Tests ────────────────────────────────────────────────────────

class TestFlowAgent:

    def _make_gdelt_result(self, escalation, article_count=30, avg_tone=-3.0):
        return FeedResult(
            data={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "escalation_score": escalation,
                "active_regions": ["middle_east"],
                "region_hits": {"middle_east": 5},
            },
            ok=True,
            fetched_at=1000.0,
        )

    @pytest.mark.asyncio
    async def test_produces_signal(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_gdelt_result(0.5)
        agent = FlowAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert signal is not None
        assert signal.agent_id == "flow_agent"

    @pytest.mark.asyncio
    async def test_high_escalation_risk_off(self):
        """High escalation = risk-off = bearish for EUR/USD (USD strengthens)."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_gdelt_result(0.8)
        agent = FlowAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert signal.direction == SignalDirection.BEARISH

    @pytest.mark.asyncio
    async def test_high_escalation_usdjpy_bearish(self):
        """High escalation = JPY safe haven wins = bearish USD/JPY."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_gdelt_result(0.8)
        agent = FlowAgent(feed)
        signal = await agent.run("fx.major.usdjpy")
        assert signal.direction == SignalDirection.BEARISH

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        """ZERO FABRICATION — if feed is down, return UNKNOWN."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")
        agent = FlowAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        assert "unavailable" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_decay_triggers_are_specific(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_gdelt_result(0.5)
        agent = FlowAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert len(signal.decay_triggers) >= 2
        # No vague triggers
        for trigger in signal.decay_triggers:
            assert len(trigger) > 20, f"Trigger too vague: {trigger}"


# ─── Sentiment Agent Tests ───────────────────────────────────────────────────

class TestSentimentAgent:

    @pytest.mark.asyncio
    async def test_produces_signal(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(
            data={"article_count": 25, "avg_tone": -1.5},
            ok=True,
            fetched_at=1000.0,
        )
        agent = SentimentAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert signal is not None
        assert signal.agent_id == "fx_sentiment_agent"
        assert signal.temporal_layer == TemporalLayer.T1

    @pytest.mark.asyncio
    async def test_strong_negative_is_bearish(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(
            data={"article_count": 30, "avg_tone": -3.0},
            ok=True,
            fetched_at=1000.0,
        )
        agent = SentimentAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence >= 0.45

    @pytest.mark.asyncio
    async def test_low_volume_is_neutral(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(
            data={"article_count": 3, "avg_tone": 0.0},
            ok=True,
            fetched_at=1000.0,
        )
        agent = SentimentAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.30

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        """ZERO FABRICATION — if feed is down, return UNKNOWN."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")
        agent = SentimentAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        assert "unavailable" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_decay_triggers_are_specific(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(
            data={"article_count": 25, "avg_tone": -1.5},
            ok=True,
            fetched_at=1000.0,
        )
        agent = SentimentAgent(feed)
        signal = await agent.run("fx.major.eurusd")
        assert len(signal.decay_triggers) >= 2
