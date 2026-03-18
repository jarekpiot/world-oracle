"""
Crypto Structural Agent — T3 (months -> years)
The slow breath — where is crypto structurally?

This agent reads secular trends:
  Bitcoin halving cycle   -> supply-side shock every ~4 years
  Institutional adoption  -> ETF flows, corporate treasuries
  Ethereum scaling        -> L2 rollups, staking economics
  Solana ecosystem        -> high throughput vs centralisation tradeoff
  Regulatory maturity     -> framework clarity vs enforcement

This is the LEAST frequently updated agent (monthly cadence).
It sets the structural backdrop — the deep current beneath the waves.

Confidence range: 0.35-0.60
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine


# Structural views — updated infrequently based on macro regime shifts.
# These are starting positions, not predictions.
STRUCTURAL_VIEWS = {
    "crypto.bitcoin": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.60,
        "thesis": "Bitcoin halving cycle reduces new supply issuance. Institutional adoption "
                  "accelerating via spot ETF flows and corporate treasury allocation. "
                  "Digital gold thesis gaining mainstream acceptance. "
                  "Supply-side scarcity meets broadening demand base.",
        "horizon": "12-36 months",
    },
    "crypto.ethereum": {
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.50,
        "thesis": "Ethereum scaling progress via L2 rollups is strong but creates value "
                  "leakage concerns. Competition from alternative L1s intensifying. "
                  "Regulatory uncertainty around staking classification. "
                  "Deflationary tokenomics are structurally positive but execution risk remains.",
        "horizon": "12-24 months",
    },
    "crypto.solana": {
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.45,
        "thesis": "High performance blockchain with strong developer ecosystem growth. "
                  "Centralisation concerns persist — validator set is concentrated. "
                  "Past outage history creates reliability questions for institutional adoption. "
                  "DeFi and consumer app traction is genuine but early.",
        "horizon": "12-24 months",
    },
}

# Default for domains not explicitly mapped
DEFAULT_STRUCTURAL = {
    "direction": SignalDirection.NEUTRAL,
    "confidence": 0.35,
    "thesis": "No strong structural view for this crypto asset. "
              "Structural analysis requires domain-specific research and "
              "understanding of tokenomics, team, and competitive positioning.",
    "horizon": "12-24 months",
}


class CryptoStructuralAgent:
    """
    Provides the T3 structural backdrop for crypto — the slow breath.
    Updated infrequently (monthly). Sets the deep current direction.
    Other agents' signals are more actionable but this provides context.
    """

    AGENT_ID = "crypto_structural_agent"

    def __init__(self):
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Return the structural view for the given crypto domain.
        This agent doesn't hit a live feed — it holds curated structural views
        that are updated on a monthly cadence by the Oracle Team.
        """
        view = STRUCTURAL_VIEWS.get(domain_path, DEFAULT_STRUCTURAL)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="Oracle Team crypto structural assessment",
            value={
                "thesis": view["thesis"],
                "horizon": view["horizon"],
            },
            direction=view["direction"],
            confidence=view["confidence"],
            layer=TemporalLayer.T3,
            domain_path=domain_path,
            decay_triggers=[
                "Major regulatory framework enacted (e.g. US crypto bill signed)",
                "Protocol-level security breach or consensus failure",
                "Bitcoin halving event (supply schedule shift)",
                "Monthly structural review by Oracle Team",
            ],
            reasoning=view["thesis"],
            valid_horizon=view["horizon"],
        )
