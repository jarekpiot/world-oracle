"""
Commodities Module — The seed module.
First plug into the oracle spine. If this works, every future module is just a copy of the pattern.

Implements the OracleModule contract from core/registry.py.
Runs agent pool in parallel, collects signals, returns ModuleResponse.
"""

import asyncio
from typing import Optional

import anthropic

from core.registry import (
    OracleModule, ModuleResponse, DecomposedQuery, DataFeed,
    Signal, SignalDirection, TemporalLayer, QueryType,
)
from core.temporal_engine import TemporalEngine
from modules.commodities.agents.inventory_agent import InventoryAgent
from modules.commodities.agents.geopolitical_agent import GeopoliticalAgent
from modules.commodities.agents.weather_agent import WeatherAgent
from modules.commodities.agents.shipping_agent import ShippingAgent
from modules.commodities.agents.positioning_agent import PositioningAgent
from modules.commodities.agents.narrative_agent import NarrativeAgent
from modules.commodities.agents.structural_agent import StructuralAgent
from modules.commodities.agents.price_agent import PriceAgent
from modules.commodities.agents.breaking_agent import BreakingEventAgent
from modules.commodities.feeds.eia import EIAFeed
from modules.commodities.feeds.price import PriceFeed
from modules.commodities.feeds.gdelt import GDELTFeed
from modules.commodities.feeds.noaa import NOAAFeed
from modules.commodities.feeds.baltic import BalticDryFeed
from modules.commodities.feeds.cot import COTFeed


class CommoditiesModule(OracleModule):
    """
    Commodities asset class module.
    Covers: energy, metals, agriculture.
    Seed implementation: crude oil via EIA inventory data.
    """

    @property
    def id(self) -> str:
        return "commodities.v1"

    @property
    def domain_prefix(self) -> str:
        return "commodity"

    @property
    def query_types(self) -> list[QueryType]:
        return [QueryType.PREDICTIVE, QueryType.FACTUAL, QueryType.CAUSAL, QueryType.COMPARATIVE]

    @property
    def temporal_layers(self) -> list[TemporalLayer]:
        return [TemporalLayer.T0, TemporalLayer.T1, TemporalLayer.T2, TemporalLayer.T3]

    @property
    def confidence_range(self) -> tuple[float, float]:
        return (0.25, 0.88)

    @property
    def feeds(self) -> list[DataFeed]:
        return [
            DataFeed(
                id="eia_spot_price",
                name="EIA Daily Spot Prices",
                url="https://api.eia.gov/v2/petroleum/pri/spt/data/",
                refresh_rate="daily",
                temporal_layer=TemporalLayer.T0,
                is_free=True,
            ),
            DataFeed(
                id="eia_petroleum",
                name="EIA Weekly Petroleum Status",
                url="https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
                refresh_rate="weekly",
                temporal_layer=TemporalLayer.T2,
                is_free=True,
            ),
            DataFeed(
                id="gdelt_geopolitical",
                name="GDELT Geopolitical Events",
                url="https://api.gdeltproject.org/api/v2/doc/doc",
                refresh_rate="15min",
                temporal_layer=TemporalLayer.T1,
                is_free=True,
            ),
            DataFeed(
                id="noaa_weather",
                name="NOAA Weather Alerts",
                url="https://api.weather.gov/alerts/active",
                refresh_rate="6hr",
                temporal_layer=TemporalLayer.T1,
                is_free=True,
            ),
            DataFeed(
                id="baltic_dry",
                name="Baltic Dry Index",
                url="",
                refresh_rate="daily",
                temporal_layer=TemporalLayer.T2,
                is_free=False,
            ),
            DataFeed(
                id="cftc_cot",
                name="CFTC Commitment of Traders",
                url="https://www.cftc.gov/dea/newcot/deacmesf.txt",
                refresh_rate="weekly",
                temporal_layer=TemporalLayer.T2,
                is_free=True,
            ),
        ]

    def __init__(self, client: anthropic.AsyncAnthropic):
        self.client = client
        self.temporal = TemporalEngine()

        # Feeds
        self.eia_feed = EIAFeed()
        self.gdelt_feed = GDELTFeed()
        self.noaa_feed = NOAAFeed()
        self.baltic_feed = BalticDryFeed()
        self.cot_feed = COTFeed()
        self.price_feed = PriceFeed()

        # Agents — all 9 wired up (T0 through T3)
        self.price_agent = PriceAgent(self.price_feed)
        self.breaking_agent = BreakingEventAgent(self.gdelt_feed)
        self.inventory_agent = InventoryAgent(self.eia_feed, client=client)
        self.geopolitical_agent = GeopoliticalAgent(self.gdelt_feed)
        self.weather_agent = WeatherAgent(self.noaa_feed)
        self.shipping_agent = ShippingAgent(self.baltic_feed)
        self.positioning_agent = PositioningAgent(self.cot_feed)
        self.narrative_agent = NarrativeAgent(self.gdelt_feed)
        self.structural_agent = StructuralAgent()

    async def handle(self, query: DecomposedQuery) -> ModuleResponse:
        """
        Run all available agents in parallel, collect signals.
        Agents with no dependencies run concurrently (wave 0).
        """
        # ── Run agents ───────────────────────────────────────────────
        # Currently: inventory only. As agents are built, add them here.
        agent_tasks = [
            self.price_agent.run(query.domain_path),
            self.breaking_agent.run(query.domain_path),
            self.inventory_agent.run(query.domain_path),
            self.geopolitical_agent.run(query.domain_path),
            self.weather_agent.run(query.domain_path),
            self.shipping_agent.run(query.domain_path),
            self.positioning_agent.run(query.domain_path),
            self.narrative_agent.run(query.domain_path),
            self.structural_agent.run(query.domain_path),
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
                "eia_spot_price": self.price_feed.health(),
                "eia_petroleum": self.eia_feed.health(),
                "gdelt_geopolitical": self.gdelt_feed.health(),
                "noaa_weather": self.noaa_feed.health(),
                "baltic_dry": self.baltic_feed.health(),
                "cftc_cot": self.cot_feed.health(),
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
