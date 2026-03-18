"""
Inventory Agent — T2 (strategic, weeks → months)
The single most important commodity signal.

An inventory DRAW (stocks falling) = bullish for price.
An inventory BUILD (stocks rising) = bearish for price.

Connects to: EIA weekly petroleum data
Confidence range: 0.70–0.88 (hard data, high trust)
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.eia import EIAFeed


# Thresholds for interpreting inventory changes (thousand barrels)
LARGE_DRAW_THRESHOLD = -3000    # draw > 3M bbl = strong bullish
SMALL_DRAW_THRESHOLD = -500     # draw > 500k bbl = mild bullish
SMALL_BUILD_THRESHOLD = 500     # build < 500k bbl = mild bearish
LARGE_BUILD_THRESHOLD = 3000    # build > 3M bbl = strong bearish


class InventoryAgent:
    """
    Reads EIA weekly petroleum inventory data and produces a T2 signal.
    Hard data — this is the agent with the highest credibility weight.
    """

    AGENT_ID = "inventory_agent"

    def __init__(self, eia_feed: EIAFeed):
        self.feed = eia_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch latest inventory data and produce a directional signal.
        Returns UNKNOWN with low confidence if data is unavailable (ZERO FABRICATION).
        """
        result = self.feed.fetch()

        # ── No data → honest UNKNOWN ────────────────────────────────────
        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="EIA weekly petroleum (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["EIA feed restored"],
                reasoning=f"EIA feed unavailable — no inventory data this cycle. Error: {result.error}",
            )

        data = result.data
        try:
            change = float(data["change"]) if data.get("change") is not None else None
            latest = float(data["latest"]) if data.get("latest") is not None else None
        except (TypeError, ValueError):
            change = None
            latest = None

        # ── No usable change data → UNKNOWN ─────────────────────────────
        if change is None:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="EIA weekly petroleum",
                value=data,
                direction=SignalDirection.UNKNOWN,
                confidence=0.30,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["Next EIA weekly release"],
                reasoning="EIA data received but change could not be calculated.",
            )

        # ── Interpret the draw/build ─────────────────────────────────────
        direction, confidence, reasoning = self._interpret(change, latest)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="EIA weekly petroleum",
            value={
                "latest_stocks": latest,
                "weekly_change": change,
                "unit": data.get("unit", "thousand barrels"),
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T2,
            domain_path=domain_path,
            decay_triggers=[
                "OPEC announces output increase >500k bpd",
                "US SPR release >20M barrels announced",
                "Major demand shock (e.g. China lockdown)",
                "EIA revises prior week data significantly",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _interpret(self, change: float, latest) -> tuple[SignalDirection, float, str]:
        """
        Convert raw inventory change into direction + confidence.
        Larger moves = higher confidence.
        """
        latest_str = f"{latest:,.0f}k bbl" if latest else "unknown level"

        if change <= LARGE_DRAW_THRESHOLD:
            return (
                SignalDirection.BULLISH,
                0.85,
                f"Large inventory draw of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Strong supply tightening signal.",
            )
        elif change <= SMALL_DRAW_THRESHOLD:
            return (
                SignalDirection.BULLISH,
                0.72,
                f"Moderate inventory draw of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Supply modestly tightening.",
            )
        elif change < SMALL_BUILD_THRESHOLD:
            return (
                SignalDirection.NEUTRAL,
                0.60,
                f"Inventory roughly flat ({change:+,.0f}k bbl). "
                f"Stocks at {latest_str}. No clear supply signal.",
            )
        elif change < LARGE_BUILD_THRESHOLD:
            return (
                SignalDirection.BEARISH,
                0.72,
                f"Moderate inventory build of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Supply loosening.",
            )
        else:
            return (
                SignalDirection.BEARISH,
                0.85,
                f"Large inventory build of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Strong supply glut signal.",
            )
