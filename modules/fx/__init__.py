"""
FX Module — Foreign Exchange
Second plug into the oracle spine. Same contract as commodities, new domain.

Implements the OracleModule contract from core/registry.py.
Runs agent pool in parallel, collects signals, returns ModuleResponse.

Domain prefix: fx
Coverage: major pairs (EUR/USD, USD/JPY, GBP/USD, USD/CHF, AUD/USD, NZD/USD)
"""

import asyncio
from typing import Optional

import anthropic

from core.registry import (
    OracleModule, ModuleResponse, DecomposedQuery, DataFeed,
    Signal, SignalDirection, TemporalLayer, QueryType,
)
from core.temporal_engine import TemporalEngine
from modules.fx.agents.rate_differential_agent import RateDifferentialAgent
from modules.fx.agents.flow_agent import FlowAgent
from modules.fx.agents.sentiment_agent import SentimentAgent
from modules.commodities.feeds.gdelt import GDELTFeed


class FXModule(OracleModule):
    """
    Foreign Exchange asset class module.
    Covers: major FX pairs via rate differentials, capital flows, and sentiment.
    Reuses GDELT feed from commodities for geopolitical/sentiment data.
    """

    @property
    def id(self) -> str:
        return "fx.v1"

    @property
    def domain_prefix(self) -> str:
        return "fx"

    @property
    def query_types(self) -> list[QueryType]:
        return [QueryType.PREDICTIVE, QueryType.FACTUAL, QueryType.CAUSAL, QueryType.COMPARATIVE]

    @property
    def temporal_layers(self) -> list[TemporalLayer]:
        return [TemporalLayer.T0, TemporalLayer.T1, TemporalLayer.T2, TemporalLayer.T3]

    @property
    def confidence_range(self) -> tuple[float, float]:
        return (0.30, 0.85)

    @property
    def feeds(self) -> list[DataFeed]:
        return [
            DataFeed(
                id="gdelt_fx",
                name="GDELT FX-related Events",
                url="https://api.gdeltproject.org/api/v2/doc/doc",
                refresh_rate="15min",
                temporal_layer=TemporalLayer.T1,
                is_free=True,
            ),
        ]

    def __init__(self, client: anthropic.AsyncAnthropic):
        self.client = client
        self.temporal = TemporalEngine()

        # Feeds — reuse GDELT from commodities infrastructure
        self.gdelt_feed = GDELTFeed()

        # Agents
        self.rate_differential_agent = RateDifferentialAgent()
        self.flow_agent = FlowAgent(self.gdelt_feed)
        self.sentiment_agent = SentimentAgent(self.gdelt_feed)

    async def handle(self, query: DecomposedQuery) -> ModuleResponse:
        """
        Run all available agents in parallel, collect signals.
        """
        # ── Run agents ───────────────────────────────────────────────
        agent_tasks = [
            self.rate_differential_agent.run(query.domain_path),
            self.flow_agent.run(query.domain_path),
            self.sentiment_agent.run(query.domain_path),
        ]

        signals: list[Signal] = await asyncio.gather(*agent_tasks)

        # Filter out None signals (defensive)
        signals = [s for s in signals if s is not None]

        # ── Build response ───────────────────────────────────────────
        # Determine dominant direction from signals
        directional = [s for s in signals
                       if s.direction in (SignalDirection.BULLISH, SignalDirection.BEARISH)]

        if directional:
            bullish_weight = sum(s.confidence for s in directional
                                if s.direction == SignalDirection.BULLISH)
            bearish_weight = sum(s.confidence for s in directional
                                if s.direction == SignalDirection.BEARISH)
            if bullish_weight > bearish_weight:
                view = SignalDirection.BULLISH
            elif bearish_weight > bullish_weight:
                view = SignalDirection.BEARISH
            else:
                view = SignalDirection.NEUTRAL
        else:
            view = SignalDirection.UNKNOWN

        avg_confidence = (sum(s.confidence for s in signals) / len(signals)) if signals else 0.0

        # Build reasoning trace
        reasoning_trace = self.temporal.build_reasoning_trace(signals)

        # Collect invalidators from all signals
        all_invalidators = []
        for s in signals:
            all_invalidators.extend(s.decay_triggers[:2])

        # Sources for provenance
        sources = [
            {"agent": s.agent_id, "feed": s.source, "timestamp": s.generated_at}
            for s in signals
        ]

        return ModuleResponse(
            module_id=self.id,
            domain_path=query.domain_path,
            signals=signals,
            synthesised_view=view,
            confidence=round(avg_confidence, 3),
            reasoning_trace=reasoning_trace,
            invalidators=list(set(all_invalidators)),
            sources=sources,
            temporal_layer=query.temporal_layer,
        )

    async def health_check(self) -> dict:
        """Check all data feeds."""
        return {
            "module": self.id,
            "feeds": {
                "gdelt_fx": self.gdelt_feed.health(),
            },
        }

    async def decay_check(self, signal: Signal) -> bool:
        """
        Check if a signal is still valid.
        Returns True if valid, False if decayed.
        For now: time-based validity only. Trigger-based decay requires
        checking live data against the trigger conditions.
        """
        return self.temporal.is_valid(signal)
