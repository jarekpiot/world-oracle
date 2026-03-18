"""
Crypto Narrative Agent — T0/T1
Crypto narratives move faster than any other asset class.

A single tweet can move billions. A regulatory headline can crash or pump
the entire market in minutes. This is NOT like commodity narratives.

Key differences from commodities narrative agent:
  - Higher weight on volume than tone (crypto is always noisy)
  - Shorter decay window (crypto narratives burn fast)
  - Crypto-specific query terms
  - Lower confidence ceiling (too much noise)

Connects to: GDELT (news tone/volume)
Confidence range: 0.30–0.55
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


class CryptoNarrativeAgent:
    """
    Reads news narrative momentum for crypto markets.
    Uses GDELT article volume and tone as a proxy for narrative velocity.
    Higher weight on volume than tone — crypto news is always noisy.
    """

    AGENT_ID = "crypto_narrative_agent"

    def __init__(self, gdelt_feed: GDELTFeed):
        self.feed = gdelt_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Measure narrative momentum via news volume and tone.
        Crypto-specific: volume matters more than tone.
        """
        query = self._domain_to_query(domain_path)
        result = self.feed.fetch(query=query)

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT crypto narrative (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T1,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="Crypto narrative feed unavailable — no sentiment signal this cycle.",
            )

        data = result.data
        article_count = data.get("article_count", 0)
        avg_tone = data.get("avg_tone", 0.0)

        direction, confidence, reasoning = self._interpret(article_count, avg_tone, domain_path)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT crypto narrative",
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
                "Narrative reversal — tone shifts >3 points in 12h",
                "Major exchange hack or exploit",
                "Surprise regulatory announcement",
                "News volume drops below 5 articles/day on topic",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _domain_to_query(self, domain_path: str) -> str:
        """Map domain path to a GDELT search query with crypto-specific terms."""
        parts = domain_path.split(".")
        query_map = {
            "bitcoin":   "bitcoin BTC price ETF institutional",
            "ethereum":  "ethereum ETH price DeFi smart contracts",
            "solana":    "solana SOL price DeFi performance",
            "crypto":    "cryptocurrency bitcoin ethereum crypto market",
        }
        asset = parts[-1] if len(parts) > 1 else "crypto"
        return query_map.get(asset, f"{asset} cryptocurrency price market")

    def _interpret(
        self, article_count: int, avg_tone: float, domain_path: str
    ) -> tuple[SignalDirection, float, str]:
        """
        Interpret crypto narrative signals.
        Key difference from commodities: volume is weighted higher than tone.
        Crypto news is always noisy — extreme volume is the real signal.
        """
        if article_count < 5:
            return (
                SignalDirection.NEUTRAL,
                0.30,
                f"Low crypto news volume ({article_count} articles) — narrative is quiet. "
                f"Unusual for crypto — may indicate consolidation phase.",
            )

        # Extreme volume is the signal in crypto, not just tone
        if article_count > 40:
            # High volume + negative tone = panic/capitulation
            if avg_tone < -2.0:
                return (
                    SignalDirection.BEARISH,
                    0.55,
                    f"Extreme negative narrative ({article_count} articles, tone {avg_tone:.1f}). "
                    f"Panic/capitulation narrative — typically bearish short-term "
                    f"but watch for capitulation bottom.",
                )
            # High volume + positive tone = euphoria
            if avg_tone > 1.5:
                return (
                    SignalDirection.BULLISH,
                    0.50,
                    f"Euphoric narrative ({article_count} articles, tone {avg_tone:.1f}). "
                    f"Momentum is strong but euphoria often precedes corrections.",
                )
            # High volume + neutral tone = major event processing
            return (
                SignalDirection.NEUTRAL,
                0.40,
                f"High volume neutral narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Market is processing a major event — direction unclear.",
            )

        # Moderate volume — tone becomes more relevant
        if avg_tone < -1.5:
            return (
                SignalDirection.BEARISH,
                0.45,
                f"Negative crypto narrative (tone {avg_tone:.1f}). "
                f"Fear building but not at capitulation levels.",
            )

        if avg_tone > 1.0:
            return (
                SignalDirection.BULLISH,
                0.45,
                f"Positive crypto narrative (tone {avg_tone:.1f}). "
                f"Optimism building — watch for confirmation from on-chain data.",
            )

        return (
            SignalDirection.NEUTRAL,
            0.35,
            f"Crypto narrative is balanced (tone {avg_tone:.1f}, {article_count} articles). "
            f"No clear directional momentum from news flow.",
        )
