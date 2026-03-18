"""
Regulation Agent — T2/T3
Regulatory cycle is THE T2/T3 driver for crypto.

No other asset class is as sensitive to regulation as crypto:
  SEC enforcement        -> existential risk for individual tokens
  CFTC jurisdiction      -> commodity vs security classification
  MiCA (EU)              -> framework clarity, compliance costs
  Stablecoin regulation  -> systemic risk management
  CBDC development       -> competitive threat or validation

Positive regulation = framework clarity = bullish (institutional money can enter)
Negative regulation = enforcement/bans = bearish (capital flight)

Connects to: GDELT (regulation news tone/volume)
Confidence range: 0.40-0.65
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


class RegulationAgent:
    """
    Tracks crypto regulatory developments via news analysis.
    Regulation is the dominant T2/T3 driver for digital assets.
    Positive regulation (framework clarity) = bullish.
    Negative regulation (enforcement, bans) = bearish.
    """

    AGENT_ID = "crypto_regulation_agent"

    def __init__(self, gdelt_feed: GDELTFeed):
        self.feed = gdelt_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Measure regulatory narrative via GDELT news analysis.
        """
        query = self._build_query(domain_path)
        result = self.feed.fetch(query=query)

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT crypto regulation (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="Crypto regulation feed unavailable — no regulatory signal this cycle.",
            )

        data = result.data
        article_count = data.get("article_count", 0)
        avg_tone = data.get("avg_tone", 0.0)

        direction, confidence, reasoning = self._interpret(article_count, avg_tone, domain_path)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT crypto regulation",
            value={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "query": query,
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T2,
            domain_path=domain_path,
            decay_triggers=[
                "New regulatory bill introduced or enacted",
                "SEC or CFTC enforcement action filed",
                "Major court ruling on crypto classification",
                "International regulatory body issues new guidance",
            ],
            reasoning=reasoning,
            raw_data=data,
            valid_horizon="8 weeks",
        )

    def _build_query(self, domain_path: str) -> str:
        """Build regulation-specific GDELT query."""
        parts = domain_path.split(".")
        asset = parts[-1] if len(parts) > 1 else "crypto"

        base_terms = "cryptocurrency regulation SEC CFTC MiCA"
        asset_terms = {
            "bitcoin":   "bitcoin regulation SEC ETF approval",
            "ethereum":  "ethereum regulation SEC staking securities",
            "solana":    "solana regulation SEC securities",
        }
        return asset_terms.get(asset, base_terms)

    def _interpret(
        self, article_count: int, avg_tone: float, domain_path: str
    ) -> tuple[SignalDirection, float, str]:
        """
        Interpret regulation signals.
        Positive tone = framework clarity, institutional green light = BULLISH
        Negative tone = enforcement, crackdown, bans = BEARISH
        """
        if article_count < 3:
            return (
                SignalDirection.NEUTRAL,
                0.40,
                f"Low regulatory news volume ({article_count} articles). "
                f"No significant regulatory developments detected. "
                f"Regulatory status quo is mildly positive for crypto.",
            )

        # Positive regulatory tone — framework clarity
        if avg_tone > 1.0 and article_count > 10:
            return (
                SignalDirection.BULLISH,
                0.65,
                f"Positive regulatory narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Framework clarity signals are bullish — institutional capital "
                f"flows when regulatory uncertainty decreases.",
            )

        if avg_tone > 0.5:
            return (
                SignalDirection.BULLISH,
                0.55,
                f"Mildly positive regulatory tone ({avg_tone:.1f}). "
                f"Regulatory environment appears constructive. "
                f"Watch for concrete policy announcements.",
            )

        # Negative regulatory tone — enforcement/crackdown
        if avg_tone < -2.0 and article_count > 10:
            return (
                SignalDirection.BEARISH,
                0.65,
                f"Strong negative regulatory narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Enforcement actions or restrictive proposals detected. "
                f"Regulatory crackdown is the highest-impact bearish catalyst for crypto.",
            )

        if avg_tone < -1.0:
            return (
                SignalDirection.BEARISH,
                0.55,
                f"Negative regulatory tone ({avg_tone:.1f}). "
                f"Regulatory headwinds building — may deter institutional inflows.",
            )

        return (
            SignalDirection.NEUTRAL,
            0.45,
            f"Mixed regulatory signals (tone {avg_tone:.1f}, {article_count} articles). "
            f"Regulatory landscape is evolving but no clear directional bias.",
        )
