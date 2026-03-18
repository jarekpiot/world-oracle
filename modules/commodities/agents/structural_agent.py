"""
Structural Agent — T3 (months → years)
The slow breath — where is the world structurally?

This agent reads secular trends:
  Energy transition     → coal declining, gas bridging, renewables rising
  Commodity supercycle  → 20-30 year demand waves (are we early or late?)
  Dollar cycle          → strong USD = headwind for commodities
  Demographic shift     → urbanisation, ageing populations
  De-globalisation      → supply chain reshoring, higher baseline costs

This is the LEAST frequently updated agent (monthly cadence).
It sets the structural backdrop — the deep current beneath the waves.

Confidence range: 0.40–0.72
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine


# Structural views — updated infrequently based on macro regime shifts.
# These are starting positions, not predictions.
# The agent's job is to hold the structural context that shorter-term
# agents can lean on or push against.
STRUCTURAL_VIEWS = {
    "commodity.energy.crude_oil": {
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.55,
        "thesis": "Energy transition creates long-term demand uncertainty for crude. "
                  "Near-term (2-5y) demand remains resilient due to developing world growth. "
                  "Supply discipline from OPEC+ supports prices but shale flexibility caps upside.",
        "horizon": "12-36 months",
    },
    "commodity.energy.natural_gas": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.60,
        "thesis": "Natural gas is the transition fuel. LNG demand structurally rising as "
                  "Europe diversifies from Russian supply and Asia coal-to-gas switching continues.",
        "horizon": "12-36 months",
    },
    "commodity.metals.copper": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.65,
        "thesis": "Electrification and energy transition are copper-intensive. "
                  "EV, grid, renewables all require more copper. Supply pipeline is thin.",
        "horizon": "18-36 months",
    },
    "commodity.metals.gold": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.58,
        "thesis": "Central bank buying (de-dollarisation), geopolitical uncertainty, "
                  "and eventual rate cutting cycle support structural gold demand.",
        "horizon": "12-24 months",
    },
    "commodity.agriculture.wheat": {
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.45,
        "thesis": "Climate change increases yield volatility but technology improves productivity. "
                  "Black Sea supply remains uncertain due to conflict.",
        "horizon": "12-24 months",
    },
}

# Default for domains not explicitly mapped
DEFAULT_STRUCTURAL = {
    "direction": SignalDirection.NEUTRAL,
    "confidence": 0.40,
    "thesis": "No strong structural view for this commodity. "
              "Structural analysis requires domain-specific research.",
    "horizon": "12-36 months",
}


class StructuralAgent:
    """
    Provides the T3 structural backdrop — the slow breath.
    Updated infrequently (monthly). Sets the deep current direction.
    Other agents' signals are more actionable but this provides context.
    """

    AGENT_ID = "structural_agent"

    def __init__(self):
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Return the structural view for the given domain.
        This agent doesn't hit a live feed — it holds curated structural views
        that are updated on a monthly cadence by the Oracle Team.
        """
        view = STRUCTURAL_VIEWS.get(domain_path, DEFAULT_STRUCTURAL)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="Oracle Team structural assessment",
            value={
                "thesis": view["thesis"],
                "horizon": view["horizon"],
            },
            direction=view["direction"],
            confidence=view["confidence"],
            layer=TemporalLayer.T3,
            domain_path=domain_path,
            decay_triggers=[
                "Major policy shift (e.g. new energy legislation)",
                "Structural demand destruction event",
                "Technology breakthrough altering supply/demand balance",
                "Monthly structural review by Oracle Team",
            ],
            reasoning=view["thesis"],
            valid_horizon=view["horizon"],
        )
