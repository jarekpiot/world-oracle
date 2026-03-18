"""
Flow Agent — T1/T2 (hours → months)
Capital flow direction drives FX in the medium term.

Core thesis:
  Risk-off = USD, JPY, CHF strengthen (safe havens)
  Risk-on  = AUD, NZD, EM currencies strengthen (carry/growth)

Uses GDELT geopolitical risk as a proxy for risk appetite.
High geopolitical tension = risk-off = safe haven bid.
Low tension = risk-on = carry trade flows.

Confidence range: 0.35–0.70
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


# Which currencies benefit from which risk regime
SAFE_HAVEN_PAIRS = {
    "fx.major.usdjpy",     # USD and JPY are both safe havens — JPY wins in extreme risk-off
    "fx.major.usdchf",     # CHF is a safe haven — CHF strengthens in risk-off
    "fx.major.eurusd",     # USD strengthens vs EUR in risk-off
    "fx.major.gbpusd",     # USD strengthens vs GBP in risk-off
}

# Pairs where the base currency benefits from risk-on
RISK_ON_PAIRS = {
    "fx.major.audusd",     # AUD is a risk-on / commodity currency
    "fx.major.nzdusd",     # NZD is a risk-on / commodity currency
}

# Escalation thresholds (same as geopolitical agent)
ESCALATION_HIGH = 0.6
ESCALATION_MODERATE = 0.3
ESCALATION_LOW = 0.15


class FlowAgent:
    """
    Reads capital flow direction via geopolitical risk proxy.
    Maps risk regime to FX pair direction.
    Risk-off = safe havens bid. Risk-on = carry/growth currencies bid.
    """

    AGENT_ID = "flow_agent"

    def __init__(self, gdelt_feed: GDELTFeed):
        self.feed = gdelt_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch geopolitical risk and map to capital flow direction for FX.
        """
        result = self.feed.fetch(
            query="geopolitical risk crisis war sanctions conflict currency"
        )

        # ── No data → honest UNKNOWN ────────────────────────────────
        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T1,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="GDELT feed unavailable — no capital flow signal this cycle.",
            )

        data = result.data
        escalation = data.get("escalation_score", 0.0)
        article_count = data.get("article_count", 0)

        direction, confidence, reasoning, layer = self._interpret(
            escalation, article_count, domain_path
        )

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT geopolitical risk (flow proxy)",
            value={
                "escalation_score": escalation,
                "article_count": article_count,
                "risk_regime": "risk-off" if escalation >= ESCALATION_MODERATE else "risk-on",
            },
            direction=direction,
            confidence=confidence,
            layer=layer,
            domain_path=domain_path,
            decay_triggers=[
                "Major geopolitical de-escalation (ceasefire, diplomatic deal)",
                "Risk sentiment reversal (VIX drop >5 points in 24h)",
                "Central bank emergency intervention in FX markets",
                "Safe haven flow exhaustion (positioning extremes)",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _interpret(
        self, escalation: float, article_count: int, domain_path: str
    ) -> tuple[SignalDirection, float, str, TemporalLayer]:
        """
        Map escalation score + pair type to direction and confidence.
        High escalation = risk-off = safe haven currencies strengthen.
        """
        is_safe_haven_pair = domain_path in SAFE_HAVEN_PAIRS
        is_risk_on_pair = domain_path in RISK_ON_PAIRS

        if escalation >= ESCALATION_HIGH:
            # Risk-off regime
            if domain_path == "fx.major.usdjpy":
                # Both safe havens — JPY tends to win in extreme risk-off
                return (
                    SignalDirection.BEARISH,
                    min(0.70, 0.50 + escalation * 0.2),
                    f"High geopolitical risk ({escalation:.2f}). Risk-off regime. "
                    f"JPY safe-haven demand likely to overpower USD — bearish USD/JPY.",
                    TemporalLayer.T1,
                )
            elif domain_path == "fx.major.usdchf":
                # CHF safe haven — strengthens vs USD in risk-off
                return (
                    SignalDirection.BEARISH,
                    min(0.65, 0.45 + escalation * 0.2),
                    f"High geopolitical risk ({escalation:.2f}). Risk-off regime. "
                    f"CHF safe-haven bid — bearish USD/CHF.",
                    TemporalLayer.T1,
                )
            elif is_safe_haven_pair:
                # USD strengthens vs non-safe-haven currencies
                return (
                    SignalDirection.BEARISH,
                    min(0.65, 0.45 + escalation * 0.2),
                    f"High geopolitical risk ({escalation:.2f}). Risk-off regime. "
                    f"USD safe-haven bid — bearish for base currency vs USD.",
                    TemporalLayer.T1,
                )
            elif is_risk_on_pair:
                # Risk-on currencies weaken
                return (
                    SignalDirection.BEARISH,
                    min(0.70, 0.50 + escalation * 0.2),
                    f"High geopolitical risk ({escalation:.2f}). Risk-off regime. "
                    f"Risk-on currencies under pressure — bearish for this pair.",
                    TemporalLayer.T1,
                )
            else:
                return (
                    SignalDirection.NEUTRAL,
                    0.45,
                    f"High geopolitical risk ({escalation:.2f}). Risk-off regime. "
                    f"No clear flow direction for this pair.",
                    TemporalLayer.T1,
                )

        elif escalation >= ESCALATION_MODERATE:
            # Elevated but not acute — mild risk-off bias
            if is_risk_on_pair:
                return (
                    SignalDirection.BEARISH,
                    0.50,
                    f"Moderate geopolitical tension ({escalation:.2f}). "
                    f"Mild risk-off bias — headwind for risk-on currencies.",
                    TemporalLayer.T1,
                )
            return (
                SignalDirection.NEUTRAL,
                0.45,
                f"Moderate geopolitical tension ({escalation:.2f}). "
                f"No dominant capital flow direction at this risk level.",
                TemporalLayer.T2,
            )

        elif escalation >= ESCALATION_LOW:
            # Low risk — mild risk-on
            if is_risk_on_pair:
                return (
                    SignalDirection.BULLISH,
                    0.50,
                    f"Low geopolitical risk ({escalation:.2f}). Risk-on environment. "
                    f"Supportive for carry/growth currencies.",
                    TemporalLayer.T2,
                )
            return (
                SignalDirection.NEUTRAL,
                0.40,
                f"Low geopolitical risk ({escalation:.2f}). "
                f"Background noise — flow signal too weak for directional call.",
                TemporalLayer.T2,
            )

        else:
            # Calm — risk-on
            if is_risk_on_pair:
                return (
                    SignalDirection.BULLISH,
                    0.55,
                    f"Geopolitical calm ({escalation:.2f}). Risk appetite strong. "
                    f"Carry trade flows support risk-on currencies.",
                    TemporalLayer.T2,
                )
            return (
                SignalDirection.NEUTRAL,
                0.40,
                f"Geopolitical calm ({escalation:.2f}). "
                f"No strong flow signal — FX driven by other factors.",
                TemporalLayer.T2,
            )
