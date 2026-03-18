"""
Sentiment Agent — T0/T1 (seconds → days)
News narrative momentum for FX pairs.

Uses GDELT feed with FX-specific queries to measure
narrative velocity and tone around currency pairs.

This is the LOWEST credibility weight agent — narratives are noisy.
Useful as a momentum confirmation, not a primary signal.

Confidence range: 0.30–0.55
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


class SentimentAgent:
    """
    Reads news narrative momentum for FX pairs.
    Uses GDELT article volume and tone as a proxy for sentiment velocity.
    Lowest credibility weight — useful but noisy.
    """

    AGENT_ID = "fx_sentiment_agent"

    def __init__(self, gdelt_feed: GDELTFeed):
        self.feed = gdelt_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Measure narrative momentum via news volume and tone for FX.
        """
        query = self._domain_to_query(domain_path)
        result = self.feed.fetch(query=query)

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT FX sentiment (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T1,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="FX sentiment feed unavailable — no narrative signal this cycle.",
            )

        data = result.data
        article_count = data.get("article_count", 0)
        avg_tone = data.get("avg_tone", 0.0)

        direction, confidence, reasoning = self._interpret(
            article_count, avg_tone, domain_path
        )

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT FX news sentiment",
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
                "Central bank surprise announcement overrides narrative",
                "News volume drops below 5 articles/day on FX topic",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _domain_to_query(self, domain_path: str) -> str:
        """Map FX domain path to a GDELT search query."""
        query_map = {
            "fx.major.eurusd":  "euro dollar EUR USD exchange rate ECB Fed",
            "fx.major.usdjpy":  "dollar yen USD JPY Bank Japan exchange rate",
            "fx.major.gbpusd":  "pound dollar GBP USD sterling Bank England",
            "fx.major.usdchf":  "dollar franc USD CHF Swiss National Bank",
            "fx.major.audusd":  "Australian dollar AUD USD RBA exchange rate",
            "fx.major.nzdusd":  "New Zealand dollar NZD USD RBNZ exchange rate",
        }
        return query_map.get(domain_path, "foreign exchange currency rate central bank")

    def _interpret(
        self, article_count: int, avg_tone: float, domain_path: str
    ) -> tuple[SignalDirection, float, str]:
        """
        Interpret FX narrative signals.
        For FX, negative tone about a currency = bearish for that currency.
        High volume + negative tone = fear/crisis = USD/JPY/CHF strengthening.
        High volume + positive tone = confidence = risk-on currencies strengthening.
        """
        if article_count < 5:
            return (
                SignalDirection.NEUTRAL,
                0.30,
                f"Low FX news volume ({article_count} articles) — narrative is quiet. "
                f"No momentum signal for this pair.",
            )

        # Strong negative tone with high volume = crisis/fear narrative
        if avg_tone < -2.0 and article_count > 20:
            return (
                SignalDirection.BEARISH,
                0.55,
                f"Strong negative FX narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Fear narrative accelerating — bearish for risk, bullish for safe havens. "
                f"Base currency likely under pressure if not a safe haven.",
            )

        if avg_tone < -1.0:
            return (
                SignalDirection.BEARISH,
                0.45,
                f"Moderately negative FX narrative (tone {avg_tone:.1f}). "
                f"Concern building — mild bearish bias for base currency.",
            )

        if avg_tone > 1.0 and article_count > 20:
            return (
                SignalDirection.BULLISH,
                0.45,
                f"Positive FX narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Optimism may support base currency — but watch for reversal.",
            )

        return (
            SignalDirection.NEUTRAL,
            0.35,
            f"FX narrative is balanced (tone {avg_tone:.1f}, {article_count} articles). "
            f"No clear directional momentum from news flow.",
        )
