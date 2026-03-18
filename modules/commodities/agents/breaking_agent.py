"""
Breaking Event Agent — T0 (minutes)
The flash. Something just happened.

This agent is NOT the geopolitical cycle reader (that's GeopoliticalAgent, T1/T2).
This agent catches the FLASH — the event that happened in the last hour:
  Missile strike, tanker seizure, pipeline explosion, emergency OPEC call.

The signal is simple:
  Breaking event detected → BULLISH (supply disruption fear)
  No breaking event       → NEUTRAL (calm is the absence of signal)

How it works:
  1. Query GDELT with breaking-event-specific keywords
  2. Measure article volume spike in last few hours
  3. High volume + very negative tone = something bad just happened
  4. Return BULLISH with confidence proportional to spike magnitude

Connects to: GDELT event database (different query than geopolitical_agent)
Confidence range: 0.25–0.80
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


# ── Breaking event detection thresholds ──────────────────────────────────────

# GDELT query — very different from geopolitical_agent's broad crisis query.
# This targets specific event types that move commodity markets within minutes.
BREAKING_QUERY = (
    "explosion OR missile OR strike OR attack OR drone "
    "OR seizure OR tanker OR port closure OR shutdown "
    "OR emergency OPEC OR pipeline sabotage OR sanctions announced"
)

# Article volume thresholds — a spike means something happened
VOLUME_SPIKE_HIGH = 30      # 30+ articles in the window = major event
VOLUME_SPIKE_MODERATE = 15  # 15+ articles = probable event
VOLUME_SPIKE_LOW = 5        # <5 articles = background noise

# Tone thresholds — breaking events have strongly negative tone
TONE_VERY_NEGATIVE = -4.0   # crisis-level negativity
TONE_NEGATIVE = -2.0        # elevated concern


class BreakingEventAgent:
    """
    T0 flash detector. Catches breaking supply-disruption events
    from GDELT article spikes with highly negative tone.

    Different from GeopoliticalAgent:
      - GeopoliticalAgent reads the ARC (T1/T2 conflict cycle phase)
      - BreakingEventAgent reads the FLASH (T0 event that just happened)
    """

    AGENT_ID = "breaking_event_agent"

    def __init__(self, gdelt_feed: GDELTFeed):
        self.feed = gdelt_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Query GDELT for breaking event keywords.
        Spike in volume + negative tone = T0 breaking event.
        Returns UNKNOWN if GDELT is down (ZERO FABRICATION).
        """
        result = self.feed.fetch(
            query=BREAKING_QUERY,
            mode="artlist",
        )

        # ── GDELT down → honest UNKNOWN ──────────────────────────────
        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT breaking events (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T0,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="GDELT feed unavailable — no T0 breaking event detection this cycle.",
            )

        data = result.data
        article_count = data.get("article_count", 0)
        avg_tone = data.get("avg_tone", 0.0)

        direction, confidence, reasoning = self._interpret(
            article_count, avg_tone, data
        )

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT breaking events",
            value={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "active_regions": data.get("active_regions", []),
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T0,
            domain_path=domain_path,
            decay_triggers=[
                "Event confirmed as non-supply-impacting",
                "Official denial from credible source",
                "Supply route confirmed operational",
                "Market absorbs event without price reaction",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _interpret(
        self, article_count: int, avg_tone: float, data: dict
    ) -> tuple[SignalDirection, float, str]:
        """
        Breaking event detection logic:
          High volume + very negative tone = T0 flash (BULLISH for commodities)
          Low volume or mild tone          = no breaking event (NEUTRAL)
        """
        regions = data.get("active_regions", [])
        regions_str = ", ".join(regions) if regions else "none detected"

        # ── No volume spike → nothing breaking ───────────────────────
        if article_count < VOLUME_SPIKE_LOW:
            return (
                SignalDirection.NEUTRAL,
                0.40,
                f"No breaking event detected. Article volume low ({article_count}). "
                f"Calm at T0 — no supply disruption flash.",
            )

        # ── Volume spike detected — check tone ───────────────────────
        is_very_negative = avg_tone <= TONE_VERY_NEGATIVE
        is_negative = avg_tone <= TONE_NEGATIVE

        if article_count >= VOLUME_SPIKE_HIGH and is_very_negative:
            # Major breaking event — high volume, crisis tone
            confidence = min(0.80, 0.65 + (article_count - VOLUME_SPIKE_HIGH) * 0.003)
            return (
                SignalDirection.BULLISH,
                confidence,
                f"BREAKING EVENT DETECTED. Article spike ({article_count}) with "
                f"crisis-level tone ({avg_tone:.1f}). Regions: {regions_str}. "
                f"Supply disruption fear — bullish for commodities.",
            )

        if article_count >= VOLUME_SPIKE_MODERATE and is_negative:
            # Probable breaking event — moderate volume, negative tone
            confidence = min(0.72, 0.60 + (article_count - VOLUME_SPIKE_MODERATE) * 0.004)
            return (
                SignalDirection.BULLISH,
                confidence,
                f"Probable breaking event. Elevated article volume ({article_count}) "
                f"with negative tone ({avg_tone:.1f}). Regions: {regions_str}. "
                f"Potential supply disruption — bullish signal.",
            )

        if article_count >= VOLUME_SPIKE_MODERATE and not is_negative:
            # Volume spike but tone not negative enough — could be
            # a non-threatening event (e.g. diplomatic meeting)
            return (
                SignalDirection.NEUTRAL,
                0.45,
                f"Article volume elevated ({article_count}) but tone not crisis-level "
                f"({avg_tone:.1f}). Volume spike may be non-supply-threatening event.",
            )

        # Low-moderate volume with some negativity — watch but no signal
        return (
            SignalDirection.NEUTRAL,
            0.40,
            f"Low article activity ({article_count}, tone {avg_tone:.1f}). "
            f"No breaking supply disruption event detected at T0.",
        )
