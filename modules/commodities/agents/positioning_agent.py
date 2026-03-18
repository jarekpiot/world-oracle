"""
Positioning Agent — T1/T2
How is the market positioned? Crowded trades reverse.

CFTC Commitment of Traders:
  Speculators extremely long → crowded → reversal risk (bearish)
  Speculators extremely short → washed out → bounce risk (bullish)
  Commercials heavily short → hedgers expect lower prices (bearish)

Connects to: CFTC COT reports (weekly, free)
Confidence range: 0.30–0.72
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.cot import COTFeed


class PositioningAgent:
    """
    Reads CFTC Commitment of Traders data to gauge market positioning.
    Extreme positioning = contrarian signal (crowded trades reverse).
    """

    AGENT_ID = "positioning_agent"

    def __init__(self, cot_feed: COTFeed):
        self.feed = cot_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch COT positioning data and produce a signal.
        Currently returns UNKNOWN — CFTC parser pending.
        """
        result = self.feed.fetch()

        if not result.ok:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="CFTC COT (unavailable)",
                value={"status": "feed_unavailable"},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["COT feed restored"],
                reasoning="CFTC COT feed unavailable — no positioning signal this cycle.",
            )

        data = result.data

        # COT parser not yet built — return honest UNKNOWN
        if not data or not data.get("available", False):
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="CFTC COT (parser pending)",
                value=data or {},
                direction=SignalDirection.UNKNOWN,
                confidence=0.30,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=[
                    "COT parser implemented",
                    "Next weekly COT release",
                ],
                reasoning="CFTC COT data format parser pending — cannot interpret positioning yet. "
                          "No fabrication: returning UNKNOWN until parser is built.",
            )

        # Future: when parser is built, interpret positioning
        spec_net = data.get("spec_net_long")
        extreme = data.get("extreme_positioning")

        if extreme == "long":
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="CFTC COT",
                value=data,
                direction=SignalDirection.BEARISH,
                confidence=0.68,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=[
                    "Speculative long positions reduce >15%",
                    "New bullish catalyst overrides positioning concern",
                ],
                reasoning=f"Speculators extremely long — crowded trade, reversal risk elevated.",
                raw_data=data,
            )
        elif extreme == "short":
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="CFTC COT",
                value=data,
                direction=SignalDirection.BULLISH,
                confidence=0.68,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=[
                    "Speculative short positions reduce >15%",
                    "New bearish catalyst overrides positioning signal",
                ],
                reasoning=f"Speculators extremely short — washed out, bounce risk elevated.",
                raw_data=data,
            )

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="CFTC COT",
            value=data,
            direction=SignalDirection.NEUTRAL,
            confidence=0.50,
            layer=TemporalLayer.T2,
            domain_path=domain_path,
            decay_triggers=["Next weekly COT release", "Position shift >10%"],
            reasoning="Positioning is balanced — no extreme that would signal reversal risk.",
            raw_data=data,
        )
