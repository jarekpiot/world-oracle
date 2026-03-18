"""
Crypto Module — Digital assets.
Second plug into the oracle spine. Same contract, same discipline.

Implements the OracleModule contract from core/registry.py.
Runs agent pool in parallel, collects signals, returns ModuleResponse.

Crypto-specific characteristics:
  - Narratives move faster than any other asset class
  - Regulation is THE structural driver
  - On-chain data is a unique signal source (pending live feed)
  - 24/7 markets — no close, no weekend
"""

import asyncio
from typing import Optional

import anthropic

from core.registry import (
    OracleModule, ModuleResponse, DecomposedQuery, DataFeed,
    Signal, SignalDirection, TemporalLayer, QueryType,
)
from core.temporal_engine import TemporalEngine
from modules.crypto.agents.onchain_agent import OnchainAgent
from modules.crypto.agents.narrative_agent import CryptoNarrativeAgent
from modules.crypto.agents.structural_agent import CryptoStructuralAgent
from modules.crypto.agents.regulation_agent import RegulationAgent
from modules.commodities.feeds.gdelt import GDELTFeed


class CryptoModule(OracleModule):
    """
    Crypto asset class module.
    Covers: bitcoin, ethereum, solana, and the broader digital asset space.
    Reuses GDELT feed for narrative and regulation signals.
    On-chain feed pending — agent returns UNKNOWN honestly.
    """

    @property
    def id(self) -> str:
        return "crypto.v1"

    @property
    def domain_prefix(self) -> str:
        return "crypto"

    @property
    def query_types(self) -> list[QueryType]:
        return [QueryType.PREDICTIVE, QueryType.FACTUAL, QueryType.CAUSAL, QueryType.COMPARATIVE]

    @property
    def temporal_layers(self) -> list[TemporalLayer]:
        return [TemporalLayer.T0, TemporalLayer.T1, TemporalLayer.T2, TemporalLayer.T3]

    @property
    def confidence_range(self) -> tuple[float, float]:
        return (0.25, 0.80)

    @property
    def feeds(self) -> list[DataFeed]:
        return [
            DataFeed(
                id="gdelt_crypto_narrative",
                name="GDELT Crypto Narrative",
                url="https://api.gdeltproject.org/api/v2/doc/doc",
                refresh_rate="15min",
                temporal_layer=TemporalLayer.T1,
                is_free=True,
            ),
            DataFeed(
                id="gdelt_crypto_regulation",
                name="GDELT Crypto Regulation",
                url="https://api.gdeltproject.org/api/v2/doc/doc",
                refresh_rate="15min",
                temporal_layer=TemporalLayer.T2,
                is_free=True,
            ),
            DataFeed(
                id="onchain_metrics",
                name="On-chain Metrics (pending)",
                url="",
                refresh_rate="15min",
                temporal_layer=TemporalLayer.T1,
                is_free=False,
                last_updated=None,
            ),
        ]

    def __init__(self, client: anthropic.AsyncAnthropic):
        self.client = client
        self.temporal = TemporalEngine()

        # Feeds — reuse GDELT, on-chain pending
        self.gdelt_feed = GDELTFeed()

        # Agents — all 4 wired up
        self.onchain_agent = OnchainAgent()
        self.narrative_agent = CryptoNarrativeAgent(self.gdelt_feed)
        self.structural_agent = CryptoStructuralAgent()
        self.regulation_agent = RegulationAgent(self.gdelt_feed)

    async def handle(self, query: DecomposedQuery) -> ModuleResponse:
        """
        Run all available agents in parallel, collect signals.
        """
        # ── Run agents ───────────────────────────────────────────────
        agent_tasks = [
            self.onchain_agent.run(query.domain_path),
            self.narrative_agent.run(query.domain_path),
            self.structural_agent.run(query.domain_path),
            self.regulation_agent.run(query.domain_path),
        ]

        signals: list[Signal] = await asyncio.gather(*agent_tasks)

        # Filter out None signals (shouldn't happen, but defensive)
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
                "gdelt_crypto_narrative": self.gdelt_feed.health(),
                "gdelt_crypto_regulation": self.gdelt_feed.health(),
                "onchain_metrics": {"status": "pending", "message": "On-chain feed not yet implemented"},
            },
        }

    async def decay_check(self, signal: Signal) -> bool:
        """
        Check if a signal is still valid.
        Returns True if valid, False if decayed.
        """
        return self.temporal.is_valid(signal)
