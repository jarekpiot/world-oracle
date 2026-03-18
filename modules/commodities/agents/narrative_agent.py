"""
Narrative Agent — T0/T1
How is the story moving? Narratives drive short-term price action.

This agent reads the momentum of the current narrative:
  Accelerating bullish narrative → T1 bullish (momentum)
  Fading narrative → signal weakening
  Narrative reversal → counter-trend risk

Connects to: GDELT (news tone), future: social sentiment
Confidence range: 0.35–0.65 (lowest raw credibility — narratives are noisy)
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


class NarrativeAgent:
    """
    Reads news narrative momentum for commodity markets.
    Uses GDELT article volume and tone as a proxy for narrative velocity.
    Lowest credibility weight — useful but noisy.
    """

    AGENT_ID = "narrative_agent"

    def __init__(self, gdelt_feed: GDELTFeed):
        self.feed = gdelt_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Measure narrative momentum via news volume and tone.
        """
        # Build a commodity-specific query from the domain path
        query = self._domain_to_query(domain_path)
        result = self.feed.fetch(query=query)

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT narrative (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T1,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="News narrative feed unavailable — no sentiment signal this cycle.",
            )

        data = result.data
        article_count = data.get("article_count", 0)
        avg_tone = data.get("avg_tone", 0.0)

        direction, confidence, reasoning = self._interpret(article_count, avg_tone, domain_path)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT news narrative",
            value={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "query": query,
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T1,
            domain_path=domain_path,
            decay_triggers=[
                "Narrative reversal — tone shifts >2 points in 24h",
                "Major counter-narrative event (e.g. surprise data release)",
                "News volume drops below 10 articles/day on topic",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _domain_to_query(self, domain_path: str) -> str:
        """Map domain path to a GDELT search query."""
        parts = domain_path.split(".")
        query_map = {
            "crude_oil":    "crude oil price supply demand OPEC",
            "natural_gas":  "natural gas LNG price supply",
            "gold":         "gold price safe haven demand",
            "copper":       "copper price industrial demand China",
            "wheat":        "wheat price crop harvest supply",
            "corn":         "corn price ethanol crop",
        }
        asset = parts[-1] if len(parts) > 1 else "commodity"
        return query_map.get(asset, f"{asset} commodity price supply demand")

    def _interpret(
        self, article_count: int, avg_tone: float, domain_path: str
    ) -> tuple[SignalDirection, float, str]:
        """
        Interpret narrative signals.
        High volume + negative tone = fear narrative (bullish for safe havens, mixed for energy).
        High volume + positive tone = optimism narrative.
        Low volume = narrative fading.
        """
        if article_count < 5:
            return (
                SignalDirection.NEUTRAL,
                0.35,
                f"Low news volume ({article_count} articles) — narrative is quiet. "
                f"No strong momentum in either direction.",
            )

        # Negative tone with high volume = crisis/fear narrative
        if avg_tone < -2.0 and article_count > 20:
            return (
                SignalDirection.BULLISH,
                0.60,
                f"Strong negative narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Fear/crisis narrative accelerating — typically bullish for commodities "
                f"via supply disruption concerns.",
            )

        if avg_tone < -1.0:
            return (
                SignalDirection.BULLISH,
                0.50,
                f"Moderately negative narrative (tone {avg_tone:.1f}). "
                f"Concern narrative building but not dominant.",
            )

        if avg_tone > 1.0 and article_count > 20:
            return (
                SignalDirection.BEARISH,
                0.50,
                f"Positive narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Optimism may indicate complacency — watch for reversal.",
            )

        return (
            SignalDirection.NEUTRAL,
            0.40,
            f"Narrative is balanced (tone {avg_tone:.1f}, {article_count} articles). "
            f"No clear directional momentum from news flow.",
        )
