"""
Geopolitical Agent — T1/T2/T3
War is the world holding its breath.

Reads the war/conflict cycle phase:
  Escalation  → inhale  → bullish energy, bearish risk assets
  Stalemate   → held    → elevated vol, narrative-driven
  Resolution  → exhale  → supply routes reopen, risk premium compresses

Connects to: GDELT event database
Confidence range: 0.40–0.78
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


# Escalation thresholds (GDELT tone-derived)
ESCALATION_HIGH = 0.6     # strong negative tone — active conflict
ESCALATION_MODERATE = 0.3  # elevated tension
ESCALATION_LOW = 0.15      # background noise


class GeopoliticalAgent:
    """
    Reads geopolitical event flow and maps it to the war/conflict cycle.
    Key regions: Middle East, Ukraine/Russia, Red Sea, Hormuz, Taiwan.
    """

    AGENT_ID = "geopolitical_agent"

    def __init__(self, gdelt_feed: GDELTFeed):
        self.feed = gdelt_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch geopolitical events and produce a directional signal.
        Escalation = bullish for commodities (supply risk).
        Resolution = bearish (risk premium drops).
        """
        result = self.feed.fetch(query="oil energy conflict sanctions war")

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
                reasoning="GDELT feed unavailable — no geopolitical signal this cycle.",
            )

        data = result.data
        escalation = data.get("escalation_score", 0.0)
        article_count = data.get("article_count", 0)
        active_regions = data.get("active_regions", [])

        direction, confidence, reasoning, layer = self._interpret(
            escalation, article_count, active_regions
        )

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT geopolitical events",
            value={
                "escalation_score": escalation,
                "article_count": article_count,
                "active_regions": active_regions,
            },
            direction=direction,
            confidence=confidence,
            layer=layer,
            domain_path=domain_path,
            decay_triggers=[
                "Ceasefire agreement in key producing region",
                "New sanctions on major oil exporter",
                "Military escalation at key shipping chokepoint",
                "Diplomatic breakthrough (e.g. Iran nuclear deal)",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _interpret(
        self, escalation: float, article_count: int, active_regions: list
    ) -> tuple[SignalDirection, float, str, TemporalLayer]:
        """
        Map escalation score to direction and confidence.
        High escalation = bullish commodities (supply risk premium).
        """
        regions_str = ", ".join(active_regions) if active_regions else "none detected"

        if escalation >= ESCALATION_HIGH:
            return (
                SignalDirection.BULLISH,
                min(0.78, 0.60 + escalation * 0.2),
                f"High geopolitical escalation ({escalation:.2f}). "
                f"Active regions: {regions_str}. "
                f"Supply risk premium rising — bullish for commodities.",
                TemporalLayer.T1,
            )
        elif escalation >= ESCALATION_MODERATE:
            return (
                SignalDirection.BULLISH,
                0.55,
                f"Moderate geopolitical tension ({escalation:.2f}). "
                f"Active regions: {regions_str}. "
                f"Elevated but not acute — mild supply risk premium.",
                TemporalLayer.T1,
            )
        elif escalation >= ESCALATION_LOW:
            return (
                SignalDirection.NEUTRAL,
                0.45,
                f"Low-level geopolitical noise ({escalation:.2f}). "
                f"No acute supply chain threat detected.",
                TemporalLayer.T2,
            )
        else:
            return (
                SignalDirection.BEARISH,
                0.50,
                f"Geopolitical calm ({escalation:.2f}). "
                f"Risk premium likely compressing — mildly bearish for commodities.",
                TemporalLayer.T2,
            )
