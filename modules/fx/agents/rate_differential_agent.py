"""
Rate Differential Agent — T2/T3 (weeks → years)
Central bank rate differentials drive FX over the medium-to-long term.

Core thesis:
  Higher rates = stronger currency (capital flows toward yield)
  Widening differential = currency strengthening
  Narrowing differential = currency weakening

This is a curated structural view — updated when central bank policy shifts.
No live feed required. The Oracle Team maintains these views.

Confidence range: 0.45–0.75
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine


# Structural rate differential views — updated on central bank decision dates.
# direction = direction for the BASE currency (first in the pair)
# e.g. EUR/USD BULLISH = EUR strengthening vs USD
RATE_DIFFERENTIAL_VIEWS = {
    "fx.major.eurusd": {
        "direction": SignalDirection.BEARISH,
        "confidence": 0.60,
        "thesis": "ECB rate path is dovish relative to Fed. ECB cutting faster than Fed "
                  "as eurozone growth lags. Rate differential favours USD over EUR. "
                  "Structural capital flows toward higher US yields.",
        "horizon": "3-12 months",
        "layer": TemporalLayer.T2,
    },
    "fx.major.usdjpy": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.55,
        "thesis": "BoJ remains structurally behind the global tightening cycle. "
                  "Rate differential still heavily favours USD over JPY despite BoJ "
                  "policy normalisation attempts. Carry trade flows support USD/JPY upside, "
                  "but BoJ intervention risk caps gains.",
        "horizon": "3-12 months",
        "layer": TemporalLayer.T2,
    },
    "fx.major.gbpusd": {
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.50,
        "thesis": "BoE and Fed on broadly similar rate paths. UK growth fragility "
                  "offsets any marginal rate advantage. Rate differential is not a "
                  "strong driver for GBP/USD at current levels.",
        "horizon": "3-12 months",
        "layer": TemporalLayer.T2,
    },
    "fx.major.usdchf": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.55,
        "thesis": "SNB rate is structurally lower than Fed rate. Rate differential "
                  "favours USD. However, CHF safe-haven demand during risk-off episodes "
                  "can temporarily override the rate signal.",
        "horizon": "3-12 months",
        "layer": TemporalLayer.T2,
    },
}

# Default for pairs not explicitly mapped
DEFAULT_RATE_VIEW = {
    "direction": SignalDirection.NEUTRAL,
    "confidence": 0.40,
    "thesis": "No curated rate differential view for this pair. "
              "Structural analysis requires central bank policy research.",
    "horizon": "3-12 months",
    "layer": TemporalLayer.T3,
}


class RateDifferentialAgent:
    """
    Provides the T2/T3 rate differential backdrop for FX pairs.
    Updated on central bank decision dates. Sets the structural
    yield-driven direction that shorter-term agents lean on or push against.
    """

    AGENT_ID = "rate_differential_agent"

    def __init__(self):
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Return the rate differential view for the given FX pair.
        This agent doesn't hit a live feed — it holds curated views
        that are updated on central bank decision dates by the Oracle Team.
        """
        view = RATE_DIFFERENTIAL_VIEWS.get(domain_path, DEFAULT_RATE_VIEW)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="Oracle Team rate differential assessment",
            value={
                "thesis": view["thesis"],
                "horizon": view["horizon"],
            },
            direction=view["direction"],
            confidence=view["confidence"],
            layer=view["layer"],
            domain_path=domain_path,
            decay_triggers=[
                "Central bank surprise rate decision (unscheduled move or larger than expected)",
                "Inflation print significantly above/below consensus (>0.3% miss)",
                "Central bank forward guidance shift (hawkish-to-dovish or vice versa)",
                "Quarterly rate differential review by Oracle Team",
            ],
            reasoning=view["thesis"],
            valid_horizon=view["horizon"],
        )
