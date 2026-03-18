"""
Positioning Agent — T2
How is the market positioned? Crowded trades reverse.

CFTC Commitment of Traders:
  Speculators extremely long -> crowded -> reversal risk (bearish)
  Speculators extremely short -> washed out -> bounce risk (bullish)
  Commercials heavily short -> hedgers expect lower prices (bearish)

Connects to: CFTC COT reports (weekly, free)
Confidence range: 0.45-0.72
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.cot import COTFeed


# Map domain paths to COT commodity keys
DOMAIN_TO_COT = {
    "commodity.energy.crude_oil":       "crude_oil",
    "commodity.energy.natural_gas":     "natural_gas",
    "commodity.metals.gold":            "gold",
    "commodity.metals.silver":          "silver",
    "commodity.metals.copper":          "copper",
    "commodity.agriculture.wheat":      "wheat",
    "commodity.agriculture.corn":       "corn",
    "commodity.agriculture.soy":        "soy",
}


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
        """
        # Map domain to commodity key
        commodity = DOMAIN_TO_COT.get(domain_path, "crude_oil")

        result = self.feed.fetch(commodity=commodity)

        if not result.ok:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="CFTC COT (unavailable)",
                value={"status": "feed_unavailable", "error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["CFTC feed restored"],
                reasoning=f"CFTC COT feed unavailable: {result.error}",
            )

        data = result.data

        if not data or not data.get("available", False):
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="CFTC COT (no data)",
                value=data or {},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["Next weekly COT release"],
                reasoning=f"CFTC COT data not available: {data.get('reason', 'unknown')}",
            )

        # We have real data — interpret it
        return self._interpret(data, domain_path)

    def _interpret(self, data: dict, domain_path: str) -> Signal:
        """
        Interpret COT positioning into a directional signal.
        """
        extreme = data.get("extreme_positioning")
        mm_net = data.get("managed_money_net")
        mm_pct = data.get("managed_money_net_pct_oi")
        report_date = data.get("report_date", "unknown")
        market = data.get("market", "unknown")

        mm_net_str = f"{mm_net:+,}" if mm_net is not None else "N/A"
        pct_str = f"{mm_pct:+.1f}% of OI" if mm_pct is not None else ""

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
                    "Managed money net long reduces >15% week-over-week",
                    "New bullish catalyst overrides positioning concern",
                    "Next COT report shows significant position change",
                ],
                reasoning=f"Managed money extremely long (net {mm_net_str}, {pct_str}). "
                          f"Crowded trade — reversal risk elevated. "
                          f"Report date: {report_date}. Market: {market}.",
                raw_data=data,
            )

        if extreme == "short":
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="CFTC COT",
                value=data,
                direction=SignalDirection.BULLISH,
                confidence=0.68,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=[
                    "Managed money net short reduces >15% week-over-week",
                    "New bearish catalyst overrides positioning signal",
                    "Next COT report shows significant position change",
                ],
                reasoning=f"Managed money extremely short (net {mm_net_str}, {pct_str}). "
                          f"Washed out — bounce risk elevated. "
                          f"Report date: {report_date}. Market: {market}.",
                raw_data=data,
            )

        # Not extreme — balanced positioning
        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="CFTC COT",
            value=data,
            direction=SignalDirection.NEUTRAL,
            confidence=0.50,
            layer=TemporalLayer.T2,
            domain_path=domain_path,
            decay_triggers=[
                "Next weekly COT release",
                "Managed money position shift >10% week-over-week",
                "Open interest change >15% indicating new money entering",
            ],
            reasoning=f"Managed money net {mm_net_str} ({pct_str}). "
                      f"Positioning is balanced — no extreme that would signal reversal risk. "
                      f"Report date: {report_date}.",
            raw_data=data,
        )
