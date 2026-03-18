"""
Crypto Module Tests
Tests the crypto module, all four agents, and feed failure handling.
Run: python -m pytest tests/test_crypto.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.registry import (
    DecomposedQuery, QueryType, TemporalLayer, SignalDirection, OracleModule,
)
from modules.crypto import CryptoModule
from modules.crypto.agents.onchain_agent import OnchainAgent
from modules.crypto.agents.narrative_agent import CryptoNarrativeAgent
from modules.crypto.agents.structural_agent import CryptoStructuralAgent, STRUCTURAL_VIEWS
from modules.crypto.agents.regulation_agent import RegulationAgent
from modules.commodities.feeds.base import FeedResult
from modules.commodities.feeds.gdelt import GDELTFeed


# ─── Module Tests ─────────────────────────────────────────────────────────────

class TestCryptoModule:

    def test_implements_oracle_module(self):
        client = MagicMock()
        module = CryptoModule(client)
        assert isinstance(module, OracleModule)

    def test_module_properties(self):
        client = MagicMock()
        module = CryptoModule(client)
        assert module.id == "crypto.v1"
        assert module.domain_prefix == "crypto"
        assert module.confidence_range == (0.25, 0.80)
        assert TemporalLayer.T0 in module.temporal_layers
        assert TemporalLayer.T1 in module.temporal_layers
        assert TemporalLayer.T2 in module.temporal_layers
        assert TemporalLayer.T3 in module.temporal_layers

    def test_query_types(self):
        client = MagicMock()
        module = CryptoModule(client)
        assert QueryType.PREDICTIVE in module.query_types
        assert QueryType.FACTUAL in module.query_types
        assert QueryType.CAUSAL in module.query_types
        assert QueryType.COMPARATIVE in module.query_types

    def test_feeds_list(self):
        client = MagicMock()
        module = CryptoModule(client)
        feeds = module.feeds
        assert len(feeds) >= 3
        feed_ids = [f.id for f in feeds]
        assert "gdelt_crypto_narrative" in feed_ids
        assert "gdelt_crypto_regulation" in feed_ids
        assert "onchain_metrics" in feed_ids

    @pytest.mark.asyncio
    async def test_handle_returns_four_signals(self):
        """Full handle() should return 4 signals — one per agent."""
        client = MagicMock()
        module = CryptoModule(client)

        # Mock the GDELT feed for narrative and regulation agents
        mock_feed = MagicMock(spec=GDELTFeed)
        mock_feed.fetch.return_value = FeedResult(
            data={
                "article_count": 25,
                "avg_tone": -1.5,
                "escalation_score": 0.3,
                "active_regions": [],
                "region_hits": {},
            },
            ok=True,
            fetched_at=1000.0,
        )
        module.gdelt_feed = mock_feed
        module.narrative_agent = CryptoNarrativeAgent(mock_feed)
        module.regulation_agent = RegulationAgent(mock_feed)

        query = DecomposedQuery(
            raw="Will bitcoin rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="crypto.bitcoin",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.50,
            sub_tasks=[],
        )

        response = await module.handle(query)
        assert response.module_id == "crypto.v1"
        assert len(response.signals) == 4
        assert len(response.sources) == 4

    @pytest.mark.asyncio
    async def test_handle_with_feeds_down(self):
        """Module still returns a response when feeds are down — UNKNOWN signals."""
        client = MagicMock()
        module = CryptoModule(client)

        mock_feed = MagicMock(spec=GDELTFeed)
        mock_feed.fetch.return_value = FeedResult(ok=False, error="timeout")
        module.gdelt_feed = mock_feed
        module.narrative_agent = CryptoNarrativeAgent(mock_feed)
        module.regulation_agent = RegulationAgent(mock_feed)

        query = DecomposedQuery(
            raw="Will bitcoin rise?",
            query_type=QueryType.PREDICTIVE,
            domain_path="crypto.bitcoin",
            temporal_layer=TemporalLayer.T2,
            confidence_threshold=0.50,
            sub_tasks=[],
        )

        response = await module.handle(query)
        assert response.module_id == "crypto.v1"
        # Should still get 4 signals (onchain=UNKNOWN, narrative=UNKNOWN,
        # structural=has view, regulation=UNKNOWN)
        assert len(response.signals) == 4


# ─── On-chain Agent Tests ─────────────────────────────────────────────────────

class TestOnchainAgent:

    @pytest.mark.asyncio
    async def test_returns_unknown_honestly(self):
        """ZERO FABRICATION — no feed, no fabricated data."""
        agent = OnchainAgent()
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        assert "pending" in signal.source.lower() or "pending" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_has_decay_triggers(self):
        agent = OnchainAgent()
        signal = await agent.run("crypto.bitcoin")
        assert len(signal.decay_triggers) >= 2

    @pytest.mark.asyncio
    async def test_temporal_layer(self):
        agent = OnchainAgent()
        signal = await agent.run("crypto.bitcoin")
        assert signal.temporal_layer == TemporalLayer.T1

    @pytest.mark.asyncio
    async def test_includes_pending_metrics(self):
        agent = OnchainAgent()
        signal = await agent.run("crypto.bitcoin")
        assert "pending_metrics" in signal.value
        assert len(signal.value["pending_metrics"]) >= 3


# ─── Narrative Agent Tests ────────────────────────────────────────────────────

class TestCryptoNarrativeAgent:

    def _make_feed_result(self, article_count, avg_tone):
        return FeedResult(
            data={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "escalation_score": 0.0,
                "active_regions": [],
                "region_hits": {},
            },
            ok=True,
            fetched_at=1000.0,
        )

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        """ZERO FABRICATION — feed down = UNKNOWN."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")
        agent = CryptoNarrativeAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        assert "unavailable" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_low_volume_is_neutral(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(3, 0.5)
        agent = CryptoNarrativeAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.30

    @pytest.mark.asyncio
    async def test_extreme_negative_volume_is_bearish(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(50, -3.0)
        agent = CryptoNarrativeAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.55

    @pytest.mark.asyncio
    async def test_euphoric_narrative_is_bullish(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(50, 2.0)
        agent = CryptoNarrativeAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_confidence_within_range(self):
        """Confidence must be in 0.30-0.55 range."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(20, -1.0)
        agent = CryptoNarrativeAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert 0.30 <= signal.confidence <= 0.55

    @pytest.mark.asyncio
    async def test_has_decay_triggers(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(20, -1.0)
        agent = CryptoNarrativeAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert len(signal.decay_triggers) >= 2

    @pytest.mark.asyncio
    async def test_temporal_layer(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(20, 0.0)
        agent = CryptoNarrativeAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.temporal_layer == TemporalLayer.T1


# ─── Structural Agent Tests ──────────────────────────────────────────────────

class TestCryptoStructuralAgent:

    @pytest.mark.asyncio
    async def test_bitcoin_is_bullish(self):
        agent = CryptoStructuralAgent()
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.60

    @pytest.mark.asyncio
    async def test_ethereum_is_neutral(self):
        agent = CryptoStructuralAgent()
        signal = await agent.run("crypto.ethereum")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_solana_is_neutral(self):
        agent = CryptoStructuralAgent()
        signal = await agent.run("crypto.solana")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.45

    @pytest.mark.asyncio
    async def test_unknown_asset_defaults(self):
        agent = CryptoStructuralAgent()
        signal = await agent.run("crypto.dogecoin")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.35

    @pytest.mark.asyncio
    async def test_structural_views_exist(self):
        """Structural views must exist for bitcoin, ethereum, solana."""
        assert "crypto.bitcoin" in STRUCTURAL_VIEWS
        assert "crypto.ethereum" in STRUCTURAL_VIEWS
        assert "crypto.solana" in STRUCTURAL_VIEWS

    @pytest.mark.asyncio
    async def test_temporal_layer_is_t3(self):
        agent = CryptoStructuralAgent()
        signal = await agent.run("crypto.bitcoin")
        assert signal.temporal_layer == TemporalLayer.T3

    @pytest.mark.asyncio
    async def test_has_decay_triggers(self):
        agent = CryptoStructuralAgent()
        signal = await agent.run("crypto.bitcoin")
        assert len(signal.decay_triggers) >= 2


# ─── Regulation Agent Tests ──────────────────────────────────────────────────

class TestRegulationAgent:

    def _make_feed_result(self, article_count, avg_tone):
        return FeedResult(
            data={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "escalation_score": 0.0,
                "active_regions": [],
                "region_hits": {},
            },
            ok=True,
            fetched_at=1000.0,
        )

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        """ZERO FABRICATION — feed down = UNKNOWN."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")
        agent = RegulationAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25

    @pytest.mark.asyncio
    async def test_positive_regulation_is_bullish(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(15, 1.5)
        agent = RegulationAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.65

    @pytest.mark.asyncio
    async def test_negative_regulation_is_bearish(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(15, -2.5)
        agent = RegulationAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.65

    @pytest.mark.asyncio
    async def test_low_volume_is_neutral(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(2, 0.0)
        agent = RegulationAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.40

    @pytest.mark.asyncio
    async def test_temporal_layer_is_t2(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(10, 0.0)
        agent = RegulationAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert signal.temporal_layer == TemporalLayer.T2

    @pytest.mark.asyncio
    async def test_has_decay_triggers(self):
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(10, 0.0)
        agent = RegulationAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert len(signal.decay_triggers) >= 2

    @pytest.mark.asyncio
    async def test_confidence_within_range(self):
        """Confidence must be in 0.40-0.65 range."""
        feed = MagicMock(spec=GDELTFeed)
        feed.fetch.return_value = self._make_feed_result(10, 0.0)
        agent = RegulationAgent(feed)
        signal = await agent.run("crypto.bitcoin")
        assert 0.40 <= signal.confidence <= 0.65
