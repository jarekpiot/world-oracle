"""
Price Agent — T0 (seconds → minutes)
The heartbeat. What is price doing RIGHT NOW?

This agent reads the most recent spot price and compares to prior session:
  Price rising   → confirms bullish thesis (or diverges from bearish)
  Price falling  → confirms bearish thesis (or diverges from bullish)
  Price flat     → no T0 signal

The key T0 insight isn't the direction alone — it's whether price
CONFIRMS or DIVERGES from the higher-layer view.

Connects to: EIA spot price (daily, free)
Confidence range: 0.35–0.70
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.price import PriceFeed


# Price move thresholds (percentage)
LARGE_MOVE_PCT = 3.0      # >3% daily move = significant
MODERATE_MOVE_PCT = 1.0    # >1% = moderate
NOISE_THRESHOLD_PCT = 0.3  # <0.3% = noise, not signal


class PriceAgent:
    """
    Reads live/recent spot price and produces a T0 heartbeat signal.
    The fastest breathing frequency — what is price telling us right now?
    """

    AGENT_ID = "price_agent"

    def __init__(self, price_feed: PriceFeed):
        self.feed = price_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch latest price and produce a T0 signal.
        Returns UNKNOWN if price data unavailable (ZERO FABRICATION).
        """
        result = self.feed.fetch()

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="EIA spot price (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T0,
                domain_path=domain_path,
                decay_triggers=["Price feed restored"],
                reasoning="Price feed unavailable — no T0 heartbeat signal.",
            )

        data = result.data
        price = data.get("price")
        pct_change = data.get("pct_change")

        if price is None:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="EIA spot price",
                value=data,
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T0,
                domain_path=domain_path,
                decay_triggers=["Next price update"],
                reasoning="Price data received but no usable price value.",
            )

        if pct_change is None:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="EIA spot price",
                value=data,
                direction=SignalDirection.NEUTRAL,
                confidence=0.35,
                layer=TemporalLayer.T0,
                domain_path=domain_path,
                decay_triggers=["Next price update"],
                reasoning=f"Current price ${price:.2f} but no prior session to compare.",
            )

        direction, confidence, reasoning = self._interpret(price, pct_change, data)

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="EIA spot price",
            value={
                "price": price,
                "pct_change": pct_change,
                "change": data.get("change"),
                "unit": data.get("unit", "USD/barrel"),
                "period": data.get("period"),
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T0,
            domain_path=domain_path,
            decay_triggers=[
                "Price reverses >1% from current level",
                "Breaking news event overrides price action",
                "Next trading session opens with gap",
                "Volume spike indicates forced liquidation",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

    def _interpret(
        self, price: float, pct_change: float, data: dict
    ) -> tuple[SignalDirection, float, str]:
        """
        Interpret price move into direction + confidence.
        Larger moves = higher confidence in the T0 signal.
        """
        change_str = f"{pct_change:+.2f}%"
        price_str = f"${price:.2f}"
        abs_change = abs(pct_change)

        if abs_change < NOISE_THRESHOLD_PCT:
            return (
                SignalDirection.NEUTRAL,
                0.40,
                f"Price at {price_str} ({change_str}). "
                f"Move is within noise range — no directional T0 signal.",
            )

        if pct_change > 0:
            direction = SignalDirection.BULLISH
            if abs_change >= LARGE_MOVE_PCT:
                confidence = 0.70
                desc = "Large upward move"
            elif abs_change >= MODERATE_MOVE_PCT:
                confidence = 0.58
                desc = "Moderate upward move"
            else:
                confidence = 0.45
                desc = "Mild upward move"
        else:
            direction = SignalDirection.BEARISH
            if abs_change >= LARGE_MOVE_PCT:
                confidence = 0.70
                desc = "Large downward move"
            elif abs_change >= MODERATE_MOVE_PCT:
                confidence = 0.58
                desc = "Moderate downward move"
            else:
                confidence = 0.45
                desc = "Mild downward move"

        return (
            direction,
            confidence,
            f"{desc}: {price_str} ({change_str}). "
            f"Price action {'confirms' if abs_change >= MODERATE_MOVE_PCT else 'suggests'} "
            f"{'upward' if pct_change > 0 else 'downward'} pressure at T0.",
        )
