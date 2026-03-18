"""
World Oracle — Foundation Tests
Validate the spine before plugging in any modules.
Run: python -m pytest tests/ -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from core.registry import (
    Signal, DecomposedQuery, ModuleResponse, DataFeed,
    QueryType, TemporalLayer, SignalDirection,
    OracleModule, ModuleRegistry
)
from core.temporal_engine import TemporalEngine
from core.confidence_engine import ConfidenceEngine
from output.formatter import format_oracle_response


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_signal(
    agent_id="inventory_agent",
    direction=SignalDirection.BULLISH,
    confidence=0.75,
    layer=TemporalLayer.T2,
    domain="commodity.energy.crude_oil",
) -> Signal:
    return Signal(
        agent_id=agent_id,
        source="test_feed",
        value={"test": True},
        direction=direction,
        confidence=confidence,
        temporal_layer=layer,
        generated_at=datetime.now(timezone.utc).isoformat(),
        valid_horizon="8 weeks",
        decay_triggers=["OPEC surprise output increase", "China PMI miss"],
        domain_path=domain,
        reasoning="Test signal for unit testing",
    )


# ─── Temporal Engine Tests ────────────────────────────────────────────────────

class TestTemporalEngine:

    def setup_method(self):
        self.engine = TemporalEngine()

    def test_tag_signal_returns_signal(self):
        signal = self.engine.tag_signal(
            agent_id="inventory_agent",
            source="EIA",
            value={"draw": -2.1},
            direction=SignalDirection.BULLISH,
            confidence=0.78,
            layer=TemporalLayer.T2,
            domain_path="commodity.energy.crude_oil",
            decay_triggers=["OPEC surprise"],
            reasoning="Inventory draw is bullish for crude",
        )
        assert isinstance(signal, Signal)
        assert signal.agent_id == "inventory_agent"
        assert signal.confidence == 0.78
        assert signal.temporal_layer == TemporalLayer.T2

    def test_different_layers_not_conflicting(self):
        """T1 bearish + T2 bullish = NOT a conflict. Different horizons."""
        s1 = make_signal(direction=SignalDirection.BEARISH, layer=TemporalLayer.T1)
        s2 = make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T2)
        assert self.engine.are_conflicting(s1, s2) is False

    def test_same_layer_opposite_direction_is_conflict(self):
        s1 = make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T2)
        s2 = make_signal(direction=SignalDirection.BEARISH, layer=TemporalLayer.T2)
        assert self.engine.are_conflicting(s1, s2) is True

    def test_alignment_score_all_bullish(self):
        signals = [
            make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T3),
            make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T2),
            make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T1),
        ]
        score = self.engine.alignment_score(signals)
        assert score == 1.0

    def test_alignment_score_mixed(self):
        """A perfect directional split on one layer = 0 alignment — correct, not a bug."""
        signals = [
            make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T2),
            make_signal(direction=SignalDirection.BEARISH, layer=TemporalLayer.T2),
        ]
        score = self.engine.alignment_score(signals)
        assert score == 0.0  # split = no alignment

    def test_alignment_score_partial(self):
        """Two layers bullish, one bearish = 0.67 alignment."""
        signals = [
            make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T3),
            make_signal(direction=SignalDirection.BULLISH, layer=TemporalLayer.T2),
            make_signal(direction=SignalDirection.BEARISH, layer=TemporalLayer.T1),
        ]
        score = self.engine.alignment_score(signals)
        assert round(score, 2) == 0.67

    def test_reasoning_trace_structure(self):
        signals = [
            make_signal(layer=TemporalLayer.T3, direction=SignalDirection.BULLISH),
            make_signal(layer=TemporalLayer.T2, direction=SignalDirection.BULLISH),
        ]
        trace = self.engine.build_reasoning_trace(signals)
        assert "structural" in trace
        assert "strategic" in trace
        assert "tactical" in trace
        assert trace["structural"]["status"] == "bullish"
        assert trace["tactical"]["status"] == "no signal"

    def test_decay_summary_counts_triggers(self):
        s1 = make_signal()
        s2 = make_signal()
        s1.decay_triggers = ["OPEC surprise", "China PMI miss"]
        s2.decay_triggers = ["OPEC surprise", "USD spike"]
        summary = self.engine.decay_summary([s1, s2])
        assert summary["OPEC surprise"] == 2
        assert summary["China PMI miss"] == 1


# ─── Confidence Engine Tests ─────────────────────────────────────────────────

class TestConfidenceEngine:

    def setup_method(self):
        self.engine = ConfidenceEngine()

    def test_no_signals_returns_abstain(self):
        result = self.engine.score([], threshold=0.65)
        assert result.meets_threshold is False
        assert result.score == 0.0
        assert result.abstain_reason is not None

    def test_strong_signals_meet_threshold(self):
        signals = [
            make_signal("inventory_agent", SignalDirection.BULLISH, 0.85),
            make_signal("geopolitical_agent", SignalDirection.BULLISH, 0.80),
            make_signal("shipping_agent", SignalDirection.BULLISH, 0.78),
        ]
        result = self.engine.score(signals, threshold=0.65)
        assert result.meets_threshold is True
        assert result.verdict == SignalDirection.BULLISH
        assert result.score > 0.65

    def test_weak_signals_abstain(self):
        signals = [
            make_signal("narrative_agent", SignalDirection.BULLISH, 0.35),
            make_signal("fallback", SignalDirection.NEUTRAL, 0.30),
        ]
        result = self.engine.score(signals, threshold=0.65)
        assert result.meets_threshold is False
        assert result.abstain_reason is not None

    def test_conflicting_signals_reduce_confidence(self):
        signals_aligned = [
            make_signal("inventory_agent", SignalDirection.BULLISH, 0.80),
            make_signal("shipping_agent", SignalDirection.BULLISH, 0.75),
        ]
        signals_mixed = [
            make_signal("inventory_agent", SignalDirection.BULLISH, 0.80),
            make_signal("shipping_agent", SignalDirection.BEARISH, 0.75),
        ]
        result_aligned = self.engine.score(signals_aligned, 0.50, alignment_score=1.0)
        result_mixed   = self.engine.score(signals_mixed,   0.50, alignment_score=0.5)
        assert result_aligned.score > result_mixed.score

    def test_verdict_follows_weighted_majority(self):
        signals = [
            make_signal("inventory_agent",    SignalDirection.BULLISH, 0.85),
            make_signal("geopolitical_agent", SignalDirection.BULLISH, 0.80),
            make_signal("narrative_agent",    SignalDirection.BEARISH, 0.55),
        ]
        result = self.engine.score(signals, 0.50)
        assert result.verdict == SignalDirection.BULLISH


# ─── Module Registry Tests ───────────────────────────────────────────────────

class TestModuleRegistry:

    def setup_method(self):
        self.registry = ModuleRegistry()

    def _make_mock_module(self, prefix="commodity", module_id="test.module"):
        m = MagicMock(spec=OracleModule)
        m.id = module_id
        m.domain_prefix = prefix
        m.query_types = [QueryType.PREDICTIVE]
        m.temporal_layers = [TemporalLayer.T2]
        m.confidence_range = (0.4, 0.9)
        return m

    def test_register_and_resolve(self):
        module = self._make_mock_module("commodity", "commodities.energy")
        self.registry.register(module)
        resolved = self.registry.resolve("commodity.energy.crude_oil")
        assert resolved is module

    def test_unknown_domain_returns_fallback(self):
        fallback = self._make_mock_module("fallback", "fallback.generic")
        self.registry.register(fallback, is_fallback=True)
        resolved = self.registry.resolve("unknown.domain.xyz")
        assert resolved is fallback

    def test_no_fallback_returns_none(self):
        resolved = self.registry.resolve("nonexistent.domain")
        assert resolved is None

    def test_list_modules(self):
        m1 = self._make_mock_module("commodity", "commodities.energy")
        m2 = self._make_mock_module("fx", "fx.major")
        self.registry.register(m1)
        self.registry.register(m2)
        modules = self.registry.list_modules()
        assert len(modules) == 2
        ids = [m["id"] for m in modules]
        assert "commodities.energy" in ids
        assert "fx.major" in ids


# ─── Formatter Tests ─────────────────────────────────────────────────────────

class TestFormatter:

    def _make_confidence(self, score=0.72, meets=True):
        from core.confidence_engine import ConfidenceResult
        return ConfidenceResult(
            score=score,
            band=(score-0.06, score+0.06),
            meets_threshold=meets,
            verdict=SignalDirection.BULLISH,
            limiting_factor="test",
            alignment_score=0.85,
            signal_count=4,
            abstain_reason=None if meets else "Below threshold",
        )

    def test_abstain_response_structure(self):
        conf = self._make_confidence(score=0.45, meets=False)
        result = format_oracle_response("test query", "commodity.energy", {}, conf, [])
        assert result["status"] == "INSUFFICIENT_SIGNAL"
        assert "oracle_says" in result
        assert "insufficient signal" in result["oracle_says"].lower()

    def test_valid_response_structure(self):
        conf = self._make_confidence(score=0.72, meets=True)
        synthesis = {
            "synthesised_view": "bullish",
            "dominant_thesis": "Supply tightening",
            "time_horizon": "T2 — 6 weeks",
            "invalidators": ["OPEC surprise"],
            "devils_advocate": "China demand could disappoint",
            "conflicts_found": [],
            "key_supporting_signals": [],
            "reasoning": "test",
            "reasoning_trace": {},
        }
        result = format_oracle_response("test query", "commodity.energy", synthesis, conf, [])
        assert result["status"] == "ORACLE_RESPONSE"
        assert result["view"]["direction"] == "bullish"
        assert result["view"]["confidence"] == 0.72
        assert len(result["risk"]["invalidators"]) > 0
